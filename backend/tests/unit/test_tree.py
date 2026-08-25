from decimal import Decimal

from tests.factories import span, usage
from tracebench.ingest.models import SpanStatus
from tracebench.query.messages import last_text, parse_messages
from tracebench.query.tree import build_tree, flatten, model_usage


def test_builds_nested_tree_with_offsets_and_subtree_rollups() -> None:
    spans = [
        span("0000000000000003", "0000000000000001", offset_ms=300, operation="execute_tool", tool_name="lookup"),
        span("0000000000000001", None, offset_ms=0, duration_ms=1000, name="root"),
        span(
            "0000000000000002",
            "0000000000000001",
            offset_ms=10,
            operation="chat",
            request_model="m",
            usage=usage(inp=100, out=20),
            cost_usd=Decimal("0.5"),
        ),
        span("0000000000000004", "0000000000000003", offset_ms=320, status=SpanStatus.ERROR),
    ]
    [root] = build_tree(spans)
    assert root.name == "root" and root.depth == 0
    assert [c.span_id for c in root.children] == ["0000000000000002", "0000000000000003"]
    tool = root.children[1]
    assert tool.offset_ms == 300 and tool.children[0].depth == 2
    assert root.subtree.span_count == 4
    assert root.subtree.llm_calls == 1 and root.subtree.tool_calls == 1 and root.subtree.error_count == 1
    assert root.subtree.cost_usd == Decimal("0.5")
    assert [n.span_id for n in flatten([root])] == [
        "0000000000000001",
        "0000000000000002",
        "0000000000000003",
        "0000000000000004",
    ]


def test_orphans_are_promoted_to_roots() -> None:
    roots = build_tree([span("0000000000000001", "00000000000000ff"), span("0000000000000002", None, offset_ms=5)])
    assert [r.span_id for r in roots] == ["0000000000000001", "0000000000000002"]


def test_model_usage_aggregates_llm_calls() -> None:
    spans = [
        span("0000000000000001", operation="chat", request_model="a", usage=usage(10, 1), cost_usd=Decimal(1)),
        span("0000000000000002", operation="chat", request_model="a", usage=usage(5, 1), cost_usd=Decimal(2)),
        span("0000000000000003", operation="chat", request_model="b", usage=usage(1, 1), cost_usd=Decimal(5)),
        span("0000000000000004", operation="execute_tool", request_model="a"),
    ]
    rows = model_usage(spans)
    assert [(r.model, r.calls, r.input_tokens) for r in rows] == [("b", 1, 1), ("a", 2, 15)]


def test_parses_semconv_parts_messages() -> None:
    raw = (
        '[{"role":"user","parts":[{"type":"text","content":"hi"}]},'
        '{"role":"assistant","parts":[{"type":"tool_call","id":"t1","name":"lookup","arguments":{"id":1}}]},'
        '{"role":"tool","parts":[{"type":"tool_call_response","id":"t1","response":"ok"}]}]'
    )
    messages = parse_messages(raw)
    assert [m.role for m in messages] == ["user", "assistant", "tool"]
    assert messages[1].parts[0].name == "lookup" and messages[1].parts[0].arguments == {"id": 1}
    assert messages[2].parts[0].response == "ok"


def test_parses_provider_style_and_plain_messages() -> None:
    anthropic_style = parse_messages(
        '[{"role":"assistant","content":[{"type":"text","text":"Sure"},{"type":"tool_use","id":"x","name":"f","input":{}}]}]'
    )
    assert anthropic_style[0].text == "Sure" and anthropic_style[0].parts[1].type == "tool_call"
    openai_style = parse_messages(
        '[{"role":"assistant","content":"","tool_calls":[{"id":"c","function":{"name":"f","arguments":"{}"}}]}]'
    )
    assert openai_style[0].parts[0].name == "f"
    plain = parse_messages("just text", default_role="assistant")
    assert last_text(plain, "assistant") == "just text"
    assert parse_messages("") == []
