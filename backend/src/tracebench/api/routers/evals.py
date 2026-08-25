from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from tracebench.api.auth import require_api_token
from tracebench.api.deps import EvalsDep
from tracebench.evals.models import CaseResult, EvalRun, EvalRunExecute, EvalRunRecord, RecordedGate, RunDiff

router = APIRouter(prefix="/api/eval-runs", tags=["evals"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[EvalRun])
async def list_runs(
    evals: EvalsDep,
    dataset_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EvalRun]:
    return await evals.list_runs(dataset_id=dataset_id, limit=limit, offset=offset)


@router.post("", response_model=EvalRun, status_code=status.HTTP_201_CREATED)
async def record_run(payload: EvalRunRecord, evals: EvalsDep) -> EvalRun:
    return await evals.record(payload)


@router.post(
    "/execute",
    response_model=EvalRun,
    status_code=status.HTTP_202_ACCEPTED,
    description=(
        "Runs the dataset from the API process. The target must be allowed by TRACEBENCH_EVAL_TARGET_ALLOWLIST "
        "(loopback only in development); redirects are not followed and error bodies are not stored."
    ),
)
async def execute_run(payload: EvalRunExecute, evals: EvalsDep) -> EvalRun:
    return await evals.execute(payload)


@router.get("/compare", response_model=RunDiff)
async def compare(base: UUID, head: UUID, evals: EvalsDep) -> RunDiff:
    return await evals.compare(base, head)


@router.get("/baseline", response_model=EvalRun)
async def baseline(dataset_id: UUID, evals: EvalsDep) -> EvalRun:
    return await evals.baseline(dataset_id)


@router.get("/{run_id}", response_model=EvalRun)
async def get_run(run_id: UUID, evals: EvalsDep) -> EvalRun:
    return await evals.get_run(run_id)


@router.get("/{run_id}/results", response_model=list[CaseResult])
async def results(run_id: UUID, evals: EvalsDep) -> list[CaseResult]:
    return await evals.results(run_id)


@router.post("/{run_id}/baseline", response_model=EvalRun)
async def set_baseline(run_id: UUID, evals: EvalsDep) -> EvalRun:
    return await evals.set_baseline(run_id)


@router.put("/{run_id}/gate", response_model=EvalRun)
async def set_gate(run_id: UUID, gate: RecordedGate, evals: EvalsDep) -> EvalRun:
    return await evals.set_gate(run_id, gate)
