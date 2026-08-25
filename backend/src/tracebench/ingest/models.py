from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

TRACE_ID_PATTERN = r"^[0-9a-f]{32}$"
SPAN_ID_PATTERN = r"^[0-9a-f]{16}$"


class SpanKind(StrEnum):
    UNSPECIFIED = "unspecified"
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(StrEnum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)

    @property
    def uncached_input_tokens(self) -> int:
        # Semconv input_tokens includes cached tokens; only the remainder bills at the full input rate.
        return max(self.input_tokens - self.cache_read_tokens - self.cache_write_tokens, 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class SpanEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    timestamp: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanRecord(BaseModel):
    """A span after GenAI semantic-convention mapping, ready for columnar storage."""

    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(pattern=TRACE_ID_PATTERN)
    span_id: str = Field(pattern=SPAN_ID_PATTERN)
    parent_span_id: str | None = Field(default=None, pattern=SPAN_ID_PATTERN)
    service_name: str
    name: str
    kind: SpanKind = SpanKind.INTERNAL
    start_time: datetime
    end_time: datetime
    status: SpanStatus = SpanStatus.UNSET
    status_message: str = ""

    operation: str = ""
    provider: str = ""
    request_model: str = ""
    response_model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: Decimal = Decimal(0)
    price_version: int = 0

    tool_name: str = ""
    tool_call_id: str = ""
    tool_arguments: str = ""
    tool_result: str = ""

    agent_name: str = ""
    session_id: str = ""
    input_messages: str = ""
    output_messages: str = ""
    system_instructions: str = ""
    finish_reasons: list[str] = Field(default_factory=list)
    error_type: str = ""

    attributes: dict[str, str] = Field(default_factory=dict)
    resource_attributes: dict[str, str] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> float:
        return max((self.end_time - self.start_time).total_seconds() * 1000.0, 0.0)

    @property
    def model(self) -> str:
        return self.response_model or self.request_model

    @property
    def is_root(self) -> bool:
        return self.parent_span_id is None

    @property
    def is_error(self) -> bool:
        return self.status is SpanStatus.ERROR
