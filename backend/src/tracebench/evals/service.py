import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx

from tracebench.datasets.models import DatasetItem
from tracebench.errors import NotFoundError, ValidationFailedError
from tracebench.evals.diff import diff_runs
from tracebench.evals.models import (
    CaseResult,
    EvalCase,
    EvalRun,
    EvalRunExecute,
    EvalRunRecord,
    RecordedGate,
    RunDiff,
    RunStatus,
    ScorerSpec,
)
from tracebench.evals.runner import EvalRunner, summarize
from tracebench.evals.scorers.factory import DEFAULT_SCORERS, ScorerFactory
from tracebench.evals.target import TargetClient
from tracebench.evals.target_policy import TargetPolicy
from tracebench.logging import get_logger
from tracebench.store.postgres.datasets import DatasetRepository
from tracebench.store.postgres.evals import EvalRepository

log = get_logger(__name__)

INTERRUPTED = "interrupted: the API stopped before the run finished"


def cases_from_items(items: list[DatasetItem]) -> list[EvalCase]:
    return [
        EvalCase(item_key=i.item_key, item_id=i.id, input=i.input, expected_output=i.expected_output) for i in items
    ]


class EvalService:
    def __init__(
        self,
        evals: EvalRepository,
        datasets: DatasetRepository,
        scorers: ScorerFactory,
        http: httpx.AsyncClient,
        policy: TargetPolicy,
        *,
        concurrency: int,
        target_timeout: float,
    ) -> None:
        self._evals = evals
        self._datasets = datasets
        self._scorers = scorers
        self._http = http
        self._policy = policy
        self._concurrency = concurrency
        self._target_timeout = target_timeout
        self._tasks: set[asyncio.Task[None]] = set()

    async def recover(self) -> None:
        """Runs execute in-process, so any run still pending or running at startup was orphaned by a crash."""
        orphaned = await self._evals.fail_unfinished(INTERRUPTED, datetime.now(UTC))
        if orphaned:
            log.warning("marked orphaned eval runs as failed", runs=orphaned)

    async def list_runs(self, *, dataset_id: UUID | None, limit: int, offset: int) -> list[EvalRun]:
        return await self._evals.list_runs(dataset_id=dataset_id, limit=limit, offset=offset)

    async def get_run(self, run_id: UUID) -> EvalRun:
        return await self._evals.get_run(run_id)

    async def results(self, run_id: UUID) -> list[CaseResult]:
        await self._evals.get_run(run_id)
        return await self._evals.results(run_id)

    async def baseline(self, dataset_id: UUID) -> EvalRun:
        run = await self._evals.baseline(dataset_id)
        if run is None:
            raise NotFoundError(f"dataset {dataset_id} has no baseline run")
        return run

    async def set_baseline(self, run_id: UUID) -> EvalRun:
        run = await self._evals.get_run(run_id)
        if run.status is not RunStatus.COMPLETED:
            raise ValidationFailedError("only completed runs can become the baseline")
        return await self._evals.set_baseline(run_id)

    async def set_gate(self, run_id: UUID, gate: RecordedGate) -> EvalRun:
        run = await self._evals.get_run(run_id)
        if run.status is not RunStatus.COMPLETED:
            raise ValidationFailedError("a gate verdict can only be attached to a completed run")
        return await self._evals.set_gate(run_id, gate)

    async def record(self, payload: EvalRunRecord) -> EvalRun:
        dataset = await self._datasets.get(payload.dataset_id)
        if payload.dataset_version > dataset.version:
            raise ValidationFailedError(f"dataset {dataset.name} has no version {payload.dataset_version}")
        run_id = await self._evals.create_run(
            dataset_id=payload.dataset_id,
            dataset_version=payload.dataset_version,
            target_url=payload.target_url,
            scorers=payload.scorers,
            status=RunStatus.RUNNING,
            name=payload.name,
            git_sha=payload.git_sha,
            git_ref=payload.git_ref,
            started_at=payload.started_at,
            embedder=payload.embedder,
        )
        await self._evals.complete_run(
            run_id,
            results=payload.results,
            summary=summarize(payload.results),
            finished_at=payload.finished_at,
        )
        return await self._evals.get_run(run_id)

    async def execute(self, payload: EvalRunExecute) -> EvalRun:
        target_url = self._policy.check(str(payload.target_url))
        dataset = await self._datasets.get(payload.dataset_id)
        version, items = await self._datasets.items(dataset.id, payload.dataset_version)
        if not items:
            raise ValidationFailedError(f"dataset {dataset.name} has no items at version {version}")
        specs: list[ScorerSpec] = list(payload.scorers or dataset.default_scorers or DEFAULT_SCORERS)
        scorers = self._scorers.build_all(specs)
        run_id = await self._evals.create_run(
            dataset_id=dataset.id,
            dataset_version=version,
            target_url=target_url,
            scorers=specs,
            status=RunStatus.PENDING,
            name=payload.name,
            git_sha=payload.git_sha,
            git_ref=payload.git_ref,
        )
        runner = EvalRunner(
            TargetClient(target_url, self._http, timeout=self._target_timeout, include_error_body=False),
            scorers,
            concurrency=self._concurrency,
        )
        task = asyncio.create_task(self._execute(run_id, runner, cases_from_items(items), specs), name=f"eval-{run_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return await self._evals.get_run(run_id)

    async def _execute(self, run_id: UUID, runner: EvalRunner, cases: list[EvalCase], specs: list[ScorerSpec]) -> None:
        started = datetime.now(UTC)
        try:
            await self._evals.mark_running(run_id, started)
            results = await runner.run(cases)
            await self._evals.complete_run(
                run_id,
                results=results,
                summary=summarize(results),
                finished_at=datetime.now(UTC),
                embedder=self._scorers.embedder_used(specs),
            )
            log.info("eval run completed", run_id=str(run_id), cases=len(results))
        except asyncio.CancelledError:
            await self._evals.fail_run(run_id, INTERRUPTED, datetime.now(UTC))
            raise
        except Exception as exc:
            log.exception("eval run failed", run_id=str(run_id))
            await self._evals.fail_run(run_id, f"run failed: {type(exc).__name__}", datetime.now(UTC))

    async def compare(self, base_id: UUID, head_id: UUID) -> RunDiff:
        base, head = await self._evals.get_run(base_id), await self._evals.get_run(head_id)
        if base.dataset_id != head.dataset_id:
            raise ValidationFailedError("runs belong to different datasets")
        return diff_runs(base, await self._evals.results(base_id), head, await self._evals.results(head_id))

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
