from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import httpx

from tracebench.cli.client import TracebenchClient
from tracebench.evals.diff import evaluate_gate
from tracebench.evals.models import (
    EvalRun,
    EvalRunRecord,
    GatePolicy,
    GateResult,
    RecordedGate,
    RunDiff,
    ScorerSpec,
)
from tracebench.evals.runner import EvalRunner, ProgressCallback
from tracebench.evals.scorers.factory import DEFAULT_SCORERS, ScorerFactory
from tracebench.evals.service import cases_from_items
from tracebench.evals.target import TargetClient

BaselineMode = Literal["auto", "none"] | UUID


class RegressionSetupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RegressionOutcome:
    run: EvalRun
    baseline: EvalRun | None
    diff: RunDiff | None
    gate: GateResult
    promoted_to_baseline: bool


@dataclass(frozen=True, slots=True)
class RegressionRequest:
    dataset: str
    target_url: str
    scorers: list[ScorerSpec]
    baseline: BaselineMode = "auto"
    policy: GatePolicy = field(default_factory=GatePolicy)
    dataset_version: int | None = None
    name: str | None = None
    git_sha: str | None = None
    git_ref: str | None = None
    set_baseline: Literal["never", "if-passed", "always"] = "never"
    concurrency: int = 8
    target_timeout: float = 60.0


async def run_regression(
    request: RegressionRequest,
    api: TracebenchClient,
    target_http: httpx.AsyncClient,
    scorer_factory: ScorerFactory,
    on_result: ProgressCallback | None = None,
) -> RegressionOutcome:
    """Replays a dataset against the target, records the run and gates it against the baseline."""
    dataset = await api.dataset_by_name(request.dataset)
    if dataset is None:
        raise RegressionSetupError(f"dataset {request.dataset!r} does not exist")
    snapshot = await api.items(dataset.id, request.dataset_version)
    if not snapshot.items:
        raise RegressionSetupError(f"dataset {dataset.name!r} has no items at version {snapshot.version}")

    specs: list[ScorerSpec] = list(request.scorers or dataset.default_scorers or DEFAULT_SCORERS)
    runner = EvalRunner(
        TargetClient(request.target_url, target_http, timeout=request.target_timeout),
        scorer_factory.build_all(specs),
        concurrency=request.concurrency,
    )
    started = datetime.now(UTC)
    results = await runner.run(cases_from_items(snapshot.items), on_result)
    run = await api.record_run(
        EvalRunRecord(
            dataset_id=dataset.id,
            dataset_version=snapshot.version,
            target_url=request.target_url,
            scorers=specs,
            results=results,
            started_at=started,
            finished_at=datetime.now(UTC),
            name=request.name,
            git_sha=request.git_sha,
            git_ref=request.git_ref,
            embedder=scorer_factory.embedder_used(specs),
        )
    )

    baseline: EvalRun | None = None
    if request.baseline == "auto":
        baseline = await api.baseline(dataset.id)
    elif isinstance(request.baseline, UUID):
        baseline = await api.run(request.baseline)
    diff = await api.compare(baseline.id, run.id) if baseline is not None else None

    assert run.summary is not None
    gate = evaluate_gate(run.summary, diff, request.policy)
    run = await api.set_gate(
        run.id,
        RecordedGate(
            passed=gate.passed,
            reasons=gate.reasons,
            policy=request.policy,
            baseline_run_id=baseline.id if baseline else None,
        ),
    )
    promote = request.set_baseline == "always" or (request.set_baseline == "if-passed" and gate.passed)
    if promote:
        run = await api.set_baseline(run.id)
    return RegressionOutcome(run=run, baseline=baseline, diff=diff, gate=gate, promoted_to_baseline=promote)
