import asyncio
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.factories import export_request, record_agent_trace
from tests.integration.targets import target_app
from tracebench.cli.client import TracebenchClient
from tracebench.cli.regression import RegressionRequest, RegressionSetupError, run_regression
from tracebench.container import Container
from tracebench.evals.embeddings import HashingEmbedder
from tracebench.evals.judges import OfflineJudge
from tracebench.evals.models import ExactMatchSpec, RunStatus
from tracebench.evals.scorers.factory import ScorerFactory
from tracebench.store.postgres.engine import create_session_factory
from tracebench.store.postgres.evals import EvalRepository


async def _promote(client: httpx.AsyncClient, container: Container, dataset: str, question: str) -> dict[str, Any]:
    request = export_request(record_agent_trace(f"golden-{uuid.uuid4().hex[:6]}", question=question))
    await client.post(
        "/v1/traces", content=request.SerializeToString(), headers={"content-type": "application/x-protobuf"}
    )
    await container.ingest.flush()
    trace_id = request.resource_spans[0].scope_spans[0].spans[0].trace_id.hex()
    response = await client.post(f"/api/traces/{trace_id}/promote", json={"dataset_name": dataset})
    assert response.status_code == 201, response.text
    item: dict[str, Any] = response.json()
    assert (await client.post(f"/api/traces/{trace_id}/promote", json={"dataset_name": dataset})).status_code == 409
    return item


async def test_promote_and_versioned_edits(client: httpx.AsyncClient, container: Container) -> None:
    name = f"golden-{uuid.uuid4().hex[:8]}"
    item = await _promote(client, container, name, "Where is order 48137?")
    assert item["input"] == {"messages": [{"role": "user", "content": "Where is order 48137?"}]}
    assert item["expected_output"] == "It shipped yesterday."
    assert item["metadata"]["models"] == ["claude-sonnet-5-5"]
    dataset_id, key = item["dataset_id"], item["item_key"]

    edited = await client.patch(
        f"/api/datasets/{dataset_id}/items/{key}", json={"expected_output": "It shipped on Monday via UPS."}
    )
    assert edited.status_code == 200 and edited.json()["revision"] == 2

    latest = (await client.get(f"/api/datasets/{dataset_id}/items")).json()
    assert latest["version"] == 2 and latest["items"][0]["expected_output"] == "It shipped on Monday via UPS."
    original = (await client.get(f"/api/datasets/{dataset_id}/items", params={"version": 1})).json()
    assert original["items"][0]["expected_output"] == "It shipped yesterday."

    cleared = await client.patch(f"/api/datasets/{dataset_id}/items/{key}", json={"expected_output": None})
    assert cleared.json()["expected_output"] is None

    assert (await client.delete(f"/api/datasets/{dataset_id}/items/{key}")).status_code == 204
    after_delete = (await client.get(f"/api/datasets/{dataset_id}/items")).json()
    assert after_delete["version"] == 4 and after_delete["items"] == []
    assert len((await client.get(f"/api/datasets/{dataset_id}/items", params={"version": 3})).json()["items"]) == 1
    assert (await client.get(f"/api/datasets/{dataset_id}/items", params={"version": 9})).status_code == 404

    datasets = (await client.get("/api/datasets")).json()
    assert any(d["name"] == name and d["item_count"] == 0 for d in datasets)
    assert (await client.post("/api/datasets", json={"name": name})).status_code == 409
    assert (await client.post("/api/datasets", json={"name": "Bad Name"})).status_code == 422


async def test_regression_gate_against_baseline(client: httpx.AsyncClient, container: Container) -> None:
    name = f"gate-{uuid.uuid4().hex[:8]}"
    created = await client.post("/api/datasets", json={"name": name, "default_scorers": [{"type": "exact_match"}]})
    dataset_id = created.json()["id"]
    await client.post(
        f"/api/datasets/{dataset_id}/items",
        json=[
            {"input": {"messages": [{"role": "user", "content": q}]}, "expected_output": f"answer to {q}"}
            for q in ("refund 48100", "status 48137", "shipping times")
        ],
    )
    factory = ScorerFactory(HashingEmbedder(), OfflineJudge())
    api = TracebenchClient(client)

    async def run(target: FastAPI, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=target), base_url="http://target") as http:
            return await run_regression(
                RegressionRequest(dataset=name, target_url="http://target/invoke", scorers=[], **kwargs),
                api,
                http,
                factory,
            )

    baseline = await run(target_app(), set_baseline="if-passed", name="main")
    assert baseline.gate.passed and baseline.promoted_to_baseline and baseline.diff is None
    assert baseline.run.summary.pass_rate == 1.0
    assert baseline.run.scorers == [ExactMatchSpec()]

    candidate = await run(target_app(broken_for="refund"), set_baseline="if-passed", name="pr")
    assert not candidate.gate.passed and not candidate.promoted_to_baseline
    assert candidate.diff is not None and candidate.diff.counts["regressed"] == 1
    assert candidate.baseline is not None and candidate.baseline.id == baseline.run.id

    compare = (
        await client.get("/api/eval-runs/compare", params={"base": str(baseline.run.id), "head": str(candidate.run.id)})
    ).json()
    assert compare["items"][0]["status"] == "regressed"
    assert compare["items"][0]["head_output"] == "I don't know."

    current = (await client.get("/api/eval-runs/baseline", params={"dataset_id": dataset_id})).json()
    assert current["id"] == str(baseline.run.id)
    promoted = await client.post(f"/api/eval-runs/{candidate.run.id}/baseline")
    assert promoted.json()["is_baseline"] is True
    runs = (await client.get("/api/eval-runs", params={"dataset_id": dataset_id})).json()
    assert [r["is_baseline"] for r in runs].count(True) == 1

    results = (await client.get(f"/api/eval-runs/{candidate.run.id}/results")).json()
    assert len(results) == 3 and sum(r["passed"] for r in results) == 2

    with pytest.raises(RegressionSetupError):
        await run_regression(
            RegressionRequest(dataset="does-not-exist", target_url="http://target/invoke", scorers=[]),
            api,
            client,
            factory,
        )


async def _wait_for(client: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    for _ in range(100):
        run: dict[str, Any] = (await client.get(f"/api/eval-runs/{run_id}")).json()
        if run["status"] in {"completed", "failed"}:
            return run
        await asyncio.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish")


async def test_server_side_execution(client: httpx.AsyncClient) -> None:
    name = f"exec-{uuid.uuid4().hex[:8]}"
    dataset_id = (await client.post("/api/datasets", json={"name": name})).json()["id"]
    await client.post(
        f"/api/datasets/{dataset_id}/items",
        json=[
            {"input": {"messages": [{"role": "user", "content": "hello"}]}, "expected_output": "answer to hello"},
            {"input": {"messages": [{"role": "user", "content": "no reference"}]}},
        ],
    )
    accepted = await client.post(
        "/api/eval-runs/execute",
        json={"dataset_id": dataset_id, "target_url": "http://target/invoke", "scorers": [{"type": "exact_match"}]},
    )
    assert accepted.status_code == 202 and accepted.json()["status"] == "pending"
    run = await _wait_for(client, accepted.json()["id"])
    assert run["status"] == "completed"
    # The item without an expected output cannot be scored, so it must not count as a pass.
    assert run["summary"]["passed"] == 1 and run["summary"]["errored"] == 1
    results = (await client.get(f"/api/eval-runs/{run['id']}/results")).json()
    unscored = next(r for r in results if r["expected_output"] is None)
    assert not unscored["passed"] and unscored["error"].startswith("unscored")


@pytest.mark.parametrize(
    "target_url",
    [
        "http://127.0.0.1:27105/?query=SELECT%201",
        "http://localhost:5505/",
        "http://169.254.169.254/latest/meta-data/",
        "http://internal.example/invoke",
        "file:///etc/passwd",
    ],
)
async def test_server_side_execution_rejects_targets_outside_the_allowlist(
    client: httpx.AsyncClient, target_url: str
) -> None:
    name = f"ssrf-{uuid.uuid4().hex[:8]}"
    dataset_id = (await client.post("/api/datasets", json={"name": name})).json()["id"]
    await client.post(f"/api/datasets/{dataset_id}/items", json=[{"input": "x", "expected_output": "y"}])
    response = await client.post("/api/eval-runs/execute", json={"dataset_id": dataset_id, "target_url": target_url})
    assert response.status_code == 422, response.text
    runs = (await client.get("/api/eval-runs", params={"dataset_id": dataset_id})).json()
    assert runs == []


async def test_concurrent_baseline_flips_leave_exactly_one_baseline(client: httpx.AsyncClient) -> None:
    name = f"race-{uuid.uuid4().hex[:8]}"
    dataset_id = (await client.post("/api/datasets", json={"name": name})).json()["id"]
    await client.post(f"/api/datasets/{dataset_id}/items", json=[{"input": "q", "expected_output": "a"}])
    record = {
        "dataset_id": dataset_id,
        "dataset_version": 1,
        "target_url": "http://target/invoke",
        "scorers": [],
        "results": [],
        "started_at": "2026-10-01T00:00:00Z",
        "finished_at": "2026-10-01T00:00:01Z",
    }
    run_ids = [(await client.post("/api/eval-runs", json=record)).json()["id"] for _ in range(4)]
    responses = await asyncio.gather(*(client.post(f"/api/eval-runs/{r}/baseline") for r in run_ids))
    assert all(r.status_code in {200, 409} for r in responses)
    runs = (await client.get("/api/eval-runs", params={"dataset_id": dataset_id})).json()
    assert [r["is_baseline"] for r in runs].count(True) == 1


async def test_concurrent_promotes_of_one_trace_create_one_item(
    client: httpx.AsyncClient, container: Container
) -> None:
    request = export_request(record_agent_trace(f"race-{uuid.uuid4().hex[:6]}", question="Where is order 1?"))
    await client.post(
        "/v1/traces", content=request.SerializeToString(), headers={"content-type": "application/x-protobuf"}
    )
    await container.ingest.flush()
    trace_id = request.resource_spans[0].scope_spans[0].spans[0].trace_id.hex()
    name = f"race-{uuid.uuid4().hex[:8]}"
    responses = await asyncio.gather(
        *(client.post(f"/api/traces/{trace_id}/promote", json={"dataset_name": name}) for _ in range(5))
    )
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409]
    dataset = (await client.get(f"/api/datasets/by-name/{name}")).json()
    assert dataset["item_count"] == 1


async def test_item_batches_are_capped(client: httpx.AsyncClient) -> None:
    dataset_id = (await client.post("/api/datasets", json={"name": f"cap-{uuid.uuid4().hex[:8]}"})).json()["id"]
    too_many = [{"input": i} for i in range(1001)]
    assert (await client.post(f"/api/datasets/{dataset_id}/items", json=too_many)).status_code == 422
    created = await client.post(f"/api/datasets/{dataset_id}/items", json=too_many[:1000])
    assert created.status_code == 201 and len(created.json()) == 1000


async def test_runs_orphaned_by_a_crash_are_failed_on_startup(client: httpx.AsyncClient, container: Container) -> None:
    dataset_id = (await client.post("/api/datasets", json={"name": f"crash-{uuid.uuid4().hex[:8]}"})).json()["id"]
    await client.post(f"/api/datasets/{dataset_id}/items", json=[{"input": "q", "expected_output": "a"}])
    record = {
        "dataset_id": dataset_id,
        "target_url": "http://target/invoke",
        "scorers": [],
        "results": [],
        "dataset_version": 1,
        "started_at": "2026-10-01T00:00:00Z",
        "finished_at": "2026-10-01T00:00:01Z",
    }
    done = (await client.post("/api/eval-runs", json=record)).json()
    repository = EvalRepository(create_session_factory(container.engine))
    orphan_id = await repository.create_run(
        dataset_id=uuid.UUID(dataset_id),
        dataset_version=1,
        target_url="http://target/invoke",
        scorers=[],
        status=RunStatus.RUNNING,
        name=None,
        git_sha=None,
        git_ref=None,
    )
    await container.evals.recover()
    failed = (await client.get(f"/api/eval-runs/{orphan_id}")).json()
    assert failed["status"] == "failed" and failed["error"].startswith("interrupted")
    assert (await client.get(f"/api/eval-runs/{done['id']}")).json()["status"] == "completed"
