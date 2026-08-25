import asyncio
import os
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from tests.integration.targets import target_app
from tracebench.config import EmbeddingsBackend, JudgeBackend, Settings
from tracebench.container import Container
from tracebench.main import create_app
from tracebench.store.clickhouse import client as clickhouse

BACKEND = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def settings() -> Settings:
    database_url = os.environ.get(
        "TRACEBENCH_TEST_DATABASE_URL", "postgresql+asyncpg://tracebench@127.0.0.1:5505/tracebench_test"
    )
    configured = Settings(
        env="test",
        log_level="WARNING",
        database_url=database_url,
        clickhouse_host=os.environ.get("TRACEBENCH_TEST_CLICKHOUSE_HOST", "127.0.0.1"),
        clickhouse_port=int(os.environ.get("TRACEBENCH_TEST_CLICKHOUSE_PORT", "27105")),
        clickhouse_database="tracebench_test",
        embeddings_backend=EmbeddingsBackend.HASH,
        judge_backend=JudgeBackend.OFFLINE,
        ingest_flush_interval_seconds=0.2,
        eval_target_allowlist=["target"],
    )
    pg = urlparse(database_url.replace("+asyncpg", ""))
    if not _reachable(pg.hostname or "127.0.0.1", pg.port or 5432) or not _reachable(
        configured.clickhouse_host, configured.clickhouse_port
    ):
        pytest.skip("integration tests need Postgres and ClickHouse (run `make services`)")
    return configured


async def _reset(settings: Settings) -> None:
    ch = await clickhouse.connect(settings.model_copy(update={"clickhouse_database": "default"}))
    try:
        await ch.command(f"DROP DATABASE IF EXISTS {settings.clickhouse_database} SYNC")
    finally:
        await ch.close()
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["database_url"] = settings.database_url
    config.attributes["configure_logger"] = False
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    await _reset(settings)
    # Server-side eval runs call this in-process stand-in for the application under test.
    eval_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=target_app()))
    application = create_app(settings, eval_http=eval_http)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def container(app: FastAPI) -> Container:
    found: Container = app.state.container
    return found


@pytest_asyncio.fixture(loop_scope="session")
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tracebench") as http:
        yield http
