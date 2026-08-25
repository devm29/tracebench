import asyncio
from collections.abc import Sequence

import pytest

from tests.factories import span
from tracebench.errors import BackpressureError
from tracebench.ingest.batcher import SpanBatcher
from tracebench.ingest.models import SpanRecord


class RecordingSink:
    def __init__(self, failures: int = 0) -> None:
        self.batches: list[list[SpanRecord]] = []
        self.failures = failures

    async def insert_spans(self, spans: Sequence[SpanRecord]) -> None:
        if self.failures:
            self.failures -= 1
            raise ConnectionError("clickhouse unavailable")
        self.batches.append(list(spans))


def _spans(n: int) -> list[SpanRecord]:
    return [span(f"{i:016x}") for i in range(1, n + 1)]


async def test_flush_splits_into_max_sized_batches() -> None:
    sink = RecordingSink()
    batcher = SpanBatcher(sink, max_batch_size=4, flush_interval=60, max_pending=100)
    batcher.submit(_spans(10))
    assert await batcher.flush() == 10
    assert [len(b) for b in sink.batches] == [4, 4, 2]
    assert batcher.stats().flushed_batches == 3


async def test_background_loop_flushes_on_interval() -> None:
    sink = RecordingSink()
    batcher = SpanBatcher(sink, max_batch_size=1000, flush_interval=0.05, max_pending=100)
    await batcher.start()
    batcher.submit(_spans(3))
    await asyncio.sleep(0.2)
    await batcher.stop()
    assert sum(len(b) for b in sink.batches) == 3


async def test_full_batch_wakes_the_flusher_early() -> None:
    sink = RecordingSink()
    batcher = SpanBatcher(sink, max_batch_size=5, flush_interval=30, max_pending=100)
    await batcher.start()
    batcher.submit(_spans(5))
    await asyncio.sleep(0.05)
    assert sink.batches
    await batcher.stop()


async def test_backpressure_when_buffer_is_full() -> None:
    batcher = SpanBatcher(RecordingSink(), max_batch_size=10, flush_interval=60, max_pending=5)
    batcher.submit(_spans(4))
    with pytest.raises(BackpressureError) as excinfo:
        batcher.submit(_spans(2))
    assert excinfo.value.retry_after_seconds > 0
    assert batcher.pending == 4


async def test_transient_insert_failures_are_retried() -> None:
    sink = RecordingSink(failures=2)
    batcher = SpanBatcher(sink, max_batch_size=10, flush_interval=60, max_pending=100, retry_backoff=0)
    batcher.submit(_spans(3))
    assert await batcher.flush() == 3
    assert batcher.stats().failed_attempts == 2


async def test_persistent_failure_requeues_spans_for_a_later_flush() -> None:
    sink = RecordingSink(failures=3)
    batcher = SpanBatcher(sink, max_batch_size=10, flush_interval=60, max_pending=100, max_attempts=3, retry_backoff=0)
    batcher.submit(_spans(3))
    assert await batcher.flush() == 0
    assert batcher.pending == 3
    assert await batcher.flush() == 3
    assert batcher.stats().dropped_spans == 0


class SlowSink:
    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.persisted: list[SpanRecord] = []

    async def insert_spans(self, spans: Sequence[SpanRecord]) -> None:
        await asyncio.sleep(self.delay)
        self.persisted.extend(spans)


async def test_stop_waits_for_the_in_flight_batch_and_drains_the_rest() -> None:
    sink = SlowSink(delay=0.1)
    batcher = SpanBatcher(sink, max_batch_size=10, flush_interval=0.01, max_pending=100)
    await batcher.start()
    batcher.submit(_spans(10))
    await asyncio.sleep(0.03)
    batcher.submit([span(f"{i:016x}") for i in range(100, 115)])
    await batcher.stop()
    assert len(sink.persisted) == 25
    assert batcher.pending == 0 and batcher.stats().dropped_spans == 0


async def test_cancelled_flush_puts_the_batch_back() -> None:
    sink = SlowSink(delay=10)
    batcher = SpanBatcher(sink, max_batch_size=10, flush_interval=60, max_pending=100)
    batcher.submit(_spans(4))
    task = asyncio.create_task(batcher.flush())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert batcher.pending == 4


async def test_spans_left_after_a_failed_final_flush_are_counted_as_dropped() -> None:
    sink = RecordingSink(failures=100)
    batcher = SpanBatcher(sink, max_batch_size=10, flush_interval=60, max_pending=100, retry_backoff=0)
    await batcher.start()
    batcher.submit(_spans(3))
    await batcher.stop()
    assert batcher.pending == 0 and batcher.stats().dropped_spans == 3
