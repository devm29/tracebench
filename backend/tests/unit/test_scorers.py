from collections.abc import Sequence
from typing import Any

import pytest

from tracebench.errors import ValidationFailedError
from tracebench.evals.embeddings import (
    EmbedderUnavailableError,
    FallbackEmbedder,
    FastEmbedEmbedder,
    HashingEmbedder,
    cosine,
)
from tracebench.evals.judges import JudgeError, JudgeVerdict, OfflineJudge
from tracebench.evals.models import EmbeddingSimilaritySpec, ExactMatchSpec, JsonSchemaSpec, LlmJudgeSpec
from tracebench.evals.scorers.base import ScoringInput
from tracebench.evals.scorers.embedding import EmbeddingSimilarityScorer
from tracebench.evals.scorers.exact import ExactMatchScorer
from tracebench.evals.scorers.factory import ScorerFactory
from tracebench.evals.scorers.json_schema import JsonSchemaScorer
from tracebench.evals.scorers.llm_judge import LlmJudgeScorer
from tracebench.evals.text import as_text, token_f1

QUESTION = {"messages": [{"role": "user", "content": "refund order 48100"}]}


def case(expected: object, output: object) -> ScoringInput:
    return ScoringInput(input=QUESTION, expected=expected, output=output)  # type: ignore[arg-type]


async def test_exact_match_normalizes_case_and_whitespace() -> None:
    scorer = ExactMatchScorer(ExactMatchSpec())
    result = await scorer.score(case("Refund  issued.", "refund issued."))
    assert result is not None and result.passed
    strict = ExactMatchScorer(ExactMatchSpec(case_sensitive=True))
    result = await strict.score(case("Refund issued.", "refund issued."))
    assert result is not None and not result.passed
    assert await scorer.score(case(None, "x")) is None


async def test_json_schema_validates_strings_and_objects() -> None:
    schema = {
        "type": "object",
        "properties": {"priority": {"enum": ["low", "high"]}},
        "required": ["priority"],
    }
    scorer = JsonSchemaScorer(JsonSchemaSpec.model_validate({"schema": schema}))
    ok = await scorer.score(case(None, '{"priority": "high"}'))
    assert ok is not None and ok.passed
    bad = await scorer.score(case(None, {"priority": "urgent"}))
    assert bad is not None and not bad.passed and bad.detail and "priority" in bad.detail
    invalid = await scorer.score(case(None, "not json"))
    assert invalid is not None and invalid.detail and invalid.detail.startswith("not valid JSON")


def test_json_schema_rejects_an_invalid_schema() -> None:
    with pytest.raises(ValidationFailedError):
        JsonSchemaScorer(JsonSchemaSpec.model_validate({"schema": {"type": "nope"}}))


async def test_hash_embeddings_are_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder(dimensions=256)
    a1, a2, b = await embedder.embed(["refund issued for order", "refund issued for order", "tent pitching guide"])
    assert a1 == a2
    assert cosine(a1, a2) == pytest.approx(1.0)
    assert cosine(a1, b) < 0.5


async def test_embedding_similarity_thresholds() -> None:
    scorer = EmbeddingSimilarityScorer(EmbeddingSimilaritySpec(threshold=0.6), HashingEmbedder())
    close = await scorer.score(case("Your refund of $89 was issued", "Your refund of $89 has been issued"))
    far = await scorer.score(case("Your refund of $89 was issued", "Our tents are waterproof"))
    empty = await scorer.score(case("Your refund of $89 was issued", ""))
    assert close is not None and close.passed
    assert far is not None and not far.passed
    assert empty is not None and empty.value == 0


class _StubFastEmbed(FastEmbedEmbedder):
    def __init__(self, *, load_error: Exception | None = None, embed_error: Exception | None = None) -> None:
        super().__init__("stub-model")
        self._load_error = load_error
        self._embed_error = embed_error

    async def load(self) -> Any:
        if self._load_error is not None:
            raise EmbedderUnavailableError(str(self._load_error))
        return object()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._embed_error is not None:
            raise self._embed_error
        return [[1.0, 0.0] for _ in texts]


async def test_fallback_embedder_switches_when_the_model_cannot_load() -> None:
    embedder = FallbackEmbedder(_StubFastEmbed(load_error=OSError("download failed")), HashingEmbedder())
    vectors = await embedder.embed(["a"])
    assert len(vectors[0]) == 512
    assert embedder.name.startswith("hash")


async def test_fallback_embedder_surfaces_inference_errors_without_degrading() -> None:
    primary = _StubFastEmbed(embed_error=RuntimeError("onnx session crashed"))
    embedder = FallbackEmbedder(primary, HashingEmbedder())
    with pytest.raises(RuntimeError, match="onnx"):
        await embedder.embed(["a"])
    assert embedder.name == "fastembed:stub-model"
    primary._embed_error = None
    assert await embedder.embed(["a"]) == [[1.0, 0.0]]


async def test_offline_judge_scores_overlap() -> None:
    judge = OfflineJudge()
    good = await judge.grade(
        rubric="r" * 10, question="q", expected="refund of $89 issued", actual="refund of $89 issued"
    )
    bad = await judge.grade(rubric="r" * 10, question="q", expected="refund of $89 issued", actual="")
    assert good.score == 1.0 and bad.score == 0.0


async def test_llm_judge_scorer_reports_judge_errors_as_failures() -> None:
    class FailingJudge:
        name = "failing"

        async def grade(self, *, rubric: str, question: str, expected: str, actual: str) -> JudgeVerdict:
            raise JudgeError("rate limited")

    scorer = LlmJudgeScorer(LlmJudgeSpec(), FailingJudge())
    result = await scorer.score(case("a", "b"))
    assert result is not None and not result.passed and result.detail == "judge error: rate limited"


def test_factory_uses_defaults_when_no_specs_given() -> None:
    factory = ScorerFactory(HashingEmbedder(), OfflineJudge())
    assert [s.name for s in factory.build_all([])] == ["embedding_similarity", "llm_judge"]
    assert [s.name for s in factory.build_all([ExactMatchSpec()])] == ["exact_match"]


def test_text_helpers() -> None:
    assert as_text({"output": "x"}) == "x"
    assert as_text({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert token_f1("a b c", "a b c") == 1.0
    assert token_f1("a b", "c d") == 0.0
