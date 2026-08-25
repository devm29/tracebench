import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from tracebench.ingest.models import SpanEvent, SpanKind, SpanRecord, SpanStatus, TokenUsage
from tracebench.query.models import (
    CostDimension,
    CostRow,
    Facets,
    ModelLatency,
    TimeWindow,
    TraceFilter,
    TraceSummary,
    WindowStats,
)
from tracebench.store.clickhouse.client import AsyncClient

SPAN_COLUMNS: Final = (
    "trace_id", "span_id", "parent_span_id", "service_name", "name", "kind",
    "start_time", "end_time", "duration_ms", "status_code", "status_message",
    "operation", "provider", "request_model", "response_model",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
    "cost_usd", "price_version", "tool_name", "tool_call_id", "tool_arguments", "tool_result",
    "agent_name", "session_id", "input_messages", "output_messages", "system_instructions",
    "finish_reasons", "error_type", "attributes", "resource_attributes", "events",
)  # fmt: skip

LLM_OPERATIONS: Final = ("chat", "text_completion", "generate_content")

_INSERT_SETTINGS: Final = {"async_insert": 1, "wait_for_async_insert": 1}

_SERVICE_PREDICATE: Final = "({service:String} = '' OR service_name = {service:String})"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _naive(value: datetime) -> datetime:
    return _utc(value).replace(tzinfo=None)


def span_to_row(span: SpanRecord) -> list[Any]:
    events = [{"name": e.name, "timestamp": e.timestamp.isoformat(), "attributes": e.attributes} for e in span.events]
    return [
        span.trace_id, span.span_id, span.parent_span_id or "", span.service_name, span.name,
        span.kind.value, _utc(span.start_time), _utc(span.end_time), span.duration_ms,
        span.status.value, span.status_message, span.operation, span.provider,
        span.request_model, span.response_model, span.usage.input_tokens, span.usage.output_tokens,
        span.usage.cache_read_tokens, span.usage.cache_write_tokens, span.cost_usd, span.price_version,
        span.tool_name, span.tool_call_id, span.tool_arguments, span.tool_result, span.agent_name,
        span.session_id, span.input_messages, span.output_messages, span.system_instructions,
        span.finish_reasons, span.error_type, span.attributes, span.resource_attributes,
        json.dumps(events, default=str) if events else "",
    ]  # fmt: skip


def row_to_span(row: dict[str, Any]) -> SpanRecord:
    raw_events = json.loads(row["events"]) if row["events"] else []
    return SpanRecord(
        trace_id=row["trace_id"],
        span_id=row["span_id"],
        parent_span_id=row["parent_span_id"] or None,
        service_name=row["service_name"],
        name=row["name"],
        kind=SpanKind(row["kind"]),
        start_time=_utc(row["start_time"]),
        end_time=_utc(row["end_time"]),
        status=SpanStatus(row["status_code"]),
        status_message=row["status_message"],
        operation=row["operation"],
        provider=row["provider"],
        request_model=row["request_model"],
        response_model=row["response_model"],
        usage=TokenUsage(
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cache_write_tokens=row["cache_write_tokens"],
        ),
        cost_usd=row["cost_usd"],
        price_version=row["price_version"],
        tool_name=row["tool_name"],
        tool_call_id=row["tool_call_id"],
        tool_arguments=row["tool_arguments"],
        tool_result=row["tool_result"],
        agent_name=row["agent_name"],
        session_id=row["session_id"],
        input_messages=row["input_messages"],
        output_messages=row["output_messages"],
        system_instructions=row["system_instructions"],
        finish_reasons=list(row["finish_reasons"]),
        error_type=row["error_type"],
        attributes=dict(row["attributes"]),
        resource_attributes=dict(row["resource_attributes"]),
        events=[SpanEvent.model_validate(e) for e in raw_events],
    )


def _summary(row: dict[str, Any]) -> TraceSummary:
    start, end = _utc(row["start_time"]), _utc(row["end_time"])
    return TraceSummary(
        trace_id=row["trace_id"],
        root_name=row["root_name"],
        service_name=row["root_service"] or (row["services"][0] if row["services"] else ""),
        session_id=row["session_id"],
        start_time=start,
        end_time=end,
        duration_ms=max((end - start).total_seconds() * 1000, 0.0),
        span_count=row["span_count"],
        error_count=row["error_count"],
        root_error=bool(row["root_error"]),
        llm_calls=row["llm_calls"],
        tool_calls=row["tool_calls"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost_usd=row["cost_usd"],
        services=sorted(row["services"]),
        models=sorted(row["models"]),
    )


def _quantile(values: Sequence[float] | None, index: int) -> float:
    if not values or len(values) <= index:
        return 0.0
    value = float(values[index])
    return 0.0 if value != value else value


_SUMMARY_SELECT: Final = """
    SELECT
        trace_id,
        min(start_time) AS start_time,
        max(end_time) AS end_time,
        max(root_name) AS root_name,
        max(root_service) AS root_service,
        max(session_id) AS session_id,
        sum(span_count) AS span_count,
        sum(error_count) AS error_count,
        max(root_error) AS root_error,
        sum(llm_calls) AS llm_calls,
        sum(tool_calls) AS tool_calls,
        sum(input_tokens) AS input_tokens,
        sum(output_tokens) AS output_tokens,
        sum(cost_usd) AS cost_usd,
        groupUniqArrayArray(services) AS services,
        groupUniqArrayArray(models) AS models
    FROM trace_summaries
"""


class ClickHouseSpanRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def insert_spans(self, spans: Sequence[SpanRecord]) -> None:
        if not spans:
            return
        await self._client.insert(
            "spans",
            [span_to_row(s) for s in spans],
            column_names=list(SPAN_COLUMNS),
            settings=_INSERT_SETTINGS,
        )

    async def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._client.query(sql, parameters=params)
        return list(result.named_results())

    async def list_traces(
        self, flt: TraceFilter, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[TraceSummary]:
        having = ["1"]
        index = []
        params: dict[str, Any] = {"limit": limit}
        if flt.start is not None:
            having.append("start_time >= {start:DateTime64(9, 'UTC')}")
            index.append("start_hour >= toStartOfHour({start:DateTime64(9, 'UTC')})")
            params["start"] = _naive(flt.start)
        if flt.end is not None:
            having.append("start_time < {end:DateTime64(9, 'UTC')}")
            index.append("start_hour < {end:DateTime64(9, 'UTC')}")
            params["end"] = _naive(flt.end)
        if flt.service:
            having.append("has(services, {service:String})")
            params["service"] = flt.service
        if flt.model:
            having.append("has(models, {model:String})")
            params["model"] = flt.model
        if flt.status == "error":
            having.append("error_count > 0")
        elif flt.status == "ok":
            having.append("error_count = 0")
        if flt.session_id:
            having.append("session_id = {session_id:String}")
            params["session_id"] = flt.session_id
        if flt.q:
            having.append(
                "(startsWith(trace_id, lower({q:String})) OR positionCaseInsensitive(root_name, {q:String}) > 0)"
            )
            params["q"] = flt.q
        if cursor is not None:
            having.append("(start_time, trace_id) < ({cursor_ts:DateTime64(9, 'UTC')}, {cursor_id:String})")
            index.append("start_hour <= {cursor_ts:DateTime64(9, 'UTC')}")
            params["cursor_ts"] = _naive(cursor[0])
            params["cursor_id"] = cursor[1]
        # trace_summaries is keyed by trace_id, so without a prefilter every page would group the
        # whole table. trace_index is sorted by hour and narrows it to the window first.
        where = f"WHERE trace_id IN (SELECT trace_id FROM trace_index WHERE {' AND '.join(index)})" if index else ""
        sql = (
            f"{_SUMMARY_SELECT} {where} GROUP BY trace_id HAVING {' AND '.join(having)} "
            "ORDER BY start_time DESC, trace_id DESC LIMIT {limit:UInt32}"
        )
        return [_summary(r) for r in await self._rows(sql, params)]

    async def get_summary(self, trace_id: str) -> TraceSummary | None:
        sql = f"{_SUMMARY_SELECT} WHERE trace_id = {{trace_id:String}} GROUP BY trace_id"
        rows = await self._rows(sql, {"trace_id": trace_id})
        return _summary(rows[0]) if rows else None

    async def get_spans(self, trace_id: str, start: datetime, end: datetime) -> list[SpanRecord]:
        sql = f"""
            SELECT {", ".join(SPAN_COLUMNS)} FROM spans
            WHERE trace_id = {{trace_id:String}}
              AND start_time BETWEEN {{lo:DateTime64(9, 'UTC')}} AND {{hi:DateTime64(9, 'UTC')}}
            ORDER BY start_time, span_id
            LIMIT 1 BY span_id
        """
        rows = await self._rows(sql, {"trace_id": trace_id, "lo": _naive(start), "hi": _naive(end)})
        return [row_to_span(r) for r in rows]

    async def window_stats(self, window: TimeWindow) -> WindowStats:
        sql = f"""
            SELECT
                sumIf(span_count, is_root = 1) AS requests,
                sumIf(error_count, is_root = 1) AS errors,
                quantilesTDigestMergeIf(0.5, 0.95, 0.99)(duration_digest, is_root = 1) AS q,
                sumIf(span_count, operation IN {LLM_OPERATIONS}) AS llm_calls,
                sum(input_tokens) AS input_tokens,
                sum(output_tokens) AS output_tokens,
                sum(cost_usd) AS cost_usd
            FROM span_rollup_1m
            WHERE bucket >= {{start:DateTime('UTC')}} AND bucket < {{end:DateTime('UTC')}} AND {_SERVICE_PREDICATE}
        """
        rows = await self._rows(sql, self._window_params(window))
        row = rows[0]
        requests = int(row["requests"])
        errors = int(row["errors"])
        return WindowStats(
            requests=requests,
            errors=errors,
            error_rate=errors / requests if requests else 0.0,
            p50_ms=_quantile(row["q"], 0),
            p95_ms=_quantile(row["q"], 1),
            p99_ms=_quantile(row["q"], 2),
            llm_calls=int(row["llm_calls"]),
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
            cost_usd=Decimal(row["cost_usd"]),
        )

    async def timeseries(self, window: TimeWindow, step_seconds: int) -> list[dict[str, Any]]:
        sql = f"""
            SELECT
                toStartOfInterval(bucket, toIntervalSecond({{step:UInt32}})) AS ts,
                sumIf(span_count, is_root = 1) AS requests,
                sumIf(error_count, is_root = 1) AS errors,
                quantilesTDigestMergeIf(0.5, 0.95)(duration_digest, is_root = 1) AS q,
                sum(cost_usd) AS cost_usd,
                sum(input_tokens) AS input_tokens,
                sum(output_tokens) AS output_tokens
            FROM span_rollup_1m
            WHERE bucket >= {{start:DateTime('UTC')}} AND bucket < {{end:DateTime('UTC')}} AND {_SERVICE_PREDICATE}
            GROUP BY ts ORDER BY ts
        """
        rows = await self._rows(sql, {**self._window_params(window), "step": step_seconds})
        return [
            {
                "bucket": _utc(r["ts"]),
                "requests": int(r["requests"]),
                "errors": int(r["errors"]),
                "p50_ms": _quantile(r["q"], 0) if r["requests"] else None,
                "p95_ms": _quantile(r["q"], 1) if r["requests"] else None,
                "cost_usd": Decimal(r["cost_usd"]),
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
            }
            for r in rows
        ]

    async def model_latency(self, window: TimeWindow) -> list[ModelLatency]:
        sql = f"""
            SELECT
                model,
                sum(span_count) AS calls,
                sum(error_count) AS errors,
                quantilesTDigestMerge(0.5, 0.95)(duration_digest) AS q,
                sum(input_tokens) AS input_tokens,
                sum(output_tokens) AS output_tokens,
                sum(cost_usd) AS cost_usd
            FROM span_rollup_1m
            WHERE bucket >= {{start:DateTime('UTC')}} AND bucket < {{end:DateTime('UTC')}} AND {_SERVICE_PREDICATE}
              AND operation IN {LLM_OPERATIONS} AND model != ''
            GROUP BY model ORDER BY calls DESC
        """
        rows = await self._rows(sql, self._window_params(window))
        return [
            ModelLatency(
                model=r["model"],
                calls=int(r["calls"]),
                errors=int(r["errors"]),
                p50_ms=_quantile(r["q"], 0),
                p95_ms=_quantile(r["q"], 1),
                input_tokens=int(r["input_tokens"]),
                output_tokens=int(r["output_tokens"]),
                cost_usd=Decimal(r["cost_usd"]),
            )
            for r in rows
        ]

    async def cost_by(self, window: TimeWindow, dimension: CostDimension, limit: int) -> list[CostRow]:
        params = {**self._window_params(window), "limit": limit}
        if dimension == "session":
            # Sessions are high cardinality, so this reads raw spans. The time window prunes
            # whole daily partitions; within them it is a scan of the window.
            sql = f"""
                SELECT session_id AS key, uniqExact(trace_id) AS calls,
                       sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
                       sum(cost_usd) AS cost_usd
                FROM spans
                WHERE start_time >= {{start:DateTime('UTC')}} AND start_time < {{end:DateTime('UTC')}}
                  AND session_id != '' AND {_SERVICE_PREDICATE}
                GROUP BY key ORDER BY cost_usd DESC LIMIT {{limit:UInt32}}
            """
        else:
            column = "service_name" if dimension == "service" else "model"
            calls = "sumIf(span_count, is_root = 1)" if dimension == "service" else "sum(span_count)"
            sql = f"""
                SELECT {column} AS key, {calls} AS calls,
                       sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
                       sum(cost_usd) AS cost_usd
                FROM span_rollup_1m
                WHERE bucket >= {{start:DateTime('UTC')}} AND bucket < {{end:DateTime('UTC')}}
                  AND {_SERVICE_PREDICATE} AND key != ''
                  {"AND operation IN " + str(LLM_OPERATIONS) if dimension == "model" else ""}
                GROUP BY key ORDER BY cost_usd DESC LIMIT {{limit:UInt32}}
            """
        rows = await self._rows(sql, params)
        total = sum((Decimal(r["cost_usd"]) for r in rows), Decimal(0))
        return [
            CostRow(
                key=r["key"],
                calls=int(r["calls"]),
                input_tokens=int(r["input_tokens"]),
                output_tokens=int(r["output_tokens"]),
                cost_usd=Decimal(r["cost_usd"]),
                share=float(Decimal(r["cost_usd"]) / total) if total else 0.0,
            )
            for r in rows
        ]

    async def tool_heatmap(self, window: TimeWindow, step_seconds: int) -> list[dict[str, Any]]:
        sql = f"""
            SELECT
                tool_name,
                toStartOfInterval(bucket, toIntervalSecond({{step:UInt32}})) AS ts,
                sum(calls) AS calls,
                sum(failures) AS failures,
                quantilesTDigestMerge(0.5, 0.95)(duration_digest) AS q
            FROM tool_rollup_1h
            WHERE bucket >= {{start:DateTime('UTC')}} AND bucket < {{end:DateTime('UTC')}} AND {_SERVICE_PREDICATE}
            GROUP BY tool_name, ts
            ORDER BY tool_name, ts
        """
        rows = await self._rows(sql, {**self._window_params(window), "step": step_seconds})
        return [
            {
                "tool_name": r["tool_name"],
                "bucket": _utc(r["ts"]),
                "calls": int(r["calls"]),
                "failures": int(r["failures"]),
                "p95_ms": _quantile(r["q"], 1),
            }
            for r in rows
        ]

    async def tool_p95(self, window: TimeWindow) -> dict[str, float]:
        sql = f"""
            SELECT tool_name, quantilesTDigestMerge(0.5, 0.95)(duration_digest) AS q
            FROM tool_rollup_1h
            WHERE bucket >= {{start:DateTime('UTC')}} AND bucket < {{end:DateTime('UTC')}} AND {_SERVICE_PREDICATE}
            GROUP BY tool_name
        """
        rows = await self._rows(sql, self._window_params(window))
        return {r["tool_name"]: _quantile(r["q"], 1) for r in rows}

    async def facets(self, since: datetime) -> Facets:
        sql = """
            SELECT
                groupUniqArray(toString(service_name)) AS services,
                groupUniqArrayIf(toString(model), model != '') AS models,
                groupUniqArrayIf(toString(operation), operation != '') AS operations
            FROM span_rollup_1m WHERE bucket >= {since:DateTime('UTC')}
        """
        rows = await self._rows(sql, {"since": _naive(since)})
        tools = await self._rows(
            "SELECT DISTINCT toString(tool_name) AS tool_name FROM tool_rollup_1h "
            "WHERE bucket >= {since:DateTime('UTC')}",
            {"since": _naive(since)},
        )
        row = rows[0] if rows else {"services": [], "models": [], "operations": []}
        return Facets(
            services=sorted(row["services"]),
            models=sorted(row["models"]),
            operations=sorted(row["operations"]),
            tools=sorted(t["tool_name"] for t in tools),
        )

    @staticmethod
    def _window_params(window: TimeWindow) -> dict[str, Any]:
        return {"start": _naive(window.start), "end": _naive(window.end), "service": window.service or ""}
