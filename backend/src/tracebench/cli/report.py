import json
from typing import Any

from tracebench.cli.regression import RegressionOutcome
from tracebench.evals.models import DiffStatus, ItemDiff
from tracebench.evals.text import as_text


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _signed_pct(value: float) -> str:
    return f"{'+' if value >= 0 else ''}{value * 100:.1f} pp"


def _question(item: ItemDiff) -> str:
    payload: Any = item.input
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list) and payload["messages"]:
        last = payload["messages"][-1]
        if isinstance(last, dict):
            return str(last.get("content", ""))
    return as_text(payload)


def _clip(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


_ZWJ = "\u200d"
_MARKDOWN_ESCAPES = str.maketrans(
    {
        "\\": "\\\\",
        "|": "\\|",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "[": "\\[",
        "]": "\\]",
        "!": "\\!",
        "#": "\\#",
        "<": "&lt;",
        ">": "&gt;",
        "@": "@" + _ZWJ,
    }
)


def cell(text: str, limit: int) -> str:
    """Makes untrusted model text inert inside a table cell: no table breaks, links, images,
    HTML or @mentions."""
    return _clip(text, limit).translate(_MARKDOWN_ESCAPES)


COMMENT_MARKER = "<!-- tracebench-regression -->"


def markdown_summary(outcome: RegressionOutcome, *, ui_url: str | None = None) -> str:
    run, summary = outcome.run, outcome.run.summary
    assert summary is not None
    verdict = "Passed" if outcome.gate.passed else "Failed"
    lines = [
        COMMENT_MARKER,
        f"## Tracebench regression check: {verdict}",
        "",
        f"Dataset **{run.dataset_name}** v{run.dataset_version} against {cell(run.target_url, 200)}",
        "",
        "| Metric | This run | Baseline | Change |",
        "| --- | ---: | ---: | ---: |",
    ]
    base_summary = outcome.baseline.summary if outcome.baseline else None
    lines.append(
        f"| Pass rate | {_pct(summary.pass_rate)} ({summary.passed}/{summary.total}) | "
        f"{_pct(base_summary.pass_rate) if base_summary else '-'} | "
        f"{_signed_pct(outcome.diff.pass_rate_delta) if outcome.diff else '-'} |"
    )
    for scorer, mean in summary.mean_scores.items():
        base = base_summary.mean_scores.get(scorer) if base_summary else None
        change = f"{mean - base:+.3f}" if base is not None else "-"
        lines.append(f"| {scorer} | {mean:.3f} | {f'{base:.3f}' if base is not None else '-'} | {change} |")
    if summary.latency_p95_ms is not None:
        base_p95 = base_summary.latency_p95_ms if base_summary else None
        lines.append(
            f"| p95 latency | {summary.latency_p95_ms:.0f} ms | "
            f"{f'{base_p95:.0f} ms' if base_p95 is not None else '-'} | "
            f"{f'{summary.latency_p95_ms - base_p95:+.0f} ms' if base_p95 is not None else '-'} |"
        )
    lines.append("")
    if outcome.gate.reasons:
        lines.extend(f"- {reason}" for reason in outcome.gate.reasons)
        lines.append("")
    if outcome.diff is not None and outcome.diff.warnings:
        lines.extend(f"> **Note:** {cell(w, 300)}" for w in outcome.diff.warnings)
        lines.append("")
    if outcome.diff is not None:
        changed = [i for i in outcome.diff.items if i.status in {DiffStatus.REGRESSED, DiffStatus.FIXED}]
        if changed:
            lines += ["| Status | Input | Output |", "| --- | --- | --- |"]
            for item in changed[:15]:
                output = item.head_error or as_text(item.head_output)
                lines.append(f"| {item.status.value} | {cell(_question(item), 70)} | {cell(output, 90)} |")
            lines.append("")
    if not outcome.baseline:
        lines.append("_No baseline run yet; this run was compared against the gate thresholds only._")
    if outcome.promoted_to_baseline:
        lines.append("_This run is now the baseline for the dataset._")
    if ui_url:
        lines.append(f"\n[Open the run in Tracebench]({ui_url.rstrip('/')}/evals/{run.id})")
    return "\n".join(lines) + "\n"


def json_summary(outcome: RegressionOutcome) -> str:
    return json.dumps(
        {
            "passed": outcome.gate.passed,
            "reasons": outcome.gate.reasons,
            "run": outcome.run.model_dump(mode="json", by_alias=True),
            "baseline_run_id": str(outcome.baseline.id) if outcome.baseline else None,
            "counts": {k.value: v for k, v in outcome.diff.counts.items()} if outcome.diff else None,
        },
        indent=2,
    )
