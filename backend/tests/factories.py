import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode

from tracebench.evals.models import EvalRun, RunStatus, RunSummary
from tracebench.ingest.models import SpanRecord, TokenUsage
from tracebench.pricing.models import MatchKind, ModelPrice, PriceVersion

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def span(
    span_id: str,
    parent: str | None = None,
    *,
    trace_id: str = "a" * 32,
    offset_ms: float = 0,
    duration_ms: float = 100,
    **fields: Any,
) -> SpanRecord:
    start = T0 + timedelta(milliseconds=offset_ms)
    return SpanRecord(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        service_name=fields.pop("service_name", "svc"),
        name=fields.pop("name", f"span-{span_id[-2:]}"),
        start_time=start,
        end_time=start + timedelta(milliseconds=duration_ms),
        **fields,
    )


def price_version(version_id: int, effective_from: datetime, prices: Sequence[ModelPrice]) -> PriceVersion:
    return PriceVersion(
        id=version_id,
        label=f"v{version_id}",
        effective_from=effective_from,
        created_at=effective_from,
        prices=list(prices),
    )


def model_price(model: str, inp: str, out: str, *, match: MatchKind = MatchKind.EXACT, **extra: str) -> ModelPrice:
    return ModelPrice(
        provider="anthropic",
        model=model,
        match=match,
        input_per_mtok=Decimal(inp),
        output_per_mtok=Decimal(out),
        **{k: Decimal(v) for k, v in extra.items()},
    )


def usage(inp: int = 0, out: int = 0, cache_read: int = 0, cache_write: int = 0) -> TokenUsage:
    return TokenUsage(input_tokens=inp, output_tokens=out, cache_read_tokens=cache_read, cache_write_tokens=cache_write)


def record_agent_trace(
    service: str = "support-agent", *, question: str = "Where is order 48100?"
) -> list[ReadableSpan]:
    """Emits a small agent trace through the real OTel SDK and returns the finished spans."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tests")
    with tracer.start_as_current_span("invoke_agent support-agent", kind=SpanKind.SERVER) as root:
        root.set_attributes(
            {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "support-agent",
                "gen_ai.conversation.id": "sess-1",
                "gen_ai.input.messages": json.dumps(
                    [{"role": "user", "parts": [{"type": "text", "content": question}]}]
                ),
                "gen_ai.output.messages": json.dumps(
                    [{"role": "assistant", "parts": [{"type": "text", "content": "It shipped yesterday."}]}]
                ),
            }
        )
        with tracer.start_as_current_span("chat claude-sonnet-5-5", kind=SpanKind.CLIENT) as chat:
            chat.set_attributes(
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "anthropic",
                    "gen_ai.request.model": "claude-sonnet-5-5",
                    "gen_ai.response.model": "claude-sonnet-5-5",
                    "gen_ai.usage.input_tokens": 1000,
                    "gen_ai.usage.output_tokens": 100,
                    "gen_ai.usage.cache_read.input_tokens": 400,
                }
            )
        with tracer.start_as_current_span("execute_tool lookup_order") as tool:
            tool.set_attributes(
                {
                    "gen_ai.operation.name": "execute_tool",
                    "gen_ai.tool.name": "lookup_order",
                    "gen_ai.tool.call.id": "toolu_1",
                    "gen_ai.tool.call.arguments": '{"order_id": "48100"}',
                }
            )
            tool.set_status(Status(StatusCode.ERROR, "timeout"))
            tool.set_attribute("error.type", "TimeoutError")
    provider.shutdown()
    return list(exporter.get_finished_spans())


def export_request(spans: Sequence[ReadableSpan]) -> ExportTraceServiceRequest:
    request: ExportTraceServiceRequest = encode_spans(spans)
    return request


def eval_run(pass_rate: float = 1.0, **overrides: Any) -> EvalRun:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "dataset_id": UUID(int=1),
        "dataset_name": "d",
        "dataset_version": 1,
        "name": None,
        "target_url": "http://t",
        "status": RunStatus.COMPLETED,
        "scorers": [],
        "git_sha": None,
        "git_ref": None,
        "is_baseline": False,
        "summary": RunSummary(
            total=4,
            passed=int(pass_rate * 4),
            failed=4 - int(pass_rate * 4),
            errored=0,
            pass_rate=pass_rate,
            mean_scores={"exact_match": pass_rate},
            latency_p50_ms=None,
            latency_p95_ms=None,
        ),
        "error": None,
        "created_at": datetime.now(UTC),
        "started_at": None,
        "finished_at": None,
    }
    return EvalRun.model_validate({**fields, **overrides})
