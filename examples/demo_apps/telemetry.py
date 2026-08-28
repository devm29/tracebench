"""OpenTelemetry setup plus helpers that record GenAI semantic-convention attributes."""

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from anthropic.types import Message, MessageParam
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span

PROVIDER = "anthropic"


def create_tracer_provider(
    service_name: str,
    endpoint: str,
    *,
    version: str = "1.0.0",
    environment: str = "demo",
    exporter: SpanExporter | None = None,
    max_queue_size: int = 2048,
) -> TracerProvider:
    resource = Resource.create(
        {"service.name": service_name, "service.version": version, "deployment.environment.name": environment}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            exporter or OTLPSpanExporter(endpoint=endpoint),
            max_queue_size=max_queue_size,
            max_export_batch_size=min(1024, max_queue_size),
            schedule_delay_millis=500,
        )
    )
    return provider


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def block_dict(block: object) -> dict[str, Any]:
    if isinstance(block, Mapping):
        return dict(cast("Mapping[str, Any]", block))
    dump = getattr(block, "model_dump", None)
    return cast("dict[str, Any]", dump()) if callable(dump) else {}


def to_semconv_messages(messages: Iterable[MessageParam]) -> list[dict[str, Any]]:
    """Converts Anthropic message params into the GenAI semconv role/parts shape."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        content = message["content"]
        blocks: Iterable[object] = [{"type": "text", "text": content}] if isinstance(content, str) else content
        parts: list[dict[str, Any]] = []
        for block in blocks:
            data = block_dict(block)
            match data.get("type"):
                case "text":
                    parts.append({"type": "text", "content": data["text"]})
                case "tool_use":
                    parts.append(
                        {
                            "type": "tool_call",
                            "id": data["id"],
                            "name": data["name"],
                            "arguments": data["input"],
                        }
                    )
                case "tool_result":
                    parts.append({"type": "tool_call_response", "id": data["tool_use_id"], "response": data["content"]})
        converted.append({"role": message["role"], "parts": parts})
    return converted


def output_messages(response: Message) -> list[dict[str, Any]]:
    finish = {"end_turn": "stop", "tool_use": "tool_call", "max_tokens": "length"}.get(
        response.stop_reason or "", response.stop_reason or "stop"
    )
    return [
        {
            "role": "assistant",
            "parts": to_semconv_messages([{"role": "assistant", "content": list(response.content)}])[0]["parts"],
            "finish_reason": finish,
        }
    ]


def record_chat_request(
    span: Span,
    *,
    model: str,
    max_tokens: int,
    system: str,
    messages: Sequence[MessageParam],
    capture_content: bool,
) -> None:
    span.set_attributes(
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": PROVIDER,
            "gen_ai.request.model": model,
            "gen_ai.request.max_tokens": max_tokens,
        }
    )
    if capture_content:
        span.set_attribute("gen_ai.system_instructions", dumps([{"type": "text", "content": system}]))
        span.set_attribute("gen_ai.input.messages", dumps(to_semconv_messages(messages)))


def record_chat_response(span: Span, response: Message, *, capture_content: bool) -> None:
    usage = response.usage
    cache_read = usage.cache_read_input_tokens or 0
    cache_write = usage.cache_creation_input_tokens or 0
    span.set_attributes(
        {
            "gen_ai.response.model": response.model,
            "gen_ai.response.id": response.id,
            "gen_ai.response.finish_reasons": [response.stop_reason or "end_turn"],
            # Anthropic reports cached tokens separately; semconv input_tokens includes them.
            "gen_ai.usage.input_tokens": usage.input_tokens + cache_read + cache_write,
            "gen_ai.usage.output_tokens": usage.output_tokens,
            "gen_ai.usage.cache_read.input_tokens": cache_read,
            "gen_ai.usage.cache_creation.input_tokens": cache_write,
        }
    )
    if capture_content:
        span.set_attribute("gen_ai.output.messages", dumps(output_messages(response)))


def tracer(provider: TracerProvider, name: str) -> trace.Tracer:
    return provider.get_tracer(name, "1.0.0")
