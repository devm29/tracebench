from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from tracebench.ingest.models import SpanRecord
from tracebench.query.messages import parse_json_or_text, parse_messages
from tracebench.query.models import EventView, ModelUsage, Rollup, SpanNode, ToolCallView

LLM_OPERATIONS = frozenset({"chat", "text_completion", "generate_content"})


def _own_rollup(span: SpanRecord) -> Rollup:
    return Rollup(
        span_count=1,
        llm_calls=int(span.operation in LLM_OPERATIONS),
        tool_calls=int(bool(span.tool_name)),
        error_count=int(span.is_error),
        input_tokens=span.usage.input_tokens,
        output_tokens=span.usage.output_tokens,
        cache_read_tokens=span.usage.cache_read_tokens,
        cost_usd=span.cost_usd,
    )


def merge_rollups(a: Rollup, b: Rollup) -> Rollup:
    return Rollup(
        span_count=a.span_count + b.span_count,
        llm_calls=a.llm_calls + b.llm_calls,
        tool_calls=a.tool_calls + b.tool_calls,
        error_count=a.error_count + b.error_count,
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_read_tokens=a.cache_read_tokens + b.cache_read_tokens,
        cost_usd=a.cost_usd + b.cost_usd,
    )


def _ms_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() * 1000.0


def _node(span: SpanRecord, depth: int, trace_start: datetime, children: list[SpanNode]) -> SpanNode:
    subtree = _own_rollup(span)
    for child in children:
        subtree = merge_rollups(subtree, child.subtree)
    tool = (
        ToolCallView(
            name=span.tool_name,
            call_id=span.tool_call_id,
            arguments=parse_json_or_text(span.tool_arguments),
            result=parse_json_or_text(span.tool_result),
        )
        if span.tool_name
        else None
    )
    return SpanNode(
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        kind=span.kind,
        service_name=span.service_name,
        start_time=span.start_time,
        end_time=span.end_time,
        offset_ms=_ms_between(trace_start, span.start_time),
        duration_ms=span.duration_ms,
        depth=depth,
        status=span.status,
        status_message=span.status_message,
        operation=span.operation,
        provider=span.provider,
        model=span.model,
        request_model=span.request_model,
        response_model=span.response_model,
        usage=span.usage,
        cost_usd=span.cost_usd,
        price_version=span.price_version,
        tool=tool,
        agent_name=span.agent_name,
        session_id=span.session_id,
        system_instructions=span.system_instructions,
        input_messages=parse_messages(span.input_messages, default_role="user"),
        output_messages=parse_messages(span.output_messages, default_role="assistant"),
        finish_reasons=span.finish_reasons,
        error_type=span.error_type,
        attributes=span.attributes,
        resource_attributes=span.resource_attributes,
        events=[
            EventView(
                name=e.name,
                timestamp=e.timestamp,
                offset_ms=_ms_between(trace_start, e.timestamp),
                attributes=e.attributes,
            )
            for e in span.events
        ],
        subtree=subtree,
        children=children,
    )


def build_tree(spans: list[SpanRecord]) -> list[SpanNode]:
    """Assembles spans into a forest ordered by start time.

    Spans whose parent never arrived (dropped by a sampler, or still in flight) are
    promoted to roots rather than hidden, so a partial trace still renders.
    """
    if not spans:
        return []
    by_id = {s.span_id: s for s in spans}
    children: dict[str, list[SpanRecord]] = defaultdict(list)
    roots: list[SpanRecord] = []
    for span in spans:
        if span.parent_span_id and span.parent_span_id in by_id and span.parent_span_id != span.span_id:
            children[span.parent_span_id].append(span)
        else:
            roots.append(span)
    trace_start = min(s.start_time for s in spans)

    def build(span: SpanRecord, depth: int, seen: frozenset[str]) -> SpanNode:
        kids = sorted(children.get(span.span_id, []), key=lambda s: (s.start_time, s.span_id))
        nested = [build(k, depth + 1, seen | {span.span_id}) for k in kids if k.span_id not in seen]
        return _node(span, depth, trace_start, nested)

    return [build(r, 0, frozenset()) for r in sorted(roots, key=lambda s: (s.start_time, s.span_id))]


def model_usage(spans: list[SpanRecord]) -> list[ModelUsage]:
    usage: dict[tuple[str, str], ModelUsage] = {}
    for span in spans:
        if not span.model or span.operation not in LLM_OPERATIONS | {"embeddings"}:
            continue
        key = (span.model, span.provider)
        current = usage.get(key) or ModelUsage(
            model=span.model,
            provider=span.provider,
            calls=0,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cost_usd=Decimal(0),
        )
        usage[key] = current.model_copy(
            update={
                "calls": current.calls + 1,
                "input_tokens": current.input_tokens + span.usage.input_tokens,
                "output_tokens": current.output_tokens + span.usage.output_tokens,
                "cache_read_tokens": current.cache_read_tokens + span.usage.cache_read_tokens,
                "cost_usd": current.cost_usd + span.cost_usd,
            }
        )
    return sorted(usage.values(), key=lambda u: u.cost_usd, reverse=True)


def flatten(nodes: list[SpanNode]) -> list[SpanNode]:
    out: list[SpanNode] = []
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(reversed(node.children))
    return out
