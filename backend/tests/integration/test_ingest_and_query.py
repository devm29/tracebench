import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from google.protobuf import json_format
from google.rpc.status_pb2 import Status

from tests.factories import export_request, record_agent_trace
from tracebench.container import Container

PROTOBUF = {"content-type": "application/x-protobuf"}


async def _ingest(
    client: httpx.AsyncClient, container: Container, service: str, question: str = "Where is 48100?"
) -> str:
    request = export_request(record_agent_trace(service, question=question))
    response = await client.post("/v1/traces", content=request.SerializeToString(), headers=PROTOBUF)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-protobuf"
    await container.ingest.flush()
    return request.resource_spans[0].scope_spans[0].spans[0].trace_id.hex()


async def test_protobuf_ingest_is_queryable_with_costs_and_rollups(
    client: httpx.AsyncClient, container: Container
) -> None:
    service = f"svc-{uuid.uuid4().hex[:8]}"
    trace_id = await _ingest(client, container, service)

    page = (await client.get("/api/traces", params={"service": service})).json()
    assert [t["trace_id"] for t in page["items"]] == [trace_id]
    summary = page["items"][0]
    assert summary["root_name"] == "invoke_agent support-agent"
    assert (summary["span_count"], summary["error_count"], summary["llm_calls"], summary["tool_calls"]) == (3, 1, 1, 1)
    # 600 uncached input * $2 + 400 cache reads * $0.20 + 100 output * $10, per million tokens
    assert Decimal(summary["cost_usd"]) == Decimal("0.00228")

    detail = (await client.get(f"/api/traces/{trace_id}")).json()
    [root] = detail["roots"]
    assert root["input_messages"][0]["parts"][0]["content"] == "Where is 48100?"
    assert [c["name"] for c in root["children"]] == ["chat claude-sonnet-5-5", "execute_tool lookup_order"]
    chat = root["children"][0]
    assert chat["price_version"] == 1 and chat["usage"]["cache_read_tokens"] == 400
    assert root["children"][1]["tool"]["arguments"] == {"order_id": "48100"}
    assert detail["rollup"]["error_count"] == 1
    assert detail["models"][0]["model"] == "claude-sonnet-5-5"

    overview = (await client.get("/api/metrics/overview", params={"range": "1h", "service": service})).json()
    assert overview["current"]["requests"] == 1 and overview["current"]["llm_calls"] == 1
    assert Decimal(overview["current"]["cost_usd"]) == Decimal("0.00228")

    tools = (await client.get("/api/metrics/tools", params={"range": "24h", "service": service})).json()
    assert tools["tools"][0]["tool_name"] == "lookup_order" and tools["tools"][0]["failures"] == 1
    assert len(tools["tools"][0]["cells"]) == len(tools["buckets"])

    series = (await client.get("/api/metrics/timeseries", params={"range": "1h", "service": service})).json()
    assert sum(p["requests"] for p in series["points"]) == 1

    sessions = (await client.get("/api/metrics/cost", params={"group_by": "session", "service": service})).json()
    assert sessions["rows"][0]["key"] == "sess-1"

    facets = (await client.get("/api/traces/facets")).json()
    assert service in facets["services"] and "lookup_order" in facets["tools"]


async def test_json_ingest_and_error_responses(client: httpx.AsyncClient, container: Container) -> None:
    service = f"json-{uuid.uuid4().hex[:8]}"
    document = json_format.MessageToDict(export_request(record_agent_trace(service)))
    for rs in document["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for s in ss["spans"]:
                for key in ("traceId", "spanId", "parentSpanId"):
                    if key in s:
                        s[key] = base64.b64decode(s[key]).hex()
    response = await client.post("/v1/traces", json=document)
    assert response.status_code == 200 and response.json() == {}
    await container.ingest.flush()
    assert len((await client.get("/api/traces", params={"service": service})).json()["items"]) == 1

    unsupported = await client.post("/v1/traces", content=b"x", headers={"content-type": "text/plain"})
    assert unsupported.status_code == 415
    assert "unsupported content type" in unsupported.json()["message"]
    malformed = await client.post("/v1/traces", content=b"\xff\x00", headers=PROTOBUF)
    assert malformed.status_code == 400
    assert Status.FromString(malformed.content).message == "malformed OTLP protobuf payload"
    missing = await client.get(f"/api/traces/{'0' * 32}")
    assert missing.status_code == 404


async def test_trace_list_paginates_with_a_stable_cursor(client: httpx.AsyncClient, container: Container) -> None:
    service = f"page-{uuid.uuid4().hex[:8]}"
    ids = {await _ingest(client, container, service, question=f"q{i}") for i in range(5)}
    seen: list[str] = []
    cursor = None
    for _ in range(5):
        params: dict[str, str | int] = {"service": service, "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (await client.get("/api/traces", params=params)).json()
        seen.extend(t["trace_id"] for t in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5 and set(seen) == ids
    bad = await client.get("/api/traces", params={"cursor": "!!notbase64"})
    assert bad.status_code == 422


async def test_new_price_version_applies_to_new_spans_only(client: httpx.AsyncClient, container: Container) -> None:
    current = (await client.get("/api/prices/current")).json()
    prices = [p for p in current["prices"] if p["model"] != "claude-sonnet-5-5"]
    prices.append(
        {
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "match": "exact",
            "input_per_mtok": "4",
            "output_per_mtok": "20",
            "cache_read_per_mtok": "0.4",
        }
    )
    old_service = f"price-old-{uuid.uuid4().hex[:6]}"
    old_trace = await _ingest(client, container, old_service)
    created = await client.post(
        "/api/prices/versions",
        json={"label": "doubled", "effective_from": datetime.now(UTC).isoformat(), "prices": prices},
    )
    assert created.status_code == 201
    versions = (await client.get("/api/prices/versions")).json()
    assert any(v["label"] == "doubled" for v in versions)

    new_service = f"price-new-{uuid.uuid4().hex[:6]}"
    new_trace = await _ingest(client, container, new_service)
    old = (await client.get(f"/api/traces/{old_trace}")).json()
    new = (await client.get(f"/api/traces/{new_trace}")).json()
    assert Decimal(new["rollup"]["cost_usd"]) == 2 * Decimal(old["rollup"]["cost_usd"])

    duplicate = await client.post(
        "/api/prices/versions",
        json={"label": "dup", "effective_from": "2020-01-01T00:00:00Z", "prices": [prices[0], prices[0]]},
    )
    assert duplicate.status_code == 422
    assert json.loads(duplicate.content)["error"]["code"] == "validation_failed"
