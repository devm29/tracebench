"""Seeds a running Tracebench with a week of realistic traffic, golden datasets and eval runs.

    python -m demo_apps.seed --api-url http://localhost:8105

Historical traffic is produced by running the real (mock-backed) apps against a virtual clock,
so every trace is exactly what the instrumented code emits, just backdated.
"""

import argparse
import asyncio
import math
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import httpx
from opentelemetry.sdk.trace import TracerProvider

from demo_apps.clock import VirtualClock
from demo_apps.config import DemoSettings, Provider
from demo_apps.seed.docs_qa import docs_qa_trace
from demo_apps.seed.scenarios import SUPPORT_OTHER, SUPPORT_POLICY, SUPPORT_REFUND, SUPPORT_STATUS, TICKETS
from demo_apps.server import create_app
from demo_apps.support_agent.agent import AgentConfig, SupportAgent
from demo_apps.support_agent.mock import MockSupportModel
from demo_apps.support_agent.tools import ToolRuntime, build_orders
from demo_apps.telemetry import create_tracer_provider
from demo_apps.ticket_triage.app import TRIAGE_SCHEMA, TicketTriager
from tracebench.cli.client import ApiError, TracebenchClient, api_client
from tracebench.cli.regression import RegressionRequest, run_regression
from tracebench.config import get_settings
from tracebench.datasets.models import Dataset, DatasetItem, DatasetItemUpdate
from tracebench.evals.embeddings import build_embedder
from tracebench.evals.judges import build_judge
from tracebench.evals.models import EmbeddingSimilaritySpec, ExactMatchSpec, JsonSchemaSpec, LlmJudgeSpec, ScorerSpec
from tracebench.evals.scorers.factory import ScorerFactory
from tracebench.pricing.models import PriceVersionCreate

SUPPORT_DATASET = "support-agent-golden"
TRIAGE_DATASET = "ticket-triage-golden"
DISCOUNT_LABEL = "Committed-use discount (Anthropic)"
DISCOUNTED_MODELS = frozenset({"claude-sonnet-5-5", "claude-haiku-4-5"})

BaselinePolicy = Literal["never", "if-passed", "always"]


@dataclass(frozen=True, slots=True)
class SupportSample:
    trace_id: str
    question: str
    intent: str
    ok: bool
    output: str


@dataclass(frozen=True, slots=True)
class TriageSample:
    trace_id: str
    ticket: str


def log(message: str) -> None:
    print(f"[seed] {message}", flush=True)


def diurnal_weight(ts: datetime) -> float:
    hour = ts.hour + ts.minute / 60
    return 0.25 + float(max(0.0, math.sin((hour - 6) / 16 * math.pi)) ** 1.5)


def sample_starts(rng: random.Random, days: int, per_day: int, now: datetime) -> list[datetime]:
    starts: list[datetime] = []
    begin = now - timedelta(days=days)
    while len(starts) < days * per_day:
        candidate = begin + timedelta(seconds=rng.uniform(0, days * 86400 - 600))
        if rng.random() < diurnal_weight(candidate) / 1.25:
            starts.append(candidate)
    return sorted(starts)


def ns(ts: datetime) -> int:
    return int(ts.timestamp() * 1_000_000_000)


def support_question(rng: random.Random, orders: list[str], old_orders: list[str]) -> str:
    roll = rng.random()
    if roll < 0.32:
        return rng.choice(SUPPORT_STATUS).format(order=rng.choice(orders))
    if roll < 0.58:
        pool = old_orders if rng.random() < 0.15 else orders
        return rng.choice(SUPPORT_REFUND).format(order=rng.choice(pool))
    if roll < 0.92:
        return rng.choice(SUPPORT_POLICY)
    return rng.choice(SUPPORT_OTHER)


async def ensure_discount(api: TracebenchClient, now: datetime) -> None:
    if any(v.label == DISCOUNT_LABEL for v in await api.price_versions()):
        return
    current = await api.current_prices()
    discounted = [
        price.model_copy(
            update={
                field: (value * Decimal("0.8")).quantize(Decimal("0.0001"))
                for field in ("input_per_mtok", "output_per_mtok", "cache_read_per_mtok", "cache_write_per_mtok")
                if (value := getattr(price, field)) is not None
            }
        )
        for price in current.prices
        if price.provider == "anthropic" and price.model in DISCOUNTED_MODELS
    ]
    # Versions are deltas, so listing only the discounted models leaves every other price as is.
    await api.create_price_version(
        PriceVersionCreate(label=DISCOUNT_LABEL, effective_from=now - timedelta(days=2), prices=discounted)
    )
    log("created price version with a 20% committed-use discount, effective two days ago")


async def generate_traffic(
    api_url: str, days: int, scale: float, rng: random.Random
) -> tuple[list[SupportSample], list[TriageSample]]:
    endpoint = f"{api_url.rstrip('/')}/v1/traces"
    providers: list[TracerProvider] = [
        create_tracer_provider(name, endpoint, max_queue_size=200_000)
        for name in ("support-agent", "ticket-triage", "docs-qa")
    ]
    support_tracer, triage_tracer, docs_tracer = (p.get_tracer("demo_apps.seed") for p in providers)
    now = datetime.now(UTC)
    today = now.date()
    orders = build_orders(today)
    recent = [o.order_id for o in orders.values() if o.delivered_on is None or (today - o.delivered_on).days < 30]
    old = [o.order_id for o in orders.values() if o.delivered_on and (today - o.delivered_on).days >= 30]
    incident_start = now - timedelta(days=2, hours=5)
    incident_end = incident_start + timedelta(hours=3)

    support_samples: list[SupportSample] = []
    starts = sample_starts(rng, days, int(60 * scale), now)
    for index, started in enumerate(starts):
        clock = VirtualClock(ns(started))
        in_incident = incident_start <= started <= incident_end
        model = MockSupportModel(clock, overload_rate=0.02, rng=random.Random(rng.random()))
        tools = ToolRuntime(
            clock, today=today, failure_rate=0.45 if in_incident else 0.04, rng=random.Random(rng.random())
        )
        agent_model = "claude-opus-5-5" if rng.random() < 0.12 else "claude-sonnet-5-5"
        agent = SupportAgent(
            model,
            tools,
            support_tracer,
            clock,
            AgentConfig(agent_model=agent_model, router_model="claude-haiku-4-5"),
        )
        session = f"sess_{rng.getrandbits(48):012x}"
        question = support_question(rng, recent, old)
        result = await agent.run([{"role": "user", "content": question}], session_id=session)
        support_samples.append(SupportSample(result.trace_id, question, result.intent, result.ok, result.output))
        if rng.random() < 0.25:
            clock_follow = VirtualClock(clock.now_ns() + int(rng.uniform(60, 600) * 1e9))
            follow = SupportAgent(
                MockSupportModel(clock_follow, rng=random.Random(rng.random())),
                ToolRuntime(clock_follow, today=today, rng=random.Random(rng.random())),
                support_tracer,
                clock_follow,
                AgentConfig(agent_model=agent_model, router_model="claude-haiku-4-5"),
            )
            await follow.run([{"role": "user", "content": rng.choice(SUPPORT_POLICY)}], session_id=session)
        if index % 100 == 0:
            log(f"support-agent: {index}/{len(starts)} traces")

    triage_samples: list[TriageSample] = []
    for started in sample_starts(rng, days, int(36 * scale), now):
        clock = VirtualClock(ns(started))
        model_name = "claude-sonnet-5-5" if rng.random() < 0.1 else "claude-haiku-4-5"
        triager = TicketTriager(triage_tracer, clock, model=model_name, client=None, rng=random.Random(rng.random()))
        ticket = rng.choice(TICKETS)
        _, trace_id = await triager.triage(ticket)
        triage_samples.append(TriageSample(trace_id, ticket))

    for started in sample_starts(rng, days, int(45 * scale), now):
        await docs_qa_trace(docs_tracer, ns(started), random.Random(rng.random()))

    for provider in providers:
        provider.force_flush(timeout_millis=60_000)
        provider.shutdown()
    log(f"sent {len(support_samples)} support, {len(triage_samples)} triage and docs-qa traces")
    return support_samples, triage_samples


async def wait_for_ingest(api: TracebenchClient) -> None:
    for _ in range(60):
        if (await api.health()).ingest.pending == 0:
            await asyncio.sleep(1.5)
            return
        await asyncio.sleep(0.5)


async def ensure_dataset(api: TracebenchClient, name: str, description: str, scorers: list[ScorerSpec]) -> Dataset:
    return await api.dataset_by_name(name) or await api.create_dataset(name, description, scorers)


async def promote(api: TracebenchClient, dataset: str, trace_ids: list[str]) -> list[DatasetItem]:
    items = []
    for trace_id in trace_ids:
        try:
            items.append(await api.promote(trace_id, dataset))
        except ApiError as exc:
            if exc.status != 409:
                log(f"promote {trace_id} failed: {exc}")
    return items


def pick_golden(samples: list[SupportSample]) -> list[str]:
    """Picks a varied golden set: distinct questions, and distinct answer shapes within each intent."""
    chosen: list[str] = []
    questions: set[str] = set()
    shapes: set[tuple[str, str]] = set()
    quotas = {"refund": 5, "order_status": 4, "policy": 6, "other": 1}
    for sample in sorted(samples, key=lambda s: (s.intent != "refund", s.trace_id)):
        skeleton = re.sub(r"\(.*?\)|\$?\d[\d.,]*", "", sample.output)
        shape = (sample.intent, " ".join(skeleton.split()[:4]))
        if not sample.ok or sample.question in questions or quotas.get(sample.intent, 0) <= 0:
            continue
        if shape in shapes and sample.intent in {"refund", "order_status"} and quotas[sample.intent] > 2:
            continue
        quotas[sample.intent] -= 1
        questions.add(sample.question)
        shapes.add(shape)
        chosen.append(sample.trace_id)
    return chosen


async def run_evals(api: TracebenchClient, api_url: str, rng: random.Random) -> None:
    settings = get_settings()
    factory = ScorerFactory(build_embedder(settings), build_judge(settings))
    endpoint = f"{api_url.rstrip('/')}/v1/traces"

    plans: list[tuple[str, str, str, str, BaselinePolicy, str]] = [
        (SUPPORT_DATASET, "/support", "v1", "main", "always", "main: nightly baseline"),
        (TRIAGE_DATASET, "/triage", "v1", "main", "always", "main: nightly baseline"),
        (
            SUPPORT_DATASET,
            "/support",
            "v2",
            "feat/one-line-replies",
            "never",
            "PR #412: one-sentence replies",
        ),
        (SUPPORT_DATASET, "/support", "v1", "fix/refund-copy", "never", "PR #415: restore refund details"),
    ]
    for dataset, path, variant, ref, set_baseline, name in plans:
        app = create_app(
            DemoSettings(
                provider=Provider.MOCK,
                agent_variant=variant,
                mock_latency_scale=0.02,
                otlp_endpoint=endpoint,
            )
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo-app") as target,
        ):
            outcome = await run_regression(
                RegressionRequest(
                    dataset=dataset,
                    target_url=f"http://demo-app{path}",
                    scorers=[],
                    name=name,
                    git_ref=ref,
                    git_sha=f"{rng.getrandbits(160):040x}",
                    set_baseline=set_baseline,
                ),
                api,
                target,
                factory,
            )
        summary = outcome.run.summary
        assert summary is not None
        verdict = "passed" if outcome.gate.passed else "failed: " + "; ".join(outcome.gate.reasons)
        log(f"eval {dataset} ({name}): pass rate {summary.pass_rate:.0%}, gate {verdict}")


async def main_async(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)
    async with api_client(args.api_url, args.api_token, timeout=60) as http:
        api = TracebenchClient(http)
        try:
            await api.health()
        except ApiError as exc:
            log(f"Tracebench API is not reachable at {args.api_url}: {exc}")
            return 1
        now = datetime.now(UTC)
        await ensure_discount(api, now)
        support: list[SupportSample] = []
        triage: list[TriageSample] = []
        if not args.skip_traffic:
            started = time.perf_counter()
            support, triage = await generate_traffic(args.api_url, args.days, args.scale, rng)
            await wait_for_ingest(api)
            log(f"traffic generated in {time.perf_counter() - started:.1f}s")
        if args.skip_evals or not support:
            return 0
        if await api.dataset_by_name(SUPPORT_DATASET) is not None and not args.force:
            log("datasets already exist; pass --force to add more items and runs")
            return 0
        await ensure_dataset(
            api,
            SUPPORT_DATASET,
            "Real support conversations promoted from production traces, curated by the support team.",
            [EmbeddingSimilaritySpec(threshold=0.85), LlmJudgeSpec(threshold=0.6)],
        )
        items = await promote(api, SUPPORT_DATASET, pick_golden(support))
        policy_item = next((i for i in items if "return policy" in str(i.input).lower()), None)
        if policy_item is not None:
            await api.update_item(
                policy_item.dataset_id,
                policy_item.item_key,
                DatasetItemUpdate(metadata={**policy_item.metadata, "reviewed_by": "support-lead"}),
            )
        log(f"promoted {len(items)} support traces into {SUPPORT_DATASET}")

        await ensure_dataset(
            api,
            TRIAGE_DATASET,
            "Ticket triage outputs; the JSON contract is enforced with a schema check.",
            [JsonSchemaSpec.model_validate({"schema": TRIAGE_SCHEMA}), ExactMatchSpec()],
        )
        unique: dict[str, str] = {}
        for sample in triage:
            unique.setdefault(sample.ticket, sample.trace_id)
        triage_items = await promote(api, TRIAGE_DATASET, list(unique.values())[:10])
        log(f"promoted {len(triage_items)} triage traces into {TRIAGE_DATASET}")

        await run_evals(api, args.api_url, rng)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default="http://localhost:8105")
    parser.add_argument("--api-token", default=os.environ.get("TRACEBENCH_API_TOKEN"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--scale", type=float, default=1.0, help="multiplier for traffic volume")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-traffic", action="store_true")
    parser.add_argument("--skip-evals", action="store_true")
    parser.add_argument("--force", action="store_true")
    sys.exit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
