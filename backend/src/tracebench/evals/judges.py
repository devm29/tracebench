import os
from typing import Protocol

import anthropic
from pydantic import BaseModel, Field

from tracebench.config import JudgeBackend, Settings
from tracebench.errors import ConfigurationError
from tracebench.evals.text import token_f1, tokens

JUDGE_SYSTEM = (
    "You grade an AI application's answer against a reference answer for a regression test suite. "
    "Apply the rubric strictly but ignore differences in tone, formatting and phrasing. "
    "Score from 0 (wrong or unrelated) to 10 (equivalent to the reference)."
)


class JudgeVerdict(BaseModel):
    score: float = Field(ge=0, le=1)
    reasoning: str


class _JudgeOutput(BaseModel):
    reasoning: str = Field(description="One or two sentences explaining the grade.")
    score: int = Field(description="Integer grade from 0 to 10.")


class JudgeError(RuntimeError):
    pass


class Judge(Protocol):
    @property
    def name(self) -> str: ...

    async def grade(self, *, rubric: str, question: str, expected: str, actual: str) -> JudgeVerdict: ...


class OfflineJudge:
    """Deterministic stand-in for an LLM judge, based on token overlap with the reference."""

    @property
    def name(self) -> str:
        return "offline"

    async def grade(self, *, rubric: str, question: str, expected: str, actual: str) -> JudgeVerdict:
        if not actual.strip():
            return JudgeVerdict(score=0.0, reasoning="The response is empty.")
        score = token_f1(expected, actual)
        missing = [t for t in dict.fromkeys(tokens(expected)) if t not in set(tokens(actual)) and len(t) > 3]
        reasoning = (
            "Covers the reference answer." if not missing else f"Missing reference terms: {', '.join(missing[:6])}."
        )
        return JudgeVerdict(score=round(score, 4), reasoning=reasoning)


class AnthropicJudge:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return f"anthropic:{self._model}"

    async def grade(self, *, rubric: str, question: str, expected: str, actual: str) -> JudgeVerdict:
        prompt = (
            f"<rubric>\n{rubric}\n</rubric>\n\n<question>\n{question}\n</question>\n\n"
            f"<reference_answer>\n{expected}\n</reference_answer>\n\n<candidate_answer>\n{actual}\n</candidate_answer>"
        )
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=2048,
                system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=_JudgeOutput,
            )
        except anthropic.RateLimitError as exc:
            raise JudgeError("judge rate limited") from exc
        except anthropic.APIStatusError as exc:
            raise JudgeError(f"judge request failed with HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise JudgeError("could not reach the Anthropic API") from exc
        if response.stop_reason == "refusal":
            raise JudgeError("judge declined to grade this case")
        parsed = response.parsed_output
        if parsed is None:
            raise JudgeError("judge returned no structured verdict")
        return JudgeVerdict(score=min(max(parsed.score, 0), 10) / 10, reasoning=parsed.reasoning)


def build_judge(settings: Settings) -> Judge:
    if settings.judge_backend is JudgeBackend.ANTHROPIC:
        api_key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        # The SDK only fails on the first request, which would turn every case into a judge
        # error and the run into a false regression; fail at setup instead.
        if not api_key and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            raise ConfigurationError("the anthropic judge needs ANTHROPIC_API_KEY; use the offline judge without one")
        return AnthropicJudge(anthropic.AsyncAnthropic(api_key=api_key), settings.judge_model)
    return OfflineJudge()
