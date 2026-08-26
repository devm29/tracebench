from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from tracebench.query.metrics import MetricsService, bucket_starts, pick_step
from tracebench.query.models import TimeWindow, WindowStats
from tracebench.store.clickhouse.spans import ClickHouseSpanRepository

END = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def window(hours: float) -> TimeWindow:
    return TimeWindow(start=END - timedelta(hours=hours), end=END, service=None)


def test_pick_step_chooses_the_smallest_nice_step_that_fits() -> None:
    assert pick_step(window(1), target_points=72) == 60
    assert pick_step(window(24), target_points=72) == 1800
    assert pick_step(window(24 * 7), target_points=72) == 10800
    assert pick_step(window(1), target_points=28, minimum=3600) == 3600
    assert pick_step(window(24 * 365), target_points=10) == 86400


def test_bucket_starts_are_aligned_and_cover_the_window() -> None:
    w = TimeWindow(start=END - timedelta(minutes=125), end=END, service=None)
    buckets = bucket_starts(w, 3600)
    assert buckets[0] == datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
    assert buckets[-1] == datetime(2026, 10, 4, 11, 0, tzinfo=UTC)
    assert all(b.minute == 0 for b in buckets)


class FakeSpans:
    def __init__(self) -> None:
        self.windows: list[TimeWindow] = []

    async def window_stats(self, w: TimeWindow) -> WindowStats:
        self.windows.append(w)
        return WindowStats(
            requests=10,
            errors=1,
            error_rate=0.1,
            p50_ms=100,
            p95_ms=200,
            p99_ms=300,
            llm_calls=20,
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal("0.5"),
        )

    async def timeseries(self, w: TimeWindow, step: int) -> list[dict[str, Any]]:
        return [
            {
                "bucket": END - timedelta(minutes=30),
                "requests": 3,
                "errors": 0,
                "p50_ms": 10.0,
                "p95_ms": 20.0,
                "cost_usd": Decimal("0.1"),
                "input_tokens": 5,
                "output_tokens": 5,
            }
        ]

    async def tool_heatmap(self, w: TimeWindow, step: int) -> list[dict[str, Any]]:
        return [
            {"tool_name": "lookup", "bucket": END - timedelta(hours=2), "calls": 10, "failures": 0, "p95_ms": 1.0},
            {"tool_name": "refund", "bucket": END - timedelta(hours=1), "calls": 4, "failures": 2, "p95_ms": 1.0},
            {"tool_name": "refund", "bucket": END - timedelta(days=30), "calls": 99, "failures": 99, "p95_ms": 1.0},
        ]

    async def tool_p95(self, w: TimeWindow) -> dict[str, float]:
        return {"lookup": 12.5}


def service(fake: FakeSpans) -> MetricsService:
    return MetricsService(cast("ClickHouseSpanRepository", fake))


async def test_overview_compares_with_the_preceding_window_of_equal_length() -> None:
    fake = FakeSpans()
    await service(fake).overview(window(6))
    current, previous = fake.windows
    assert previous.end == current.start
    assert previous.end - previous.start == current.end - current.start


async def test_timeseries_fills_empty_buckets_with_zeros() -> None:
    series = await service(FakeSpans()).timeseries(window(1))
    assert series.interval_seconds == 60
    assert len(series.points) == 60
    filled = [p for p in series.points if p.requests]
    assert len(filled) == 1 and filled[0].bucket == END - timedelta(minutes=30)
    assert all(p.p95_ms is None for p in series.points if not p.requests)


async def test_tool_heatmap_ranks_by_failure_rate_and_ignores_out_of_window_rows() -> None:
    heatmap = await service(FakeSpans()).tool_heatmap(window(24))
    assert [t.tool_name for t in heatmap.tools] == ["refund", "lookup"]
    refund = heatmap.tools[0]
    assert (refund.calls, refund.failures, refund.failure_rate) == (4, 2, 0.5)
    assert len(refund.cells) == len(heatmap.buckets)
    assert heatmap.tools[1].p95_ms == 12.5 and refund.p95_ms == 0.0
