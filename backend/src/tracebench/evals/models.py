from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, JsonValue

DEFAULT_JUDGE_RUBRIC = (
    "The response answers the user's request with the same facts and outcome as the expected answer. "
    "Wording may differ; missing or contradicting facts may not."
)


class ExactMatchSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["exact_match"] = "exact_match"
    case_sensitive: bool = False
    normalize_whitespace: bool = True


class JsonSchemaSpec(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    type: Literal["json_schema"] = "json_schema"
    json_schema: dict[str, Any] = Field(alias="schema")


class EmbeddingSimilaritySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["embedding_similarity"] = "embedding_similarity"
    threshold: float = Field(default=0.8, ge=0, le=1)


class LlmJudgeSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["llm_judge"] = "llm_judge"
    rubric: str = Field(default=DEFAULT_JUDGE_RUBRIC, min_length=10, max_length=4000)
    threshold: float = Field(default=0.7, ge=0, le=1)


ScorerSpec = Annotated[
    ExactMatchSpec | JsonSchemaSpec | EmbeddingSimilaritySpec | LlmJudgeSpec,
    Field(discriminator="type"),
]


class ScoreResult(BaseModel):
    scorer: str
    value: float = Field(ge=0, le=1)
    passed: bool
    detail: str | None = None


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_key: UUID
    item_id: UUID
    input: JsonValue
    expected_output: JsonValue | None = None


class CaseResult(BaseModel):
    item_key: UUID
    item_id: UUID
    input: JsonValue
    expected_output: JsonValue | None
    output: JsonValue | None
    passed: bool
    scores: list[ScoreResult]
    latency_ms: float | None = None
    error: str | None = None


class RunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errored: int
    pass_rate: float
    mean_scores: dict[str, float]
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMetadata(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    git_sha: str | None = Field(default=None, max_length=64)
    git_ref: str | None = Field(default=None, max_length=255)


class EvalRunRecord(RunMetadata):
    """A run executed elsewhere (usually the CLI in CI) and reported back for storage."""

    dataset_id: UUID
    dataset_version: int = Field(ge=0)
    target_url: str = Field(max_length=2000)
    scorers: list[ScorerSpec]
    results: list[CaseResult]
    started_at: datetime
    finished_at: datetime
    embedder: str | None = Field(default=None, max_length=200)


class EvalRunExecute(RunMetadata):
    dataset_id: UUID
    target_url: AnyHttpUrl = Field(
        description="Must be allowed by TRACEBENCH_EVAL_TARGET_ALLOWLIST (loopback only in development)."
    )
    dataset_version: int | None = Field(default=None, ge=0)
    scorers: list[ScorerSpec] | None = None


class GatePolicy(BaseModel):
    fail_on_regression: bool = True
    min_pass_rate: float | None = Field(default=None, ge=0, le=1)
    max_pass_rate_drop: float | None = Field(default=None, ge=0, le=1)


class GateResult(BaseModel):
    passed: bool
    reasons: list[str]


class RecordedGate(GateResult):
    """The CI verdict for a run, as the CLI computed it with its own policy."""

    policy: GatePolicy
    baseline_run_id: UUID | None = None


class EvalRun(BaseModel):
    id: UUID
    dataset_id: UUID
    dataset_name: str
    dataset_version: int
    name: str | None
    target_url: str
    status: RunStatus
    scorers: list[ScorerSpec]
    git_sha: str | None
    git_ref: str | None
    is_baseline: bool
    summary: RunSummary | None
    error: str | None
    embedder: str | None = None
    gate: RecordedGate | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DiffStatus(StrEnum):
    REGRESSED = "regressed"
    FIXED = "fixed"
    UNCHANGED_PASS = "unchanged_pass"
    UNCHANGED_FAIL = "unchanged_fail"
    ADDED = "added"
    REMOVED = "removed"


class ScoreDelta(BaseModel):
    scorer: str
    base: float | None
    head: float | None
    delta: float | None


class ItemDiff(BaseModel):
    item_key: UUID
    status: DiffStatus
    input: JsonValue
    expected_output: JsonValue | None
    base_output: JsonValue | None
    head_output: JsonValue | None
    base_passed: bool | None
    head_passed: bool | None
    base_error: str | None
    head_error: str | None
    score_deltas: list[ScoreDelta]
    base_latency_ms: float | None
    head_latency_ms: float | None


class RunDiff(BaseModel):
    base: EvalRun
    head: EvalRun
    pass_rate_delta: float
    mean_score_deltas: dict[str, float]
    counts: dict[DiffStatus, int]
    items: list[ItemDiff]
    warnings: list[str] = Field(default_factory=list)
