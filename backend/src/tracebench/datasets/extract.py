from typing import Any

from pydantic import JsonValue

from tracebench.errors import NotFoundError, ValidationFailedError
from tracebench.query.messages import last_text
from tracebench.query.models import ChatMessage, SpanNode, TraceDetail
from tracebench.query.tree import flatten


def _conversation(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.text} for m in messages if m.role in {"user", "assistant"} and m.text]


def _find(nodes: list[SpanNode], span_id: str) -> SpanNode:
    for node in flatten(nodes):
        if node.span_id == span_id:
            return node
    raise NotFoundError(f"span {span_id} not found in trace")


def extract_case(detail: TraceDetail, span_id: str | None = None) -> tuple[JsonValue, JsonValue | None, dict[str, Any]]:
    """Derives a replayable input and the observed output from a trace.

    Prefers the chosen span's own messages (usually the agent root). When the root did
    not record content, it falls back to the first LLM call's user turns for the input
    and the last LLM call's answer for the output, which is what the user actually saw.
    """
    node = _find(detail.roots, span_id) if span_id else detail.roots[0]
    descendants = flatten([node])
    llm_spans = [n for n in descendants if n.input_messages or n.output_messages]

    conversation = _conversation(node.input_messages)
    if not conversation:
        first = next((n for n in llm_spans if _conversation(n.input_messages)), None)
        conversation = [m for m in _conversation(first.input_messages) if m["role"] == "user"] if first else []
    if not conversation:
        raise ValidationFailedError(
            "trace has no captured input messages; enable content capture in your instrumentation"
        )

    output = last_text(node.output_messages, "assistant")
    if not output:
        output = next((last_text(n.output_messages, "assistant") for n in reversed(llm_spans)), "")

    metadata: dict[str, Any] = {
        "service": node.service_name,
        "span_name": node.name,
        "models": sorted({n.model for n in descendants if n.model}),
        "trace_status": "error" if detail.rollup.error_count else "ok",
    }
    payload: JsonValue = {"messages": [{"role": m["role"], "content": m["content"]} for m in conversation]}
    return payload, output or None, metadata
