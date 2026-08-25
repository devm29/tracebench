from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from tracebench.ingest.models import SpanKind, SpanStatus, TokenUsage


class TraceFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: datetime | None = None
    end: datetime | None = None
    service: str | None = None
    model: str | None = None
    status: Literal["ok", "error"] | None = None
    session_id: str | None = None
    q: str | None = Field(default=None, max_length=200)


class TraceSummary(BaseModel):
    trace_id: str
    root_name: str
    service_name: str
    session_id: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    span_count: int
    error_count: int
    root_error: bool
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    services: list[str]
    models: list[str]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class MessagePart(BaseModel):
    type: str
    content: str | None = None
    name: str | None = None
    id: str | None = None
    arguments: Any = None
    response: Any = None


class ChatMessage(BaseModel):
    role: str
    parts: list[MessagePart]
    finish_reason: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(p.content for p in self.parts if p.type == "text" and p.content)


class ToolCallView(BaseModel):
    name: str
    call_id: str
    arguments: Any = None
    result: Any = None


class Rollup(BaseModel):
    span_count: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    error_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: Decimal = Decimal(0)


class EventView(BaseModel):
    name: str
    timestamp: datetime
    offset_ms: float
    attributes: dict[str, Any]


class SpanNode(BaseModel):
    span_id: str
    parent_span_id: str | None
    name: str
    kind: SpanKind
    service_name: str
    start_time: datetime
    end_time: datetime
    offset_ms: float
    duration_ms: float
    depth: int
    status: SpanStatus
    status_message: str
    operation: str
    provider: str
    model: str
    request_model: str
    response_model: str
    usage: TokenUsage
    cost_usd: Decimal
    price_version: int
    tool: ToolCallView | None
    agent_name: str
    session_id: str
    system_instructions: str
    input_messages: list[ChatMessage]
    output_messages: list[ChatMessage]
    finish_reasons: list[str]
    error_type: str
    attributes: dict[str, str]
    resource_attributes: dict[str, str]
    events: list[EventView]
    subtree: Rollup
    children: list["SpanNode"] = Field(default_factory=list)


class ModelUsage(BaseModel):
    model: str
    provider: str
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: Decimal


class TraceDetail(BaseModel):
    trace_id: str
    root_name: str
    service_name: str
    session_id: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    services: list[str]
    rollup: Rollup
    models: list[ModelUsage]
    roots: list[SpanNode]


class Facets(BaseModel):
    services: list[str]
    models: list[str]
    operations: list[str]
    tools: list[str]


class TimeWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    service: str | None = None


class WindowStats(BaseModel):
    requests: int
    errors: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class Overview(BaseModel):
    window: TimeWindow
    current: WindowStats
    previous: WindowStats


class TimeseriesPoint(BaseModel):
    bucket: datetime
    requests: int
    errors: int
    p50_ms: float | None
    p95_ms: float | None
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int


class Timeseries(BaseModel):
    interval_seconds: int
    points: list[TimeseriesPoint]


class ModelLatency(BaseModel):
    model: str
    calls: int
    errors: int
    p50_ms: float
    p95_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


CostDimension = Literal["service", "model", "session"]


class CostRow(BaseModel):
    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    share: float


class CostBreakdown(BaseModel):
    group_by: CostDimension
    total_cost_usd: Decimal
    rows: list[CostRow]


class HeatCell(BaseModel):
    calls: int
    failures: int


class ToolHeatRow(BaseModel):
    tool_name: str
    calls: int
    failures: int
    failure_rate: float
    p95_ms: float
    cells: list[HeatCell]


class ToolHeatmap(BaseModel):
    interval_seconds: int
    buckets: list[datetime]
    tools: list[ToolHeatRow]
