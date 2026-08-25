import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...

    async def sleep_ms(self, ms: float) -> None: ...


class RealClock:
    """Wall clock. Simulated latencies are scaled down so mock-backed demos stay snappy."""

    def __init__(self, latency_scale: float = 1.0) -> None:
        self._scale = latency_scale

    def now_ns(self) -> int:
        return time.time_ns()

    async def sleep_ms(self, ms: float) -> None:
        if self._scale > 0:
            await asyncio.sleep(ms * self._scale / 1000)


class VirtualClock:
    """Deterministic clock for backfilling historical traffic: sleeping just advances time."""

    def __init__(self, start_ns: int) -> None:
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    async def sleep_ms(self, ms: float) -> None:
        self._now += int(ms * 1_000_000)
