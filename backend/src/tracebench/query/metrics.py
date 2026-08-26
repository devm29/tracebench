from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tracebench.query.models import (
    CostBreakdown,
    CostDimension,
    HeatCell,
    ModelLatency,
    Overview,
    Timeseries,
    TimeseriesPoint,
    TimeWindow,
    ToolHeatmap,
    ToolHeatRow,
)
from tracebench.store.clickhouse.spans import ClickHouseSpanRepository

_NICE_STEPS = (60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400)


def pick_step(window: TimeWindow, *, target_points: int, minimum: int = 60) -> int:
    span = max((window.end - window.start).total_seconds(), 1)
    raw = span / target_points
    for step in _NICE_STEPS:
        if step >= raw and step >= minimum:
            return step
    return _NICE_STEPS[-1]


def bucket_starts(window: TimeWindow, step: int) -> list[datetime]:
    epoch = int(window.start.timestamp())
    first = epoch - epoch % step
    last = int(window.end.timestamp())
    return [datetime.fromtimestamp(t, tz=UTC) for t in range(first, last, step)]


class MetricsService:
    def __init__(self, spans: ClickHouseSpanRepository) -> None:
        self._spans = spans

    async def overview(self, window: TimeWindow) -> Overview:
        length = window.end - window.start
        previous = TimeWindow(start=window.start - length, end=window.start, service=window.service)
        return Overview(
            window=window,
            current=await self._spans.window_stats(window),
            previous=await self._spans.window_stats(previous),
        )

    async def timeseries(self, window: TimeWindow) -> Timeseries:
        step = pick_step(window, target_points=72)
        rows = {r["bucket"]: r for r in await self._spans.timeseries(window, step)}
        points = []
        for bucket in bucket_starts(window, step):
            row = rows.get(bucket)
            if row is None:
                points.append(
                    TimeseriesPoint(
                        bucket=bucket,
                        requests=0,
                        errors=0,
                        p50_ms=None,
                        p95_ms=None,
                        cost_usd=Decimal(0),
                        input_tokens=0,
                        output_tokens=0,
                    )
                )
            else:
                points.append(TimeseriesPoint.model_validate(row))
        return Timeseries(interval_seconds=step, points=points)

    async def models(self, window: TimeWindow) -> list[ModelLatency]:
        return await self._spans.model_latency(window)

    async def cost(self, window: TimeWindow, group_by: CostDimension, limit: int) -> CostBreakdown:
        rows = await self._spans.cost_by(window, group_by, limit)
        return CostBreakdown(
            group_by=group_by,
            total_cost_usd=sum((r.cost_usd for r in rows), Decimal(0)),
            rows=rows,
        )

    async def tool_heatmap(self, window: TimeWindow) -> ToolHeatmap:
        step = pick_step(window, target_points=28, minimum=3600)
        buckets = bucket_starts(window, step)
        index = {b: i for i, b in enumerate(buckets)}
        cells: dict[str, list[HeatCell]] = {}
        for row in await self._spans.tool_heatmap(window, step):
            position = index.get(row["bucket"])
            if position is None:
                continue
            tool_cells = cells.setdefault(row["tool_name"], [HeatCell(calls=0, failures=0) for _ in buckets])
            tool_cells[position] = HeatCell(calls=row["calls"], failures=row["failures"])
        p95 = await self._spans.tool_p95(window)
        tools = []
        for name, tool_cells in cells.items():
            calls = sum(c.calls for c in tool_cells)
            failures = sum(c.failures for c in tool_cells)
            tools.append(
                ToolHeatRow(
                    tool_name=name,
                    calls=calls,
                    failures=failures,
                    failure_rate=failures / calls if calls else 0.0,
                    p95_ms=p95.get(name, 0.0),
                    cells=tool_cells,
                )
            )
        tools.sort(key=lambda t: (t.failure_rate, t.calls), reverse=True)
        return ToolHeatmap(interval_seconds=step, buckets=buckets, tools=tools)


def default_window(hours: int = 24 * 7, service: str | None = None) -> TimeWindow:
    end = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
    return TimeWindow(start=end - timedelta(hours=hours), end=end, service=service)
