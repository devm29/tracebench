from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from tracebench.evals.models import ScorerSpec

NAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,79}$"
MAX_ITEMS_PER_REQUEST = 1000


class DatasetCreate(BaseModel):
    name: str = Field(pattern=NAME_PATTERN, description="lowercase slug, e.g. support-agent-golden")
    description: str = Field(default="", max_length=2000)
    default_scorers: list[ScorerSpec] = Field(default_factory=list)


class DatasetUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    default_scorers: list[ScorerSpec] | None = None


class Dataset(BaseModel):
    id: UUID
    name: str
    description: str
    version: int
    item_count: int
    default_scorers: list[ScorerSpec]
    created_at: datetime
    updated_at: datetime


class DatasetItemCreate(BaseModel):
    input: JsonValue
    expected_output: JsonValue | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    source_span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")


class DatasetItemUpdate(BaseModel):
    input: JsonValue | None = None
    expected_output: JsonValue | None = None
    metadata: dict[str, Any] | None = None


class DatasetItem(BaseModel):
    id: UUID
    item_key: UUID
    dataset_id: UUID
    revision: int
    input: JsonValue
    expected_output: JsonValue | None
    metadata: dict[str, Any]
    source_trace_id: str | None
    source_span_id: str | None
    created_at: datetime


class DatasetVersionItems(BaseModel):
    dataset: Dataset
    version: int
    items: list[DatasetItem]


class PromoteRequest(BaseModel):
    dataset_id: UUID | None = None
    dataset_name: str | None = Field(default=None, pattern=NAME_PATTERN)
    expected_output: JsonValue | None = None
    span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
