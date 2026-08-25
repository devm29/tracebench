import asyncio
import contextlib
from datetime import UTC, datetime

from tracebench.logging import get_logger
from tracebench.pricing.book import PriceBook
from tracebench.pricing.defaults import DEFAULT_PRICES
from tracebench.pricing.models import PriceVersion, PriceVersionCreate, PriceVersionSummary
from tracebench.store.postgres.prices import PriceRepository

log = get_logger(__name__)


class PriceService:
    """Owns the in-memory PriceBook used on the ingest hot path.

    The book is rebuilt from Postgres on a timer and immediately after a new version is
    created, so ingest never waits on a database round trip to price a span.
    """

    def __init__(self, repository: PriceRepository, *, refresh_seconds: float) -> None:
        self._repository = repository
        self._refresh_seconds = refresh_seconds
        self._book = PriceBook([])
        self._task: asyncio.Task[None] | None = None

    @property
    def book(self) -> PriceBook:
        return self._book

    async def start(self) -> None:
        if not await self._repository.all_versions():
            await self._repository.create(DEFAULT_PRICES)
            log.info("seeded default price table")
        await self.refresh()
        self._task = asyncio.create_task(self._refresh_loop(), name="price-refresh")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def refresh(self) -> None:
        self._book = PriceBook(await self._repository.all_versions())

    async def versions(self) -> list[PriceVersionSummary]:
        return await self._repository.summaries()

    async def version(self, version_id: int) -> PriceVersion | None:
        return await self._repository.get(version_id)

    def current(self) -> PriceVersion | None:
        return self._book.version_at(datetime.now(UTC))

    async def create_version(self, payload: PriceVersionCreate) -> PriceVersion:
        created = await self._repository.create(payload)
        await self.refresh()
        return created

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._refresh_seconds)
            try:
                await self.refresh()
            except Exception:
                log.exception("price table refresh failed; keeping the previous book")
