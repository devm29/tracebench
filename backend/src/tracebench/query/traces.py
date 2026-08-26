import base64
import binascii
import re
from datetime import UTC, datetime, timedelta
from functools import reduce

from tracebench.errors import NotFoundError, ValidationFailedError
from tracebench.query.models import Facets, Page, TraceDetail, TraceFilter, TraceSummary
from tracebench.query.tree import build_tree, merge_rollups, model_usage
from tracebench.store.clickhouse.spans import ClickHouseSpanRepository

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
# Children can legitimately start a little before the summary bounds because of clock skew
# between services, so the span fetch window is padded.
_SKEW = timedelta(seconds=30)


def encode_cursor(summary: TraceSummary) -> str:
    raw = f"{summary.start_time.isoformat()}|{summary.trace_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        ts, trace_id = base64.urlsafe_b64decode(padded).decode().split("|", 1)
        return datetime.fromisoformat(ts).astimezone(UTC), trace_id
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationFailedError("invalid pagination cursor") from exc


class TraceService:
    def __init__(self, spans: ClickHouseSpanRepository) -> None:
        self._spans = spans

    async def list_traces(self, flt: TraceFilter, *, limit: int, cursor: str | None) -> Page[TraceSummary]:
        decoded = decode_cursor(cursor) if cursor else None
        rows = await self._spans.list_traces(flt, limit=limit + 1, cursor=decoded)
        has_more = len(rows) > limit
        items = rows[:limit]
        return Page[TraceSummary](
            items=items,
            next_cursor=encode_cursor(items[-1]) if has_more and items else None,
        )

    async def get_trace(self, trace_id: str) -> TraceDetail:
        trace_id = trace_id.lower()
        if not _TRACE_ID.match(trace_id):
            raise ValidationFailedError("trace_id must be 32 lowercase hex characters")
        summary = await self._spans.get_summary(trace_id)
        if summary is None:
            raise NotFoundError(f"trace {trace_id} not found")
        spans = await self._spans.get_spans(trace_id, summary.start_time - _SKEW, summary.end_time + _SKEW)
        if not spans:
            raise NotFoundError(f"trace {trace_id} not found")
        roots = build_tree(spans)
        rollup = reduce(merge_rollups, (r.subtree for r in roots[1:]), roots[0].subtree)
        start = min(s.start_time for s in spans)
        end = max(s.end_time for s in spans)
        return TraceDetail(
            trace_id=trace_id,
            root_name=roots[0].name,
            service_name=roots[0].service_name,
            session_id=next((s.session_id for s in spans if s.session_id), ""),
            start_time=start,
            end_time=end,
            duration_ms=(end - start).total_seconds() * 1000,
            services=sorted({s.service_name for s in spans}),
            rollup=rollup,
            models=model_usage(spans),
            roots=roots,
        )

    async def facets(self, *, days: int = 30) -> Facets:
        return await self._spans.facets(datetime.now(UTC) - timedelta(days=days))
