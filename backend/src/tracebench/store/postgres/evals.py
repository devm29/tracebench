import uuid
from datetime import datetime
from typing import Any, cast

from pydantic import TypeAdapter
from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError

from tracebench.errors import ConflictError, NotFoundError
from tracebench.evals.models import (
    CaseResult,
    EvalRun,
    RecordedGate,
    RunStatus,
    RunSummary,
    ScoreResult,
    ScorerSpec,
)
from tracebench.store.postgres.engine import SessionFactory
from tracebench.store.postgres.tables import DatasetRow, EvalResultRow, EvalRunRow

_scorers = TypeAdapter(list[ScorerSpec])
_scores = TypeAdapter(list[ScoreResult])


def _run(row: EvalRunRow) -> EvalRun:
    return EvalRun(
        id=row.id,
        dataset_id=row.dataset_id,
        dataset_name=row.dataset.name,
        dataset_version=row.dataset_version,
        name=row.name,
        target_url=row.target_url,
        status=RunStatus(row.status),
        scorers=_scorers.validate_python(row.scorers),
        git_sha=row.git_sha,
        git_ref=row.git_ref,
        is_baseline=row.is_baseline,
        summary=RunSummary.model_validate(row.summary) if row.summary else None,
        error=row.error,
        embedder=row.embedder,
        gate=RecordedGate.model_validate(row.gate) if row.gate else None,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _result(row: EvalResultRow) -> CaseResult:
    return CaseResult(
        item_key=row.item_key,
        item_id=row.item_id,
        input=row.input,
        expected_output=row.expected_output,
        output=row.output,
        passed=row.passed,
        scores=_scores.validate_python(row.scores),
        latency_ms=row.latency_ms,
        error=row.error,
    )


class EvalRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def create_run(
        self,
        *,
        dataset_id: uuid.UUID,
        dataset_version: int,
        target_url: str,
        scorers: list[ScorerSpec],
        status: RunStatus,
        name: str | None,
        git_sha: str | None,
        git_ref: str | None,
        started_at: datetime | None = None,
        embedder: str | None = None,
    ) -> uuid.UUID:
        async with self._sessions() as session, session.begin():
            row = EvalRunRow(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                target_url=target_url,
                scorers=_scorers.dump_python(scorers, mode="json", by_alias=True),
                status=status.value,
                name=name,
                git_sha=git_sha,
                git_ref=git_ref,
                is_baseline=False,
                started_at=started_at,
                embedder=embedder,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def complete_run(
        self,
        run_id: uuid.UUID,
        *,
        results: list[CaseResult],
        summary: RunSummary,
        finished_at: datetime,
        started_at: datetime | None = None,
        embedder: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            row = await session.get(EvalRunRow, run_id, with_for_update=True)
            if row is None:
                raise NotFoundError(f"eval run {run_id} not found")
            session.add_all(
                EvalResultRow(
                    run_id=run_id,
                    item_key=r.item_key,
                    item_id=r.item_id,
                    input=r.input,
                    expected_output=r.expected_output,
                    output=r.output,
                    passed=r.passed,
                    scores=_scores.dump_python(r.scores, mode="json"),
                    latency_ms=r.latency_ms,
                    error=r.error,
                )
                for r in results
            )
            row.status = RunStatus.COMPLETED.value
            row.summary = summary.model_dump(mode="json")
            row.finished_at = finished_at
            if started_at is not None:
                row.started_at = started_at
            if embedder is not None:
                row.embedder = embedder

    async def mark_running(self, run_id: uuid.UUID, started_at: datetime) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(EvalRunRow)
                .where(EvalRunRow.id == run_id)
                .values(status=RunStatus.RUNNING.value, started_at=started_at)
            )

    async def fail_run(self, run_id: uuid.UUID, error: str, finished_at: datetime) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(EvalRunRow)
                .where(EvalRunRow.id == run_id)
                .values(status=RunStatus.FAILED.value, error=error[:4000], finished_at=finished_at)
            )

    async def fail_unfinished(self, error: str, finished_at: datetime) -> int:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(EvalRunRow)
                .where(EvalRunRow.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]))
                .values(status=RunStatus.FAILED.value, error=error, finished_at=finished_at)
            )
            return cast("CursorResult[Any]", result).rowcount

    async def set_gate(self, run_id: uuid.UUID, gate: RecordedGate) -> EvalRun:
        async with self._sessions() as session, session.begin():
            row = await session.get(EvalRunRow, run_id, with_for_update=True)
            if row is None:
                raise NotFoundError(f"eval run {run_id} not found")
            row.gate = gate.model_dump(mode="json")
        return await self.get_run(run_id)

    async def get_run(self, run_id: uuid.UUID) -> EvalRun:
        async with self._sessions() as session:
            row = await session.get(EvalRunRow, run_id)
            if row is None:
                raise NotFoundError(f"eval run {run_id} not found")
            return _run(row)

    async def list_runs(self, *, dataset_id: uuid.UUID | None, limit: int, offset: int) -> list[EvalRun]:
        stmt = select(EvalRunRow).order_by(EvalRunRow.created_at.desc()).limit(limit).offset(offset)
        if dataset_id is not None:
            stmt = stmt.where(EvalRunRow.dataset_id == dataset_id)
        async with self._sessions() as session:
            return [_run(r) for r in await session.scalars(stmt)]

    async def results(self, run_id: uuid.UUID) -> list[CaseResult]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(EvalResultRow).where(EvalResultRow.run_id == run_id).order_by(EvalResultRow.item_key)
            )
            return [_result(r) for r in rows]

    async def baseline(self, dataset_id: uuid.UUID) -> EvalRun | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(EvalRunRow).where(EvalRunRow.dataset_id == dataset_id, EvalRunRow.is_baseline.is_(True))
            )
            return _run(row) if row else None

    async def set_baseline(self, run_id: uuid.UUID) -> EvalRun:
        try:
            await self._flip_baseline(run_id)
        except IntegrityError as exc:
            raise ConflictError("another run became the baseline at the same time; retry") from exc
        return await self.get_run(run_id)

    async def _flip_baseline(self, run_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            dataset_id = await session.scalar(select(EvalRunRow.dataset_id).where(EvalRunRow.id == run_id))
            if dataset_id is None:
                raise NotFoundError(f"eval run {run_id} not found")
            # Serializes baseline changes per dataset; the partial unique index is the backstop.
            await session.execute(select(DatasetRow.id).where(DatasetRow.id == dataset_id).with_for_update())
            await session.execute(
                update(EvalRunRow)
                .where(
                    EvalRunRow.dataset_id == dataset_id,
                    EvalRunRow.is_baseline.is_(True),
                    EvalRunRow.id != run_id,
                )
                .values(is_baseline=False)
            )
            await session.execute(update(EvalRunRow).where(EvalRunRow.id == run_id).values(is_baseline=True))
