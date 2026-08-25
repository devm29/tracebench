import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from tracebench.config import Settings
from tracebench.store.clickhouse.schema import backfill_statements, statements


async def _connect(settings: Settings, database: str | None) -> AsyncClient:
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password.get_secret_value(),
        database=database or "default",
        secure=settings.clickhouse_secure,
    )


async def ensure_schema(settings: Settings) -> None:
    client = await _connect(settings, None)
    try:
        for statement in statements(settings.clickhouse_database, settings.span_ttl_days):
            await client.command(statement)
        for statement in backfill_statements(settings.clickhouse_database):
            await client.command(statement)
    finally:
        await client.close()


__all__ = ["AsyncClient", "connect", "ensure_schema"]


async def connect(settings: Settings) -> AsyncClient:
    return await _connect(settings, settings.clickhouse_database)
