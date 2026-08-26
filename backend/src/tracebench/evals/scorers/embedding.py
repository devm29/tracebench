from tracebench.evals.embeddings import Embedder, cosine
from tracebench.evals.models import EmbeddingSimilaritySpec, ScoreResult
from tracebench.evals.scorers.base import ScoringInput
from tracebench.evals.text import as_text


class EmbeddingSimilarityScorer:
    name = "embedding_similarity"

    def __init__(self, spec: EmbeddingSimilaritySpec, embedder: Embedder) -> None:
        self._threshold = spec.threshold
        self._embedder = embedder

    async def score(self, case: ScoringInput) -> ScoreResult | None:
        if case.expected is None:
            return None
        expected, actual = as_text(case.expected), as_text(case.output)
        if not actual.strip():
            return ScoreResult(scorer=self.name, value=0.0, passed=False, detail="empty output")
        exp_vec, act_vec = await self._embedder.embed([expected, actual])
        similarity = max(0.0, min(1.0, cosine(exp_vec, act_vec)))
        return ScoreResult(
            scorer=self.name,
            value=round(similarity, 4),
            passed=similarity >= self._threshold,
            detail=f"cosine {similarity:.3f} vs threshold {self._threshold:.2f} ({self._embedder.name})",
        )
