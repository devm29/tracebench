import json
from typing import Any

import pytest

from tests.factories import T0, span
from tracebench.datasets.extract import extract_case
from tracebench.errors import NotFoundError, ValidationFailedError
from tracebench.ingest.models import SpanRecord
from tracebench.query.models import TraceDetail
from tracebench.query.tree import build_tree, model_usage

ROOT, CHAT_1, TOOL, CHAT_2 = (f"{i:016x}" for i in range(1, 5))


def messages(*turns: tuple[str, str]) -> str:
    return json.dumps([{"role": role, "parts": [{"type": "text", "content": text}]} for role, text in turns])


def detail(spans: list[SpanRecord]) -> TraceDetail:
    roots = build_tree(spans)
    return TraceDetail(
        trace_id="a" * 32,
        root_name=roots[0].name,
        service_name="svc",
        session_id="",
        start_time=T0,
        end_time=T0,
        duration_ms=0,
        services=["svc"],
        rollup=roots[0].subtree,
        models=model_usage(spans),
        roots=roots,
    )


def agent_trace(*, root_messages: bool) -> TraceDetail:
    root_fields: dict[str, Any] = (
        {
            "input_messages": messages(("system", "be nice"), ("user", "Where is my order?")),
            "output_messages": messages(("assistant", "It shipped.")),
        }
        if root_messages
        else {}
    )
    return detail(
        [
            span(ROOT, None, duration_ms=1000, name="invoke_agent", **root_fields),
            span(
                CHAT_1,
                ROOT,
                offset_ms=10,
                operation="chat",
                request_model="claude-haiku-4-5",
                input_messages=messages(("user", "Where is my order?"), ("assistant", "draft")),
                output_messages=messages(("assistant", "Let me check.")),
            ),
            span(TOOL, ROOT, offset_ms=100, operation="execute_tool", tool_name="lookup"),
            span(
                CHAT_2,
                ROOT,
                offset_ms=200,
                operation="chat",
                request_model="claude-sonnet-5-5",
                output_messages=messages(("assistant", "Order 48100 shipped Monday.")),
            ),
        ]
    )


def test_prefers_the_root_spans_own_conversation() -> None:
    case_input, output, metadata = extract_case(agent_trace(root_messages=True))
    assert case_input == {"messages": [{"role": "user", "content": "Where is my order?"}]}
    assert output == "It shipped."
    assert metadata["models"] == ["claude-haiku-4-5", "claude-sonnet-5-5"]
    assert metadata["trace_status"] == "ok"


def test_falls_back_to_first_llm_input_and_last_llm_output() -> None:
    case_input, output, _ = extract_case(agent_trace(root_messages=False))
    assert case_input == {"messages": [{"role": "user", "content": "Where is my order?"}]}
    assert output == "Order 48100 shipped Monday."


def test_a_chosen_span_scopes_the_extraction() -> None:
    _, output, metadata = extract_case(agent_trace(root_messages=False), CHAT_1)
    assert output == "Let me check."
    assert metadata["models"] == ["claude-haiku-4-5"]


def test_traces_without_content_or_unknown_spans_are_rejected() -> None:
    bare = detail([span(ROOT, None)])
    with pytest.raises(ValidationFailedError):
        extract_case(bare)
    with pytest.raises(NotFoundError):
        extract_case(agent_trace(root_messages=True), "f" * 16)


def test_missing_output_is_reported_as_none() -> None:
    no_output = detail([span(ROOT, None, input_messages=messages(("user", "hi")))])
    assert extract_case(no_output)[1] is None
