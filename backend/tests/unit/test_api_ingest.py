import gzip
import json
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from google.rpc.status_pb2 import Status
from pydantic import SecretStr

from tests.factories import export_request, record_agent_trace
from tracebench.config import Settings
from tracebench.ingest.batcher import SpanBatcher
from tracebench.ingest.models import SpanRecord
from tracebench.ingest.service import IngestService
from tracebench.main import create_app
from tracebench.pricing.service import PriceService
from tracebench.store.postgres.prices import PriceRepository

PROTOBUF = {"content-type": "application/x-protobuf"}


class MemorySink:
    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []

    async def insert_spans(self, spans: Sequence[SpanRecord]) -> None:
        self.spans.extend(spans)


def app_client(
    *,
    max_pending: int = 10_000,
    body_limit: int = 4096,
    api_token: SecretStr | None = None,
    ingest_token: SecretStr | None = None,
) -> httpx.AsyncClient:
    """The real app and ingest pipeline over an in-memory sink; no databases are started."""
    configured = Settings(
        env="test",
        log_level="WARNING",
        ingest_max_body_bytes=body_limit,
        api_token=api_token,
        ingest_token=ingest_token,
    )
    batcher = SpanBatcher(MemorySink(), max_batch_size=100, flush_interval=60, max_pending=max_pending)
    prices = PriceService(cast("PriceRepository", None), refresh_seconds=60)
    app = create_app(configured)
    app.state.container = SimpleNamespace(settings=configured, ingest=IngestService(batcher, prices))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tracebench")


def trace_bytes() -> bytes:
    payload: bytes = export_request(record_agent_trace()).SerializeToString()
    return payload


async def test_accepts_protobuf_and_gzip() -> None:
    async with app_client(body_limit=1 << 20) as client:
        plain = await client.post("/v1/traces", content=trace_bytes(), headers=PROTOBUF)
        zipped = await client.post(
            "/v1/traces", content=gzip.compress(trace_bytes()), headers={**PROTOBUF, "content-encoding": "gzip"}
        )
    assert plain.status_code == 200 and zipped.status_code == 200


async def test_unsupported_media_type_is_a_json_status() -> None:
    async with app_client() as client:
        response = await client.post("/v1/traces", content=b"x", headers={"content-type": "text/plain"})
    assert response.status_code == 415
    assert response.json()["code"] == 3 and "text/plain" in response.json()["message"]


async def test_bad_protobuf_is_400_with_a_protobuf_status() -> None:
    async with app_client() as client:
        response = await client.post("/v1/traces", content=b"\xff\x00", headers=PROTOBUF)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/x-protobuf"
    assert Status.FromString(response.content).code == 3


@pytest.mark.parametrize("depth", [5_000, 50_000])
async def test_deeply_nested_json_is_rejected_not_crashed(depth: int) -> None:
    nested = "[" * depth + "]" * depth
    body = f'{{"resourceSpans": [{{"scopeSpans": [{{"spans": [{{"attributes": {nested}}}]}}]}}]}}'.encode()
    async with app_client(body_limit=1 << 20) as client:
        response = await client.post("/v1/traces", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert len(response.json()["message"]) < 400


async def test_declared_and_streamed_bodies_over_the_limit_are_413() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"\x00" * 1024

    async with app_client(body_limit=4096) as client:
        declared = await client.post("/v1/traces", content=b"\x00" * 5000, headers=PROTOBUF)
        streamed = await client.post("/v1/traces", content=chunks(), headers=PROTOBUF)
    assert declared.status_code == 413 and streamed.status_code == 413
    assert "content-length" not in streamed.request.headers


async def test_full_buffer_is_a_retryable_503() -> None:
    async with app_client(max_pending=1, body_limit=1 << 20) as client:
        response = await client.post("/v1/traces", content=trace_bytes(), headers=PROTOBUF)
    assert response.status_code == 503
    assert int(response.headers["retry-after"]) > 0
    assert Status.FromString(response.content).code == 14


@pytest.mark.parametrize(("header", "expected"), [(None, 401), ("Bearer wrong", 401), ("Bearer s3cret", 200)])
async def test_ingest_token_is_enforced_when_configured(header: str | None, expected: int) -> None:
    headers = {**PROTOBUF, **({"authorization": header} if header else {})}
    async with app_client(body_limit=1 << 20, ingest_token=SecretStr("s3cret")) as client:
        response = await client.post("/v1/traces", content=trace_bytes(), headers=headers)
    assert response.status_code == expected


async def test_api_token_guards_mutations() -> None:
    async with app_client(api_token=SecretStr("s3cret")) as client:
        response = await client.post("/api/datasets", json={"name": "golden"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert json.loads(response.content)["error"]["code"] == "unauthorized"
