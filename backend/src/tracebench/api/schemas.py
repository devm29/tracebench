from pydantic import BaseModel

from tracebench.ingest.batcher import BatcherStats


class Health(BaseModel):
    status: str
    version: str
    clickhouse: bool
    postgres: bool
    ingest: BatcherStats
    price_version: int | None
