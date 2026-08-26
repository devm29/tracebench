from collections.abc import Sequence

from tracebench.evals.embeddings import Embedder
from tracebench.evals.judges import Judge
from tracebench.evals.models import (
    EmbeddingSimilaritySpec,
    ExactMatchSpec,
    JsonSchemaSpec,
    LlmJudgeSpec,
    ScorerSpec,
)
from tracebench.evals.scorers.base import Scorer
from tracebench.evals.scorers.embedding import EmbeddingSimilarityScorer
from tracebench.evals.scorers.exact import ExactMatchScorer
from tracebench.evals.scorers.json_schema import JsonSchemaScorer
from tracebench.evals.scorers.llm_judge import LlmJudgeScorer

DEFAULT_SCORERS: tuple[ScorerSpec, ...] = (EmbeddingSimilaritySpec(), LlmJudgeSpec())


class ScorerFactory:
    def __init__(self, embedder: Embedder, judge: Judge) -> None:
        self._embedder = embedder
        self._judge = judge

    def build(self, spec: ScorerSpec) -> Scorer:
        match spec:
            case ExactMatchSpec():
                return ExactMatchScorer(spec)
            case JsonSchemaSpec():
                return JsonSchemaScorer(spec)
            case EmbeddingSimilaritySpec():
                return EmbeddingSimilarityScorer(spec, self._embedder)
            case LlmJudgeSpec():
                return LlmJudgeScorer(spec, self._judge)

    def build_all(self, specs: Sequence[ScorerSpec]) -> list[Scorer]:
        return [self.build(s) for s in (specs or DEFAULT_SCORERS)]

    def embedder_used(self, specs: Sequence[ScorerSpec]) -> str | None:
        """Name of the embedder behind embedding_similarity, read after scoring so a fallback shows."""
        if any(isinstance(s, EmbeddingSimilaritySpec) for s in (specs or DEFAULT_SCORERS)):
            return self._embedder.name
        return None
