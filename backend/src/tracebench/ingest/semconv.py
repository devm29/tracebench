"""Maps OTLP spans onto SpanRecord using the OpenTelemetry GenAI semantic conventions.

Covers the current attribute set (gen_ai.input.messages, gen_ai.provider.name, the
cache_read/cache_creation usage split) and the older names still emitted by many
instrumentations (gen_ai.system, gen_ai.prompt, gen_ai.usage.prompt_tokens, content events).
"""

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Final

from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, Span, Status

from tracebench.ingest.models import SpanEvent, SpanKind, SpanRecord, SpanStatus, TokenUsage

OPERATION: Final = "gen_ai.operation.name"
PROVIDER: Final = "gen_ai.provider.name"
LEGACY_SYSTEM: Final = "gen_ai.system"
REQUEST_MODEL: Final = "gen_ai.request.model"
RESPONSE_MODEL: Final = "gen_ai.response.model"
INPUT_TOKENS: Final = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS: Final = "gen_ai.usage.output_tokens"
LEGACY_PROMPT_TOKENS: Final = "gen_ai.usage.prompt_tokens"
LEGACY_COMPLETION_TOKENS: Final = "gen_ai.usage.completion_tokens"
CACHE_READ_TOKENS: Final = "gen_ai.usage.cache_read.input_tokens"
CACHE_WRITE_TOKENS: Final = "gen_ai.usage.cache_creation.input_tokens"
LEGACY_CACHE_READ_TOKENS: Final = "gen_ai.usage.cache_read_input_tokens"
LEGACY_CACHE_WRITE_TOKENS: Final = "gen_ai.usage.cache_creation_input_tokens"
TOOL_NAME: Final = "gen_ai.tool.name"
TOOL_CALL_ID: Final = "gen_ai.tool.call.id"
TOOL_ARGUMENTS: Final = "gen_ai.tool.call.arguments"
TOOL_RESULT: Final = "gen_ai.tool.call.result"
AGENT_NAME: Final = "gen_ai.agent.name"
CONVERSATION_ID: Final = "gen_ai.conversation.id"
SESSION_ID: Final = "session.id"
INPUT_MESSAGES: Final = "gen_ai.input.messages"
OUTPUT_MESSAGES: Final = "gen_ai.output.messages"
SYSTEM_INSTRUCTIONS: Final = "gen_ai.system_instructions"
LEGACY_PROMPT: Final = "gen_ai.prompt"
LEGACY_COMPLETION: Final = "gen_ai.completion"
FINISH_REASONS: Final = "gen_ai.response.finish_reasons"
ERROR_TYPE: Final = "error.type"
SERVICE_NAME: Final = "service.name"

INFERENCE_DETAILS_EVENT: Final = "gen_ai.client.inference.operation.details"
LEGACY_PROMPT_EVENT: Final = "gen_ai.content.prompt"
LEGACY_COMPLETION_EVENT: Final = "gen_ai.content.completion"

_PROMOTED_KEYS: Final = frozenset(
    {
        OPERATION, PROVIDER, LEGACY_SYSTEM, REQUEST_MODEL, RESPONSE_MODEL,
        INPUT_TOKENS, OUTPUT_TOKENS, LEGACY_PROMPT_TOKENS, LEGACY_COMPLETION_TOKENS,
        CACHE_READ_TOKENS, CACHE_WRITE_TOKENS, LEGACY_CACHE_READ_TOKENS, LEGACY_CACHE_WRITE_TOKENS,
        TOOL_NAME, TOOL_CALL_ID, TOOL_ARGUMENTS, TOOL_RESULT, AGENT_NAME, CONVERSATION_ID, SESSION_ID,
        INPUT_MESSAGES, OUTPUT_MESSAGES, SYSTEM_INSTRUCTIONS, LEGACY_PROMPT, LEGACY_COMPLETION,
        FINISH_REASONS, ERROR_TYPE,
    }
)  # fmt: skip

_KIND_MAP: Final = {
    Span.SPAN_KIND_UNSPECIFIED: SpanKind.UNSPECIFIED,
    Span.SPAN_KIND_INTERNAL: SpanKind.INTERNAL,
    Span.SPAN_KIND_SERVER: SpanKind.SERVER,
    Span.SPAN_KIND_CLIENT: SpanKind.CLIENT,
    Span.SPAN_KIND_PRODUCER: SpanKind.PRODUCER,
    Span.SPAN_KIND_CONSUMER: SpanKind.CONSUMER,
}

_STATUS_MAP: Final = {
    Status.STATUS_CODE_UNSET: SpanStatus.UNSET,
    Status.STATUS_CODE_OK: SpanStatus.OK,
    Status.STATUS_CODE_ERROR: SpanStatus.ERROR,
}


class SpanMappingError(ValueError):
    pass


def any_value_to_python(value: AnyValue) -> Any:
    match value.WhichOneof("value"):
        case "string_value":
            return value.string_value
        case "bool_value":
            return value.bool_value
        case "int_value":
            return value.int_value
        case "double_value":
            return value.double_value
        case "bytes_value":
            return value.bytes_value.hex()
        case "array_value":
            return [any_value_to_python(v) for v in value.array_value.values]
        case "kvlist_value":
            return {kv.key: any_value_to_python(kv.value) for kv in value.kvlist_value.values}
        case _:
            return None


def attributes_to_dict(attributes: Iterable[KeyValue]) -> dict[str, Any]:
    return {kv.key: any_value_to_python(kv.value) for kv in attributes}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), default=str)


def _as_int(*candidates: Any) -> int:
    for candidate in candidates:
        if candidate is None or isinstance(candidate, bool):
            continue
        try:
            return max(int(candidate), 0)
        except (TypeError, ValueError):
            continue
    return 0


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    return [str(value)]


def _nanos_to_datetime(nanos: int) -> datetime:
    seconds, remainder = divmod(nanos, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=remainder // 1000)


def _content_from_events(events: list[SpanEvent]) -> tuple[str, str, str]:
    input_messages = output_messages = system_instructions = ""
    for event in events:
        attrs = event.attributes
        if event.name == INFERENCE_DETAILS_EVENT:
            input_messages = input_messages or _as_text(attrs.get(INPUT_MESSAGES))
            output_messages = output_messages or _as_text(attrs.get(OUTPUT_MESSAGES))
            system_instructions = system_instructions or _as_text(attrs.get(SYSTEM_INSTRUCTIONS))
        elif event.name == LEGACY_PROMPT_EVENT:
            input_messages = input_messages or _as_text(attrs.get(LEGACY_PROMPT))
        elif event.name == LEGACY_COMPLETION_EVENT:
            output_messages = output_messages or _as_text(attrs.get(LEGACY_COMPLETION))
    return input_messages, output_messages, system_instructions


def map_span(span: Span, resource: dict[str, Any]) -> SpanRecord:
    if len(span.trace_id) != 16 or len(span.span_id) != 8:
        raise SpanMappingError("span is missing a valid trace_id or span_id")
    if span.end_time_unix_nano and span.end_time_unix_nano < span.start_time_unix_nano:
        raise SpanMappingError("span ends before it starts")

    attrs = attributes_to_dict(span.attributes)
    events = [
        SpanEvent(
            name=e.name,
            timestamp=_nanos_to_datetime(e.time_unix_nano),
            attributes=attributes_to_dict(e.attributes),
        )
        for e in span.events
    ]
    event_input, event_output, event_system = _content_from_events(events)

    status = _STATUS_MAP.get(span.status.code, SpanStatus.UNSET)
    error_type = _as_text(attrs.get(ERROR_TYPE))
    if error_type and status is SpanStatus.UNSET:
        status = SpanStatus.ERROR

    start = _nanos_to_datetime(span.start_time_unix_nano)
    end = _nanos_to_datetime(span.end_time_unix_nano or span.start_time_unix_nano)

    return SpanRecord(
        trace_id=span.trace_id.hex(),
        span_id=span.span_id.hex(),
        parent_span_id=span.parent_span_id.hex() if len(span.parent_span_id) == 8 else None,
        service_name=_as_text(resource.get(SERVICE_NAME)) or "unknown_service",
        name=span.name or "<unnamed>",
        kind=_KIND_MAP.get(span.kind, SpanKind.UNSPECIFIED),
        start_time=start,
        end_time=end,
        status=status,
        status_message=span.status.message,
        operation=_as_text(attrs.get(OPERATION)),
        provider=_as_text(attrs.get(PROVIDER) or attrs.get(LEGACY_SYSTEM)),
        request_model=_as_text(attrs.get(REQUEST_MODEL)),
        response_model=_as_text(attrs.get(RESPONSE_MODEL)),
        usage=TokenUsage(
            input_tokens=_as_int(attrs.get(INPUT_TOKENS), attrs.get(LEGACY_PROMPT_TOKENS)),
            output_tokens=_as_int(attrs.get(OUTPUT_TOKENS), attrs.get(LEGACY_COMPLETION_TOKENS)),
            cache_read_tokens=_as_int(attrs.get(CACHE_READ_TOKENS), attrs.get(LEGACY_CACHE_READ_TOKENS)),
            cache_write_tokens=_as_int(attrs.get(CACHE_WRITE_TOKENS), attrs.get(LEGACY_CACHE_WRITE_TOKENS)),
        ),
        tool_name=_as_text(attrs.get(TOOL_NAME)),
        tool_call_id=_as_text(attrs.get(TOOL_CALL_ID)),
        tool_arguments=_as_text(attrs.get(TOOL_ARGUMENTS)),
        tool_result=_as_text(attrs.get(TOOL_RESULT)),
        agent_name=_as_text(attrs.get(AGENT_NAME)),
        session_id=_as_text(attrs.get(CONVERSATION_ID) or attrs.get(SESSION_ID)),
        input_messages=_as_text(attrs.get(INPUT_MESSAGES) or attrs.get(LEGACY_PROMPT)) or event_input,
        output_messages=_as_text(attrs.get(OUTPUT_MESSAGES) or attrs.get(LEGACY_COMPLETION)) or event_output,
        system_instructions=_as_text(attrs.get(SYSTEM_INSTRUCTIONS)) or event_system,
        finish_reasons=_as_str_list(attrs.get(FINISH_REASONS)),
        error_type=error_type,
        attributes={k: _as_text(v) for k, v in attrs.items() if k not in _PROMOTED_KEYS},
        resource_attributes={k: _as_text(v) for k, v in resource.items()},
        events=events,
    )


class MappedBatch:
    __slots__ = ("errors", "records", "rejected")

    def __init__(self) -> None:
        self.records: list[SpanRecord] = []
        self.rejected = 0
        self.errors: list[str] = []


def map_resource_spans(resource_spans: Iterable[ResourceSpans]) -> MappedBatch:
    batch = MappedBatch()
    for rs in resource_spans:
        resource = attributes_to_dict(rs.resource.attributes)
        for scope_spans in rs.scope_spans:
            for span in scope_spans.spans:
                try:
                    batch.records.append(map_span(span, resource))
                except (SpanMappingError, ValueError) as exc:
                    batch.rejected += 1
                    if len(batch.errors) < 5:
                        batch.errors.append(str(exc).splitlines()[0])
    return batch
