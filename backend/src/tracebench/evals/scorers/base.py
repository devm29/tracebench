from dataclasses import dataclass
from typing import Protocol

from pydantic import JsonValue

from tracebench.evals.models import ScoreResult


@dataclass(frozen=True, slots=True)
class ScoringInput:
    input: JsonValue
    expected: JsonValue | None
    output: JsonValue | None


class Scorer(Protocol):
    @property
    def name(self) -> str: ...

    async def score(self, case: ScoringInput) -> ScoreResult | None:
        """Returns None when the scorer does not apply to this case (e.g. no expected output)."""
        ...
