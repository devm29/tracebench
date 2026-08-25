import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tests.factories import eval_run
from tracebench.cli import main as cli
from tracebench.cli.client import ApiError
from tracebench.cli.regression import RegressionOutcome, RegressionRequest, RegressionSetupError
from tracebench.cli.report import COMMENT_MARKER, cell, markdown_summary
from tracebench.config import Settings
from tracebench.evals.models import DiffStatus, GateResult, ItemDiff, RunDiff

runner = CliRunner()
BASE_ARGS = ["eval", "run", "golden", "--target", "http://localhost:6405/support", "--embeddings", "hash", "-q"]


def outcome(passed: bool, diff: RunDiff | None = None) -> RegressionOutcome:
    reasons = [] if passed else ["1 case(s) passed on the baseline and fail now"]
    return RegressionOutcome(
        run=eval_run(1.0 if passed else 0.75),
        baseline=None,
        diff=diff,
        gate=GateResult(passed=passed, reasons=reasons),
        promoted_to_baseline=False,
    )


def stub_regression(monkeypatch: pytest.MonkeyPatch, result: RegressionOutcome | Exception) -> list[Any]:
    calls: list[Any] = []

    async def fake(request: RegressionRequest, *args: Any, **kwargs: Any) -> RegressionOutcome:
        calls.append(request)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cli, "run_regression", fake)
    return calls


def test_gate_pass_exits_0_and_writes_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = stub_regression(monkeypatch, outcome(True))
    summary, result = tmp_path / "summary.md", tmp_path / "result.json"
    invoked = runner.invoke(
        cli.app, [*BASE_ARGS, "--summary-file", str(summary), "--json-output", str(result), "--min-pass-rate", "0.9"]
    )
    assert invoked.exit_code == 0, invoked.output
    assert calls[0].policy.min_pass_rate == 0.9
    assert summary.read_text().startswith(COMMENT_MARKER)
    assert json.loads(result.read_text())["passed"] is True


def test_regression_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_regression(monkeypatch, outcome(False))
    assert runner.invoke(cli.app, BASE_ARGS).exit_code == 1


@pytest.mark.parametrize(
    "error",
    [ApiError(0, "cannot reach Tracebench"), RegressionSetupError("no dataset"), RuntimeError("bug")],
)
def test_setup_and_unexpected_errors_exit_2(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    stub_regression(monkeypatch, error)
    assert runner.invoke(cli.app, BASE_ARGS).exit_code == 2


def test_invalid_json_schema_exits_2_before_calling_anything(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = stub_regression(monkeypatch, outcome(True))
    schema = tmp_path / "bad.json"
    schema.write_text(json.dumps({"type": 12}))
    invoked = runner.invoke(cli.app, [*BASE_ARGS, "--scorer", f"json_schema:@{schema}"])
    assert invoked.exit_code == 2 and calls == []
    assert "invalid JSON schema" in invoked.output


@pytest.mark.parametrize("target", ["not a url", "ftp://host/x", "http://"])
def test_invalid_target_exits_2(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    calls = stub_regression(monkeypatch, outcome(True))
    args = [a if a != "http://localhost:6405/support" else target for a in BASE_ARGS]
    assert runner.invoke(cli.app, args).exit_code == 2 and calls == []


def test_missing_anthropic_key_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_regression(monkeypatch, outcome(True))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    no_key = Settings().model_copy(update={"anthropic_api_key": None})
    monkeypatch.setattr(cli, "get_settings", lambda: no_key)
    invoked = runner.invoke(cli.app, [*BASE_ARGS, "--judge", "anthropic"])
    assert invoked.exit_code == 2 and "ANTHROPIC_API_KEY" in invoked.output


def test_cell_neutralizes_markdown_in_model_output() -> None:
    hostile = "ok | @octocat ![x](http://evil/p.png) <img src=x> `code`"
    escaped = cell(hostile, 200)
    assert "|" not in escaped.replace("\\|", "")
    assert "@octocat" not in escaped and "<img" not in escaped
    assert "![x](" not in escaped and "\\`code\\`" in escaped


def test_markdown_summary_escapes_changed_cases() -> None:
    item = ItemDiff(
        item_key=eval_run().id,
        status=DiffStatus.REGRESSED,
        input={"messages": [{"role": "user", "content": "refund | @admin"}]},
        expected_output="x",
        base_output="x",
        head_output="<script>alert(1)</script>",
        base_passed=True,
        head_passed=False,
        base_error=None,
        head_error=None,
        score_deltas=[],
        base_latency_ms=None,
        head_latency_ms=None,
    )
    run = eval_run(0.75)
    diff = RunDiff(
        base=run,
        head=run,
        pass_rate_delta=-0.25,
        mean_score_deltas={},
        counts=dict.fromkeys(DiffStatus, 0),
        items=[item],
        warnings=["embedders differ"],
    )
    text = markdown_summary(outcome(False, diff))
    row = next(line for line in text.splitlines() if line.startswith("| regressed"))
    assert row.count(" | ") == 2 and "<script>" not in row and "@admin" not in row
    assert "embedders differ" in text
