import json

from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span, Status

from tests.factories import export_request, record_agent_trace
from tracebench.ingest.models import SpanKind, SpanStatus
from tracebench.ingest.semconv import any_value_to_python, map_resource_spans, map_span


def _kv(key: str, value: AnyValue) -> KeyValue:
    return KeyValue(key=key, value=value)


def _span(**attrs: AnyValue) -> Span:
    return Span(
        trace_id=bytes.fromhex("1" * 32),
        span_id=bytes.fromhex("2" * 16),
        name="chat gpt-4o",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=1_700_000_000_000_000_000,
        end_time_unix_nano=1_700_000_000_250_000_000,
        attributes=[_kv(k.replace("__", "."), v) for k, v in attrs.items()],
    )


def test_maps_real_sdk_spans_into_records() -> None:
    batch = map_resource_spans(export_request(record_agent_trace()).resource_spans)
    assert batch.rejected == 0
    by_name = {r.name: r for r in batch.records}

    root = by_name["invoke_agent support-agent"]
    assert root.is_root and root.kind is SpanKind.SERVER
    assert root.operation == "invoke_agent" and root.agent_name == "support-agent"
    assert root.session_id == "sess-1"
    assert json.loads(root.input_messages)[0]["parts"][0]["content"] == "Where is order 48100?"

    chat = by_name["chat claude-sonnet-5-5"]
    assert chat.parent_span_id == root.span_id
    assert chat.provider == "anthropic" and chat.model == "claude-sonnet-5-5"
    assert (chat.usage.input_tokens, chat.usage.output_tokens, chat.usage.cache_read_tokens) == (1000, 100, 400)
    assert chat.usage.uncached_input_tokens == 600

    tool = by_name["execute_tool lookup_order"]
    assert tool.tool_name == "lookup_order" and tool.tool_call_id == "toolu_1"
    assert tool.status is SpanStatus.ERROR and tool.error_type == "TimeoutError"
    assert root.resource_attributes["service.name"] == "support-agent"
    assert root.service_name == "support-agent"


def test_legacy_attribute_names_are_understood() -> None:
    record = map_span(
        _span(
            gen_ai__system=AnyValue(string_value="openai"),
            gen_ai__usage__prompt_tokens=AnyValue(int_value=50),
            gen_ai__usage__completion_tokens=AnyValue(int_value=7),
            gen_ai__prompt=AnyValue(string_value='[{"role":"user","content":"hi"}]'),
        ),
        {},
    )
    assert record.provider == "openai"
    assert (record.usage.input_tokens, record.usage.output_tokens) == (50, 7)
    assert record.input_messages.startswith("[")
    assert record.service_name == "unknown_service"
    assert record.duration_ms == 250.0


def test_error_type_marks_unset_status_as_error_and_keeps_unknown_attributes() -> None:
    record = map_span(
        _span(error__type=AnyValue(string_value="RateLimitError"), app__tier=AnyValue(string_value="gold")), {}
    )
    assert record.status is SpanStatus.ERROR
    assert record.attributes == {"app.tier": "gold"}


def test_explicit_ok_status_is_preserved() -> None:
    span = _span()
    span.status.CopyFrom(Status(code=Status.STATUS_CODE_OK))
    assert map_span(span, {}).status is SpanStatus.OK


def test_content_falls_back_to_inference_event() -> None:
    span = _span()
    event = span.events.add()
    event.name = "gen_ai.client.inference.operation.details"
    event.time_unix_nano = span.start_time_unix_nano
    event.attributes.append(_kv("gen_ai.output.messages", AnyValue(string_value='[{"role":"assistant"}]')))
    assert map_span(span, {}).output_messages == '[{"role":"assistant"}]'


def test_structured_attribute_values_are_serialized() -> None:
    value = AnyValue()
    value.array_value.values.add().string_value = "stop"
    value.array_value.values.add().string_value = "length"
    assert any_value_to_python(value) == ["stop", "length"]
    record = map_span(_span(gen_ai__response__finish_reasons=value), {})
    assert record.finish_reasons == ["stop", "length"]


def test_invalid_spans_are_rejected_not_fatal() -> None:
    request = export_request(record_agent_trace())
    broken = request.resource_spans[0].scope_spans[0].spans.add()
    broken.trace_id = b"short"
    batch = map_resource_spans(request.resource_spans)
    assert batch.rejected == 1
    assert len(batch.records) == 3
    assert batch.errors
