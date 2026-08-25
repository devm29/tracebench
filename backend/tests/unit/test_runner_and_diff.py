import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.factories import eval_run
from tracebench.cli.scorers import ScorerSpecError, parse_scorer
from tracebench.evals.diff import diff_runs, evaluate_gate
from tracebench.evals.embeddings import HashingEmbedder
from tracebench.evals.judges import OfflineJudge
from tracebench.evals.models import (
    CaseResult,
    DiffStatus,
    EmbeddingSimilaritySpec,
    EvalCase,
    EvalRun,
    ExactMatchSpec,
    GatePolicy,
    JsonSchemaSpec,
    ScoreResult,
)
from tracebench.evals.runner import EvalRunner, summarize
from tracebench.evals.scorers.factory import ScorerFactory
from tracebench.evals.target import TargetClient


def _case(question: str, expected: str) -> EvalCase:
    return EvalCase(
        item_key=uuid.uuid4(),
        item_id=uuid.uuid4(),
        input={"messages": [{"role": "user", "content": question}]},
        expected_output=expected,
    )


def _handler(request: httpx.Request) -> httpx.Response:
    question = json.loads(request.content)["messages"][-1]["content"]
    if question == "boom":
        return httpx.Response(500, text="internal error")
    if question == "slow":
        raise httpx.ReadTimeout("timed out", request=request)
    return httpx.Response(200, json={"output": question.upper(), "trace_id": "t"})


async def test_runner_scores_successes_and_records_target_errors() -> None:
    factory = ScorerFactory(HashingEmbedder(), OfflineJudge())
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
        runner = EvalRunner(
            TargetClient("http://target/invoke", http, timeout=1),
            factory.build_all([ExactMatchSpec(), EmbeddingSimilaritySpec(threshold=0.9)]),
            concurrency=2,
        )
        seen: list[CaseResult] = []
        results = await runner.run(
            [_case("hello", "HELLO"), _case("hello", "goodbye"), _case("boom", "x"), _case("slow", "x")],
            on_result=seen.append,
        )
    assert len(seen) == 4
    ok, wrong, failed, timed_out = results
    assert ok.passed and ok.output == "HELLO" and len(ok.scores) == 2
    assert not wrong.passed and wrong.error is None
    assert failed.error is not None and failed.error.startswith("HTTP 500")
    assert timed_out.error is not None and "timed out" in timed_out.error

    summary = summarize(results)
    assert (summary.total, summary.passed, summary.failed, summary.errored) == (4, 1, 1, 2)
    assert summary.pass_rate == 0.25
    assert set(summary.mean_scores) == {"exact_match", "embedding_similarity"}


def _run(pass_rate: float, **overrides: Any) -> EvalRun:
    return eval_run(pass_rate, **overrides)


def _result(key: uuid.UUID, passed: bool) -> CaseResult:
    return CaseResult(
        item_key=key,
        item_id=key,
        input="q",
        expected_output="a",
        output="a" if passed else "b",
        passed=passed,
        scores=[ScoreResult(scorer="exact_match", value=1.0 if passed else 0.0, passed=passed)],
    )


def test_diff_classifies_every_transition() -> None:
    keys = [uuid.uuid4() for _ in range(5)]
    base = [_result(keys[0], True), _result(keys[1], False), _result(keys[2], True), _result(keys[3], False)]
    head = [_result(keys[0], False), _result(keys[1], True), _result(keys[2], True), _result(keys[4], True)]
    diff = diff_runs(_run(0.5), base, _run(0.75), head)
    statuses = {i.item_key: i.status for i in diff.items}
    assert statuses == {
        keys[0]: DiffStatus.REGRESSED,
        keys[1]: DiffStatus.FIXED,
        keys[2]: DiffStatus.UNCHANGED_PASS,
        keys[3]: DiffStatus.REMOVED,
        keys[4]: DiffStatus.ADDED,
    }
    assert diff.items[0].status is DiffStatus.REGRESSED
    assert diff.pass_rate_delta == 0.25
    regressed = diff.items[0]
    assert regressed.score_deltas[0].delta == -1.0


def test_gate_policies() -> None:
    key = uuid.uuid4()
    diff = diff_runs(_run(1.0), [_result(key, True)], _run(0.5), [_result(key, False)])
    head_summary = _run(0.5).summary
    assert head_summary is not None
    assert not evaluate_gate(head_summary, diff, GatePolicy()).passed
    assert evaluate_gate(head_summary, diff, GatePolicy(fail_on_regression=False)).passed
    dropped = evaluate_gate(head_summary, diff, GatePolicy(fail_on_regression=False, max_pass_rate_drop=0.1))
    assert not dropped.passed and "dropped" in dropped.reasons[0]
    floor = evaluate_gate(head_summary, None, GatePolicy(min_pass_rate=0.9))
    assert not floor.passed and "below" in floor.reasons[0]
    assert evaluate_gate(head_summary, None, GatePolicy()).passed


def test_cli_scorer_shorthands(tmp_path: Path) -> None:
    assert isinstance(parse_scorer("exact_match"), ExactMatchSpec)
    spec = parse_scorer("embedding_similarity:0.7")
    assert isinstance(spec, EmbeddingSimilaritySpec) and spec.threshold == 0.7
    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"type": "object"}')
    assert isinstance(parse_scorer(f"json_schema:@{schema_file}"), JsonSchemaSpec)
    for bad in ("nope", "llm_judge:abc", "json_schema:inline", "embedding_similarity:2"):
        with pytest.raises(ScorerSpecError):
            parse_scorer(bad)


async def test_cases_no_scorer_applies_to_are_unscored_not_passed() -> None:
    factory = ScorerFactory(HashingEmbedder(), OfflineJudge())
    no_reference = EvalCase(item_key=uuid.uuid4(), item_id=uuid.uuid4(), input={"messages": []}, expected_output=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http:
        runner = EvalRunner(
            TargetClient("http://target/invoke", http, timeout=1), factory.build_all([ExactMatchSpec()])
        )
        no_reference = no_reference.model_copy(update={"input": {"messages": [{"role": "user", "content": "hi"}]}})
        [result] = await runner.run([no_reference])
    assert not result.passed and result.scores == []
    assert result.error is not None and result.error.startswith("unscored")
    assert summarize([result]).pass_rate == 0.0


def test_diff_warns_when_runs_used_different_embedders() -> None:
    base = _run(1.0, embedder="fastembed:BAAI/bge-small-en-v1.5")
    head = _run(1.0, embedder="hash-512", dataset_version=2)
    warnings = diff_runs(base, [], head, []).warnings
    assert len(warnings) == 2 and "not comparable" in warnings[0]
    assert diff_runs(base, [], _run(1.0, embedder=base.embedder), []).warnings == []
