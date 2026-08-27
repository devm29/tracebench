from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status

from tracebench.api.auth import require_api_token
from tracebench.api.deps import RANGE_HOURS, RANGE_PATTERN, DatasetsDep, TracesDep
from tracebench.datasets.models import DatasetItem, PromoteRequest
from tracebench.query.models import Facets, Page, TraceDetail, TraceFilter, TraceSummary

router = APIRouter(prefix="/api/traces", tags=["traces"], dependencies=[Depends(require_api_token)])

TraceId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{32}$")]


@router.get("", response_model=Page[TraceSummary])
async def list_traces(
    traces: TracesDep,
    range_: Annotated[
        str, Query(alias="range", pattern=RANGE_PATTERN, description="Lookback used when 'from' is not given.")
    ] = "24h",
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    service: Annotated[str | None, Query(max_length=200)] = None,
    model: Annotated[str | None, Query(max_length=200)] = None,
    status_: Annotated[Literal["ok", "error"] | None, Query(alias="status")] = None,
    session_id: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[TraceSummary]:
    if start is None:
        start = (end or datetime.now(UTC)) - timedelta(hours=RANGE_HOURS[range_])
    flt = TraceFilter(
        start=start, end=end, service=service, model=model, status=status_, session_id=session_id, q=q or None
    )
    return await traces.list_traces(flt, limit=limit, cursor=cursor)


@router.get("/facets", response_model=Facets)
async def facets(traces: TracesDep, days: Annotated[int, Query(ge=1, le=90)] = 30) -> Facets:
    return await traces.facets(days=days)


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: TraceId, traces: TracesDep) -> TraceDetail:
    return await traces.get_trace(trace_id)


@router.post("/{trace_id}/promote", response_model=DatasetItem, status_code=status.HTTP_201_CREATED)
async def promote(trace_id: TraceId, payload: PromoteRequest, datasets: DatasetsDep) -> DatasetItem:
    return await datasets.promote(trace_id.lower(), payload)
