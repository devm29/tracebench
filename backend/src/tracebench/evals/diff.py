from collections import Counter
from collections.abc import Sequence
from uuid import UUID

from tracebench.evals.models import (
    CaseResult,
    DiffStatus,
    EvalRun,
    GatePolicy,
    GateResult,
    ItemDiff,
    RunDiff,
    RunSummary,
    ScoreDelta,
)

_ORDER = {
    DiffStatus.REGRESSED: 0,
    DiffStatus.FIXED: 1,
    DiffStatus.UNCHANGED_FAIL: 2,
    DiffStatus.ADDED: 3,
    DiffStatus.REMOVED: 4,
    DiffStatus.UNCHANGED_PASS: 5,
}


def _status(base: CaseResult | None, head: CaseResult | None) -> DiffStatus:
    if base is None:
        return DiffStatus.ADDED
    if head is None:
        return DiffStatus.REMOVED
    if base.passed and not head.passed:
        return DiffStatus.REGRESSED
    if not base.passed and head.passed:
        return DiffStatus.FIXED
    return DiffStatus.UNCHANGED_PASS if head.passed else DiffStatus.UNCHANGED_FAIL


def _score_deltas(base: CaseResult | None, head: CaseResult | None) -> list[ScoreDelta]:
    base_scores = {s.scorer: s.value for s in base.scores} if base else {}
    head_scores = {s.scorer: s.value for s in head.scores} if head else {}
    deltas = []
    for name in sorted(base_scores.keys() | head_scores.keys()):
        b, h = base_scores.get(name), head_scores.get(name)
        deltas.append(
            ScoreDelta(
                scorer=name,
                base=b,
                head=h,
                delta=round(h - b, 4) if b is not None and h is not None else None,
            )
        )
    return deltas


def _warnings(base: EvalRun, head: EvalRun) -> list[str]:
    warnings: list[str] = []
    if base.embedder and head.embedder and base.embedder != head.embedder:
        warnings.append(
            f"embedding similarity was computed with {base.embedder} on the base run and {head.embedder} "
            "on the head run, so its scores are not comparable"
        )
    if base.dataset_version != head.dataset_version:
        warnings.append(f"runs use different dataset versions (v{base.dataset_version} vs v{head.dataset_version})")
    return warnings


def diff_runs(
    base: EvalRun, base_results: Sequence[CaseResult], head: EvalRun, head_results: Sequence[CaseResult]
) -> RunDiff:
    base_by_key: dict[UUID, CaseResult] = {r.item_key: r for r in base_results}
    head_by_key: dict[UUID, CaseResult] = {r.item_key: r for r in head_results}
    items: list[ItemDiff] = []
    for key in base_by_key.keys() | head_by_key.keys():
        b, h = base_by_key.get(key), head_by_key.get(key)
        reference = h or b
        assert reference is not None
        items.append(
            ItemDiff(
                item_key=key,
                status=_status(b, h),
                input=reference.input,
                expected_output=reference.expected_output,
                base_output=b.output if b else None,
                head_output=h.output if h else None,
                base_passed=b.passed if b else None,
                head_passed=h.passed if h else None,
                base_error=b.error if b else None,
                head_error=h.error if h else None,
                score_deltas=_score_deltas(b, h),
                base_latency_ms=b.latency_ms if b else None,
                head_latency_ms=h.latency_ms if h else None,
            )
        )
    items.sort(key=lambda i: (_ORDER[i.status], str(i.item_key)))
    counts = Counter(i.status for i in items)
    base_summary, head_summary = base.summary, head.summary
    mean_deltas: dict[str, float] = {}
    if base_summary and head_summary:
        for name in sorted(base_summary.mean_scores.keys() & head_summary.mean_scores.keys()):
            mean_deltas[name] = round(head_summary.mean_scores[name] - base_summary.mean_scores[name], 4)
    return RunDiff(
        base=base,
        head=head,
        warnings=_warnings(base, head),
        pass_rate_delta=round(
            (head_summary.pass_rate if head_summary else 0.0) - (base_summary.pass_rate if base_summary else 0.0),
            4,
        ),
        mean_score_deltas=mean_deltas,
        counts={status: counts.get(status, 0) for status in DiffStatus},
        items=items,
    )


def evaluate_gate(summary: RunSummary, diff: RunDiff | None, policy: GatePolicy) -> GateResult:
    reasons: list[str] = []
    if policy.min_pass_rate is not None and summary.pass_rate < policy.min_pass_rate:
        reasons.append(f"pass rate {summary.pass_rate:.1%} is below the required {policy.min_pass_rate:.1%}")
    if diff is not None:
        regressed = diff.counts.get(DiffStatus.REGRESSED, 0)
        if policy.fail_on_regression and regressed:
            reasons.append(f"{regressed} case(s) passed on the baseline and fail now")
        drop = -diff.pass_rate_delta
        if policy.max_pass_rate_drop is not None and drop > policy.max_pass_rate_drop:
            reasons.append(f"pass rate dropped {drop:.1%} vs baseline (allowed {policy.max_pass_rate_drop:.1%})")
    return GateResult(passed=not reasons, reasons=reasons)
