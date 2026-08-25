import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import anthropic
import httpx
import typer
from rich.console import Console
from rich.table import Table

from tracebench import __version__
from tracebench.cli.client import ApiError, TracebenchClient, api_client
from tracebench.cli.regression import (
    BaselineMode,
    RegressionOutcome,
    RegressionRequest,
    RegressionSetupError,
    run_regression,
)
from tracebench.cli.report import json_summary, markdown_summary
from tracebench.cli.scorers import ScorerSpecError, load_scorer_file, parse_scorer
from tracebench.config import EmbeddingsBackend, JudgeBackend, get_settings
from tracebench.datasets.models import MAX_ITEMS_PER_REQUEST, DatasetItemCreate
from tracebench.errors import TracebenchError
from tracebench.evals.embeddings import build_embedder
from tracebench.evals.judges import build_judge
from tracebench.evals.models import CaseResult, GatePolicy, ScorerSpec
from tracebench.evals.scorers.factory import ScorerFactory
from tracebench.evals.text import as_text

app = typer.Typer(help="Tracebench: replay golden datasets against your LLM app and gate CI on regressions.")
eval_app = typer.Typer(help="Run evaluations.")
datasets_app = typer.Typer(help="Manage golden datasets.")
runs_app = typer.Typer(help="Inspect eval runs.")
app.add_typer(eval_app, name="eval")
app.add_typer(datasets_app, name="datasets")
app.add_typer(runs_app, name="runs")

console = Console(stderr=True)
out = Console()

ApiUrl = Annotated[str, typer.Option("--api-url", envvar="TRACEBENCH_API_URL", help="Tracebench API base URL.")]
ApiToken = Annotated[
    str | None,
    typer.Option(
        "--api-token", envvar="TRACEBENCH_API_TOKEN", help="Bearer token, when the API sets one.", show_default=False
    ),
]
DEFAULT_API = "http://localhost:8105"

EXIT_REGRESSION = 1
EXIT_ERROR = 2


def _api(url: str, token: str | None) -> httpx.AsyncClient:
    return api_client(url, token)


def _target_url(raw: str) -> str:
    try:
        url = httpx.URL(raw)
    except httpx.InvalidURL as exc:
        raise ValueError(f"invalid --target {raw!r}: {exc}") from exc
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValueError(f"--target must be an absolute http(s) URL, got {raw!r}")
    return str(url)


def _fail(message: str) -> typer.Exit:
    console.print(f"[red]error:[/red] {message}")
    return typer.Exit(EXIT_ERROR)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
) -> None:
    if version:
        out.print(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        out.print(ctx.get_help())


def _progress(result: CaseResult) -> None:
    mark = "[green]pass[/green]" if result.passed else ("[yellow]error[/yellow]" if result.error else "[red]fail[/red]")
    latency = f"{result.latency_ms:.0f}ms" if result.latency_ms is not None else "-"
    console.print(f"  {mark}  {str(result.item_key)[:8]}  {latency:>7}")


def _print_outcome(outcome: RegressionOutcome) -> None:
    summary = outcome.run.summary
    assert summary is not None
    table = Table(title=f"{outcome.run.dataset_name} v{outcome.run.dataset_version}", title_justify="left")
    table.add_column("metric")
    table.add_column("this run", justify="right")
    table.add_column("baseline", justify="right")
    base = outcome.baseline.summary if outcome.baseline else None
    table.add_row("pass rate", f"{summary.pass_rate:.1%}", f"{base.pass_rate:.1%}" if base else "-")
    for scorer, mean in summary.mean_scores.items():
        prior = base.mean_scores.get(scorer) if base else None
        table.add_row(scorer, f"{mean:.3f}", f"{prior:.3f}" if prior is not None else "-")
    console.print(table)
    if outcome.diff is not None:
        counts = {k.value: v for k, v in outcome.diff.counts.items() if v}
        console.print("diff vs baseline: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        for warning in outcome.diff.warnings:
            console.print(f"[yellow]warning:[/yellow] {warning}")
    if outcome.gate.passed:
        console.print("[green]regression gate passed[/green]")
    else:
        console.print("[red]regression gate failed[/red]")
        for reason in outcome.gate.reasons:
            console.print(f"  - {reason}")


@eval_app.command("run")
def eval_run(
    dataset: Annotated[str, typer.Argument(help="Dataset name.")],
    target: Annotated[
        str, typer.Option("--target", "-t", envvar="TRACEBENCH_TARGET_URL", help="App endpoint to call.")
    ],
    api_url: ApiUrl = DEFAULT_API,
    api_token: ApiToken = None,
    scorer: Annotated[
        list[str] | None,
        typer.Option(
            "--scorer",
            "-s",
            help="exact_match | embedding_similarity[:t] | llm_judge[:t] | json_schema:@file",
        ),
    ] = None,
    scorers_file: Annotated[Path | None, typer.Option(help="JSON file with a list of scorer specs.")] = None,
    baseline: Annotated[str, typer.Option(help="'auto' (dataset baseline), 'none', or a run id.")] = "auto",
    set_baseline: Annotated[
        Literal["never", "if-passed", "always"],
        typer.Option(help="Promote this run to the dataset baseline."),
    ] = "never",
    min_pass_rate: Annotated[float | None, typer.Option(min=0, max=1)] = None,
    max_pass_rate_drop: Annotated[float | None, typer.Option(min=0, max=1)] = None,
    allow_regressions: Annotated[bool, typer.Option(help="Do not fail when individual cases regress.")] = False,
    dataset_version: Annotated[int | None, typer.Option(min=0)] = None,
    name: Annotated[str | None, typer.Option(help="Label for this run.")] = None,
    git_sha: Annotated[str | None, typer.Option(envvar="GITHUB_SHA")] = None,
    git_ref: Annotated[str | None, typer.Option(envvar="GITHUB_REF_NAME")] = None,
    concurrency: Annotated[int, typer.Option(min=1, max=64)] = 8,
    timeout: Annotated[float, typer.Option(help="Per-request timeout for the target, seconds.")] = 60.0,
    summary_file: Annotated[
        Path | None, typer.Option(envvar="GITHUB_STEP_SUMMARY", help="Append a markdown summary here.")
    ] = None,
    json_output: Annotated[Path | None, typer.Option(help="Write a machine-readable result here.")] = None,
    ui_url: Annotated[str | None, typer.Option(envvar="TRACEBENCH_UI_URL")] = None,
    embeddings: Annotated[EmbeddingsBackend | None, typer.Option(help="Override the embeddings backend.")] = None,
    judge: Annotated[JudgeBackend | None, typer.Option(help="Override the LLM judge backend.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Replay DATASET against TARGET, score it, record the run and compare it with the baseline.

    Exits 0 when the gate passes, 1 on regression and 2 on setup errors.
    """
    try:
        target_url = _target_url(target)
        specs: list[ScorerSpec] = [parse_scorer(s) for s in scorer or []]
        if scorers_file is not None:
            specs.extend(load_scorer_file(scorers_file))
        baseline_mode: BaselineMode = "auto" if baseline == "auto" else "none" if baseline == "none" else UUID(baseline)
        settings = get_settings().model_copy(
            update={
                k: v for k, v in {"embeddings_backend": embeddings, "judge_backend": judge}.items() if v is not None
            }
        )
        factory = ScorerFactory(build_embedder(settings), build_judge(settings))
        if specs:
            factory.build_all(specs)
    except (ScorerSpecError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    except TracebenchError as exc:
        raise _fail(exc.message) from exc
    except anthropic.AnthropicError as exc:
        raise _fail(f"cannot set up the LLM judge: {exc}") from exc

    request = RegressionRequest(
        dataset=dataset,
        target_url=target_url,
        scorers=specs,
        baseline=baseline_mode,
        policy=GatePolicy(
            fail_on_regression=not allow_regressions,
            min_pass_rate=min_pass_rate,
            max_pass_rate_drop=max_pass_rate_drop,
        ),
        dataset_version=dataset_version,
        name=name,
        git_sha=git_sha,
        git_ref=git_ref,
        set_baseline=set_baseline,
        concurrency=concurrency,
        target_timeout=timeout,
    )

    async def go() -> RegressionOutcome:
        async with _api(api_url, api_token) as api_http, httpx.AsyncClient() as target_http:
            return await run_regression(
                request, TracebenchClient(api_http), target_http, factory, None if quiet else _progress
            )

    # Exit code 1 means "regression"; anything that stops the gate from producing a verdict is a 2.
    try:
        outcome = asyncio.run(go())
    except (ApiError, RegressionSetupError) as exc:
        raise _fail(str(exc)) from exc
    except TracebenchError as exc:
        raise _fail(exc.message) from exc
    except Exception as exc:
        raise _fail(f"{type(exc).__name__}: {exc}") from exc

    _print_outcome(outcome)
    if summary_file is not None:
        with summary_file.open("a", encoding="utf-8") as fh:
            fh.write(markdown_summary(outcome, ui_url=ui_url))
    if json_output is not None:
        json_output.write_text(json_summary(outcome), encoding="utf-8")
    raise typer.Exit(0 if outcome.gate.passed else EXIT_REGRESSION)


@datasets_app.command("list")
def datasets_list(api_url: ApiUrl = DEFAULT_API, api_token: ApiToken = None) -> None:
    """List datasets."""

    async def go() -> None:
        async with _api(api_url, api_token) as http:
            rows = await TracebenchClient(http).list_datasets()
        table = Table("name", "version", "items", "updated")
        for d in rows:
            table.add_row(d.name, str(d.version), str(d.item_count), d.updated_at.strftime("%Y-%m-%d %H:%M"))
        out.print(table)

    try:
        asyncio.run(go())
    except ApiError as exc:
        raise _fail(str(exc)) from exc


@datasets_app.command("export")
def datasets_export(
    name: str,
    api_url: ApiUrl = DEFAULT_API,
    api_token: ApiToken = None,
    version: Annotated[int | None, typer.Option(min=0)] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export a dataset version as JSON lines."""

    async def go() -> list[str]:
        async with _api(api_url, api_token) as http:
            client = TracebenchClient(http)
            dataset = await client.dataset_by_name(name)
            if dataset is None:
                raise ApiError(404, f"dataset {name!r} not found")
            snapshot = await client.items(dataset.id, version)
        return [
            json.dumps({"input": i.input, "expected_output": i.expected_output, "metadata": i.metadata})
            for i in snapshot.items
        ]

    try:
        lines = asyncio.run(go())
    except ApiError as exc:
        raise _fail(str(exc)) from exc
    text = "\n".join(lines) + ("\n" if lines else "")
    if output is None:
        sys.stdout.write(text)
    else:
        output.write_text(text, encoding="utf-8")
        console.print(f"wrote {len(lines)} items to {output}")


@datasets_app.command("import")
def datasets_import(
    name: str,
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    api_url: ApiUrl = DEFAULT_API,
    api_token: ApiToken = None,
) -> None:
    """Append items from a JSON lines file (input, expected_output, metadata); creates the dataset if missing."""
    try:
        items = [
            DatasetItemCreate.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except ValueError as exc:
        raise _fail(f"invalid JSON lines file: {exc}") from exc

    async def go() -> None:
        async with _api(api_url, api_token) as http:
            client = TracebenchClient(http)
            dataset = await client.dataset_by_name(name) or await client.create_dataset(name)
            for start in range(0, len(items), MAX_ITEMS_PER_REQUEST):
                await client.add_items(dataset.id, items[start : start + MAX_ITEMS_PER_REQUEST])
        console.print(f"added {len(items)} items to {name}")

    try:
        asyncio.run(go())
    except ApiError as exc:
        raise _fail(str(exc)) from exc


@runs_app.command("compare")
def runs_compare(base: UUID, head: UUID, api_url: ApiUrl = DEFAULT_API, api_token: ApiToken = None) -> None:
    """Show case-level differences between two runs."""

    async def go() -> None:
        async with _api(api_url, api_token) as http:
            diff = await TracebenchClient(http).compare(base, head)
        out.print(f"pass rate change: {diff.pass_rate_delta * 100:+.1f} pp")
        table = Table("status", "item", "base", "head", "output")
        for item in diff.items:
            table.add_row(
                item.status.value,
                str(item.item_key)[:8],
                "-" if item.base_passed is None else ("pass" if item.base_passed else "fail"),
                "-" if item.head_passed is None else ("pass" if item.head_passed else "fail"),
                (item.head_error or as_text(item.head_output))[:80],
            )
        out.print(table)

    try:
        asyncio.run(go())
    except ApiError as exc:
        raise _fail(str(exc)) from exc


@runs_app.command("set-baseline")
def runs_set_baseline(run_id: UUID, api_url: ApiUrl = DEFAULT_API, api_token: ApiToken = None) -> None:
    """Make RUN_ID the baseline for its dataset."""

    async def go() -> None:
        async with _api(api_url, api_token) as http:
            run = await TracebenchClient(http).set_baseline(run_id)
        console.print(f"run {run.id} is now the baseline for {run.dataset_name}")

    try:
        asyncio.run(go())
    except ApiError as exc:
        raise _fail(str(exc)) from exc


if __name__ == "__main__":
    app()
