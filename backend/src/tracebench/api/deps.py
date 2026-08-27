from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Query, Request

from tracebench.container import Container
from tracebench.datasets.service import DatasetService
from tracebench.errors import ValidationFailedError
from tracebench.evals.service import EvalService
from tracebench.ingest.service import IngestService
from tracebench.pricing.service import PriceService
from tracebench.query.metrics import MetricsService
from tracebench.query.models import TimeWindow
from tracebench.query.traces import TraceService

RANGE_HOURS = {"1h": 1, "6h": 6, "24h": 24, "7d": 24 * 7, "30d": 24 * 30}
RANGE_PATTERN = r"^(1h|6h|24h|7d|30d)$"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def _ingest(c: ContainerDep) -> IngestService:
    return c.ingest


def _traces(c: ContainerDep) -> TraceService:
    return c.traces


def _metrics(c: ContainerDep) -> MetricsService:
    return c.metrics


def _datasets(c: ContainerDep) -> DatasetService:
    return c.datasets


def _evals(c: ContainerDep) -> EvalService:
    return c.evals


def _prices(c: ContainerDep) -> PriceService:
    return c.prices


IngestDep = Annotated[IngestService, Depends(_ingest)]
TracesDep = Annotated[TraceService, Depends(_traces)]
MetricsDep = Annotated[MetricsService, Depends(_metrics)]
DatasetsDep = Annotated[DatasetService, Depends(_datasets)]
EvalsDep = Annotated[EvalService, Depends(_evals)]
PricesDep = Annotated[PriceService, Depends(_prices)]


def time_window(
    range_: Annotated[str | None, Query(alias="range", pattern=RANGE_PATTERN)] = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    service: Annotated[str | None, Query(max_length=200)] = None,
) -> TimeWindow:
    now = datetime.now(UTC)
    if end is not None and start is None:
        raise ValidationFailedError("'to' requires 'from'; use 'range' for windows ending now")
    if start is not None:
        start_utc = start if start.tzinfo else start.replace(tzinfo=UTC)
        end_utc = (end if end.tzinfo else end.replace(tzinfo=UTC)) if end is not None else now
        if end_utc <= start_utc:
            raise ValidationFailedError("'to' must be after 'from'")
        if end_utc - start_utc > timedelta(days=90):
            raise ValidationFailedError("time range may not exceed 90 days")
        return TimeWindow(start=start_utc, end=end_utc, service=service or None)
    hours = RANGE_HOURS[range_ or "7d"]
    # Round up to the next minute so the newest rollup bucket is included and responses cache well.
    end_rounded = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return TimeWindow(start=end_rounded - timedelta(hours=hours), end=end_rounded, service=service or None)


WindowDep = Annotated[TimeWindow, Depends(time_window)]
