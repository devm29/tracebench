import re

from tracebench.evals.models import ExactMatchSpec, ScoreResult
from tracebench.evals.scorers.base import ScoringInput
from tracebench.evals.text import as_text

_SPACE = re.compile(r"\s+")


class ExactMatchScorer:
    name = "exact_match"

    def __init__(self, spec: ExactMatchSpec) -> None:
        self._spec = spec

    def _normalize(self, text: str) -> str:
        if self._spec.normalize_whitespace:
            text = _SPACE.sub(" ", text).strip()
        return text if self._spec.case_sensitive else text.casefold()

    async def score(self, case: ScoringInput) -> ScoreResult | None:
        if case.expected is None:
            return None
        matched = self._normalize(as_text(case.output)) == self._normalize(as_text(case.expected))
        return ScoreResult(
            scorer=self.name,
            value=1.0 if matched else 0.0,
            passed=matched,
            detail=None if matched else "output differs from expected",
        )
