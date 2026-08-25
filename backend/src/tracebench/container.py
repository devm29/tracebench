from dataclasses import dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tracebench.config import Settings
from tracebench.datasets.service import DatasetService
from tracebench.evals.embeddings import build_embedder
from tracebench.evals.judges import build_judge
from tracebench.evals.scorers.factory import ScorerFactory
from tracebench.evals.service import EvalService
from tracebench.evals.target_policy import TargetPolicy
from tracebench.ingest.batcher import SpanBatcher
from tracebench.ingest.service import IngestService
from tracebench.pricing.service import PriceService
from tracebench.query.metrics import MetricsService
from tracebench.query.traces import TraceService
from tracebench.store.clickhouse import client as clickhouse
from tracebench.store.clickhouse.client import AsyncClient
from tracebench.store.clickhouse.spans import ClickHouseSpanRepository
from tracebench.store.postgres.datasets import DatasetRepository
from tracebench.store.postgres.engine import create_engine, create_session_factory
from tracebench.store.postgres.evals import EvalRepository
from tracebench.store.postgres.prices import PriceRepository


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    clickhouse: AsyncClient
    eval_http: httpx.AsyncClient
    spans: ClickHouseSpanRepository
    batcher: SpanBatcher
    prices: PriceService
    ingest: IngestService
    traces: TraceService
    metrics: MetricsService
    datasets: DatasetService
    evals: EvalService

    @classmethod
    async def build(cls, settings: Settings, *, eval_http: httpx.AsyncClient | None = None) -> "Container":
        """`eval_http` is the client used to call eval targets; tests pass one with a mock transport."""
        await clickhouse.ensure_schema(settings)
        ch_client = await clickhouse.connect(settings)
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        # Never follow redirects: an allowed target could otherwise bounce the API anywhere.
        http = eval_http or httpx.AsyncClient(follow_redirects=False)

        spans = ClickHouseSpanRepository(ch_client)
        batcher = SpanBatcher(
            spans,
            max_batch_size=settings.ingest_max_batch_size,
            flush_interval=settings.ingest_flush_interval_seconds,
            max_pending=settings.ingest_max_pending_spans,
        )
        prices = PriceService(PriceRepository(sessions), refresh_seconds=settings.price_refresh_seconds)
        traces = TraceService(spans)
        dataset_repo = DatasetRepository(sessions)
        scorer_factory = ScorerFactory(build_embedder(settings), build_judge(settings))
        return cls(
            settings=settings,
            engine=engine,
            clickhouse=ch_client,
            eval_http=http,
            spans=spans,
            batcher=batcher,
            prices=prices,
            ingest=IngestService(batcher, prices),
            traces=traces,
            metrics=MetricsService(spans),
            datasets=DatasetService(dataset_repo, traces),
            evals=EvalService(
                EvalRepository(sessions),
                dataset_repo,
                scorer_factory,
                http,
                TargetPolicy.from_settings(settings),
                concurrency=settings.eval_concurrency,
                target_timeout=settings.eval_target_timeout_seconds,
            ),
        )

    async def start(self) -> None:
        await self.evals.recover()
        await self.prices.start()
        await self.batcher.start()

    async def close(self) -> None:
        await self.evals.shutdown()
        await self.batcher.stop()
        await self.prices.stop()
        await self.eval_http.aclose()
        await self.clickhouse.close()
        await self.engine.dispose()

    async def check_postgres(self) -> bool:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
