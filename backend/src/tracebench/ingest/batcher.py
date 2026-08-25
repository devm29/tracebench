import asyncio
import contextlib
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from tracebench.errors import BackpressureError
from tracebench.ingest.models import SpanRecord
from tracebench.logging import get_logger

log = get_logger(__name__)


class SpanSink(Protocol):
    async def insert_spans(self, spans: Sequence[SpanRecord]) -> None: ...


class BatcherStats(BaseModel):
    pending: int
    flushed_spans: int
    flushed_batches: int
    failed_attempts: int
    dropped_spans: int


@dataclass(slots=True)
class _Counters:
    flushed_spans: int = 0
    flushed_batches: int = 0
    failed_attempts: int = 0
    dropped_spans: int = 0


class SpanBatcher:
    """Coalesces many small OTLP exports into large ClickHouse inserts.

    ClickHouse prefers few large inserts over many small ones (each insert creates a
    part that has to be merged), so spans are buffered and flushed when either the
    batch fills up or the flush interval elapses. When the buffer is full, submit()
    raises BackpressureError, which the API turns into a retryable 503 that OTLP
    exporters already know how to back off from.
    """

    def __init__(
        self,
        sink: SpanSink,
        *,
        max_batch_size: int,
        flush_interval: float,
        max_pending: int,
        max_attempts: int = 3,
        retry_backoff: float = 0.2,
    ) -> None:
        self._sink = sink
        self._max_batch_size = max_batch_size
        self._flush_interval = flush_interval
        self._max_pending = max_pending
        self._max_attempts = max_attempts
        self._retry_backoff = retry_backoff
        self._buffer: deque[SpanRecord] = deque()
        self._flush_lock = asyncio.Lock()
        self._wakeup = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._counters = _Counters()

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def stats(self) -> BatcherStats:
        return BatcherStats(
            pending=self.pending,
            flushed_spans=self._counters.flushed_spans,
            flushed_batches=self._counters.flushed_batches,
            failed_attempts=self._counters.failed_attempts,
            dropped_spans=self._counters.dropped_spans,
        )

    async def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="span-batcher")

    async def stop(self) -> None:
        """Drains the buffer. The loop is asked to exit rather than cancelled, so an
        in-flight insert completes instead of losing a batch that was already acknowledged."""
        if self._task is not None:
            self._stopping.set()
            self._wakeup.set()
            await self._task
            self._task = None
        await self.flush()
        if self._buffer:
            self._counters.dropped_spans += len(self._buffer)
            log.error("spans could not be persisted before shutdown", dropped=len(self._buffer))
            self._buffer.clear()

    def submit(self, spans: Sequence[SpanRecord]) -> None:
        if not spans:
            return
        if len(self._buffer) + len(spans) > self._max_pending:
            raise BackpressureError("ingest buffer is full, retry shortly", retry_after_seconds=2)
        self._buffer.extend(spans)
        if len(self._buffer) >= self._max_batch_size:
            self._wakeup.set()

    async def flush(self) -> int:
        flushed = 0
        async with self._flush_lock:
            while self._buffer:
                batch = [self._buffer.popleft() for _ in range(min(self._max_batch_size, len(self._buffer)))]
                try:
                    inserted = await self._insert_with_retry(batch)
                except asyncio.CancelledError:
                    # Put the batch back so a later flush can persist it. ClickHouse may have
                    # committed it already, so this is at-least-once; trace reads dedupe by span_id.
                    self._buffer.extendleft(reversed(batch))
                    raise
                if not inserted:
                    break
                flushed += len(batch)
        return flushed

    async def _insert_with_retry(self, batch: list[SpanRecord]) -> bool:
        for attempt in range(1, self._max_attempts + 1):
            try:
                await self._sink.insert_spans(batch)
            except Exception as exc:
                self._counters.failed_attempts += 1
                log.warning("span insert failed", attempt=attempt, size=len(batch), error=str(exc))
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._retry_backoff * 2 ** (attempt - 1))
                continue
            self._counters.flushed_spans += len(batch)
            self._counters.flushed_batches += 1
            return True
        room = self._max_pending - len(self._buffer)
        if room >= len(batch):
            self._buffer.extendleft(reversed(batch))
        else:
            self._counters.dropped_spans += len(batch)
            log.error("dropping spans after repeated insert failures", dropped=len(batch))
        return False

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wakeup.wait(), timeout=self._flush_interval)
            self._wakeup.clear()
            try:
                await self.flush()
            except Exception:
                log.exception("unexpected flush failure")
