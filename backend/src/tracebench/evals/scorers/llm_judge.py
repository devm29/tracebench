from tracebench.evals.judges import Judge, JudgeError
from tracebench.evals.models import LlmJudgeSpec, ScoreResult
from tracebench.evals.scorers.base import ScoringInput
from tracebench.evals.text import as_text


def _question(case_input: object) -> str:
    if isinstance(case_input, dict) and isinstance(case_input.get("messages"), list):
        turns = [m for m in case_input["messages"] if isinstance(m, dict)]
        return "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in turns)
    return as_text(case_input)


class LlmJudgeScorer:
    name = "llm_judge"

    def __init__(self, spec: LlmJudgeSpec, judge: Judge) -> None:
        self._spec = spec
        self._judge = judge

    async def score(self, case: ScoringInput) -> ScoreResult | None:
        if case.expected is None:
            return None
        try:
            verdict = await self._judge.grade(
                rubric=self._spec.rubric,
                question=_question(case.input),
                expected=as_text(case.expected),
                actual=as_text(case.output),
            )
        except JudgeError as exc:
            return ScoreResult(scorer=self.name, value=0.0, passed=False, detail=f"judge error: {exc}")
        return ScoreResult(
            scorer=self.name,
            value=verdict.score,
            passed=verdict.score >= self._spec.threshold,
            detail=f"[{self._judge.name}] {verdict.reasoning}",
        )
