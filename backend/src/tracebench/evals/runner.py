import asyncio
import statistics
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence

from tracebench.evals.models import CaseResult, EvalCase, RunSummary, ScoreResult
from tracebench.evals.scorers.base import Scorer, ScoringInput
from tracebench.evals.target import TargetClient

ProgressCallback = Callable[[CaseResult], Awaitable[None] | None]

UNSCORED = "unscored: no scorer applies to this case (it has no expected output; add one or use json_schema)"


class EvalRunner:
    def __init__(self, target: TargetClient, scorers: Sequence[Scorer], *, concurrency: int = 8) -> None:
        self._target = target
        self._scorers = list(scorers)
        self._semaphore = asyncio.Semaphore(concurrency)

    async def run(self, cases: Sequence[EvalCase], on_result: ProgressCallback | None = None) -> list[CaseResult]:
        async def one(case: EvalCase) -> CaseResult:
            async with self._semaphore:
                result = await self.run_case(case)
            if on_result is not None:
                maybe = on_result(result)
                if maybe is not None:
                    await maybe
            return result

        return list(await asyncio.gather(*(one(c) for c in cases)))

    async def run_case(self, case: EvalCase) -> CaseResult:
        response = await self._target.invoke(case.input)
        if response.error is not None:
            return CaseResult(
                item_key=case.item_key,
                item_id=case.item_id,
                input=case.input,
                expected_output=case.expected_output,
                output=None,
                passed=False,
                scores=[],
                latency_ms=response.latency_ms,
                error=response.error,
            )
        scoring = ScoringInput(input=case.input, expected=case.expected_output, output=response.output)
        outcomes = await asyncio.gather(*(s.score(scoring) for s in self._scorers), return_exceptions=True)
        scores: list[ScoreResult] = []
        for scorer, outcome in zip(self._scorers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                scores.append(
                    ScoreResult(scorer=scorer.name, value=0.0, passed=False, detail=f"scorer crashed: {outcome}")
                )
            elif outcome is not None:
                scores.append(outcome)
        # all() of nothing is True; a case nobody scored must not count as a pass.
        return CaseResult(
            item_key=case.item_key,
            item_id=case.item_id,
            input=case.input,
            expected_output=case.expected_output,
            output=response.output,
            passed=bool(scores) and all(s.passed for s in scores),
            scores=scores,
            latency_ms=response.latency_ms,
            error=None if scores else UNSCORED,
        )


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q * 100) - 1]


def summarize(results: Sequence[CaseResult]) -> RunSummary:
    total = len(results)
    errored = sum(1 for r in results if r.error is not None)
    passed = sum(1 for r in results if r.passed)
    by_scorer: dict[str, list[float]] = defaultdict(list)
    for result in results:
        for score in result.scores:
            by_scorer[score.scorer].append(score.value)
    latencies = sorted(r.latency_ms for r in results if r.latency_ms is not None and r.error is None)
    return RunSummary(
        total=total,
        passed=passed,
        failed=total - passed - errored,
        errored=errored,
        pass_rate=passed / total if total else 0.0,
        mean_scores={name: round(statistics.fmean(vals), 4) for name, vals in sorted(by_scorer.items())},
        latency_p50_ms=_percentile(latencies, 0.5),
        latency_p95_ms=_percentile(latencies, 0.95),
    )
