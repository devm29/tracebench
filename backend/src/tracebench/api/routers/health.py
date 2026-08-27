from fastapi import APIRouter

from tracebench import __version__
from tracebench.api.deps import ContainerDep
from tracebench.api.schemas import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
async def health(container: ContainerDep) -> Health:
    try:
        clickhouse_ok = await container.spans.ping()
    except Exception:
        clickhouse_ok = False
    try:
        postgres_ok = await container.check_postgres()
    except Exception:
        postgres_ok = False
    current = container.prices.current()
    return Health(
        status="ok" if clickhouse_ok and postgres_ok else "degraded",
        version=__version__,
        clickhouse=clickhouse_ok,
        postgres=postgres_ok,
        ingest=container.batcher.stats(),
        price_version=current.id if current else None,
    )
