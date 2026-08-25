import asyncio

from pydantic import BaseModel

from tracebench.ingest.batcher import SpanBatcher
from tracebench.ingest.models import SpanRecord
from tracebench.ingest.otlp import OtlpEncoding, decode_request
from tracebench.ingest.semconv import map_resource_spans
from tracebench.pricing.book import PriceBook
from tracebench.pricing.service import PriceService


class IngestResult(BaseModel):
    accepted: int
    rejected: int
    errors: list[str]


def decode_and_map(body: bytes, encoding: OtlpEncoding, book: PriceBook) -> tuple[list[SpanRecord], IngestResult]:
    request = decode_request(body, encoding)
    mapped = map_resource_spans(request.resource_spans)
    records = [book.apply(r) for r in mapped.records]
    return records, IngestResult(accepted=len(records), rejected=mapped.rejected, errors=mapped.errors)


class IngestService:
    def __init__(self, batcher: SpanBatcher, prices: PriceService) -> None:
        self._batcher = batcher
        self._prices = prices

    async def ingest(self, body: bytes, encoding: OtlpEncoding) -> IngestResult:
        # Protobuf decoding and semconv mapping are CPU bound; keep them off the event loop.
        records, result = await asyncio.to_thread(decode_and_map, body, encoding, self._prices.book)
        self._batcher.submit(records)
        return result

    async def flush(self) -> int:
        return await self._batcher.flush()
