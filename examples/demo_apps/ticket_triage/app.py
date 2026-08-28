"""Ticket triage: a single structured-output call made with the raw Anthropic SDK.

This is the minimal instrumentation pattern: one CLIENT span per model call carrying the
GenAI semconv request, usage and content attributes.
"""

import random
import re
from typing import Literal

import anthropic
from anthropic.types import MessageParam
from opentelemetry.trace import SpanKind, Tracer
from pydantic import BaseModel, Field

from demo_apps.clock import Clock
from demo_apps.llm import build_message, estimate_tokens, latency_ms
from demo_apps.spans import clocked_span, current_trace_id
from demo_apps.telemetry import record_chat_request, record_chat_response

SYSTEM = (
    "You triage inbound support tickets for Lumen Supply Co. Classify the category, priority and sentiment "
    "and write a one-sentence summary an agent can act on."
)

Category = Literal["shipping", "returns", "product_defect", "billing", "account", "other"]
Priority = Literal["low", "normal", "high", "urgent"]
Sentiment = Literal["negative", "neutral", "positive"]


class Triage(BaseModel):
    category: Category
    priority: Priority
    sentiment: Sentiment
    summary: str = Field(max_length=240)


TRIAGE_SCHEMA = Triage.model_json_schema()

_RULES: list[tuple[Category, tuple[str, ...]]] = [
    ("product_defect", ("broke", "broken", "defect", "ripped", "torn", "leak", "zipper", "stopped working")),
    ("billing", ("charged", "charge", "invoice", "billing", "double", "card", "payment")),
    ("returns", ("return", "refund", "exchange", "send back")),
    ("shipping", ("shipping", "delivery", "package", "tracking", "arrive", "late", "lost")),
    ("account", ("password", "login", "account", "email address", "sign in")),
]
_NEGATIVE = (
    "angry",
    "terrible",
    "unacceptable",
    "worst",
    "frustrated",
    "disappointed",
    "ridiculous",
    "again",
)
_POSITIVE = ("love", "thanks", "great", "awesome", "appreciate")
_URGENT = ("today", "asap", "urgent", "immediately", "trip", "chargeback", "lawyer")


def mock_triage(ticket: str) -> Triage:
    lowered = ticket.lower()
    category: Category = next((c for c, words in _RULES if any(w in lowered for w in words)), "other")
    negative = sum(w in lowered for w in _NEGATIVE)
    sentiment: Sentiment = "negative" if negative else "positive" if any(w in lowered for w in _POSITIVE) else "neutral"
    if any(w in lowered for w in _URGENT):
        priority: Priority = "urgent" if negative or "chargeback" in lowered else "high"
    elif category in {"billing", "product_defect"} or negative:
        priority = "high"
    else:
        priority = "normal" if category != "other" else "low"
    first = re.split(r"(?<=[.!?])\s", ticket.strip())[0]
    summary = f"Customer reports a {category.replace('_', ' ')} issue: {first[:160]}"
    return Triage(category=category, priority=priority, sentiment=sentiment, summary=summary)


class TicketTriager:
    def __init__(
        self,
        tracer: Tracer,
        clock: Clock,
        *,
        model: str,
        client: anthropic.AsyncAnthropic | None,
        capture_content: bool = True,
        rng: random.Random | None = None,
    ) -> None:
        self._tracer = tracer
        self._clock = clock
        self._model = model
        self._client = client
        self._capture = capture_content
        self._rng = rng or random.Random(0)

    async def triage(self, ticket: str) -> tuple[Triage, str]:
        messages: list[MessageParam] = [{"role": "user", "content": ticket}]
        with clocked_span(self._tracer, f"chat {self._model}", self._clock, kind=SpanKind.CLIENT) as span:
            record_chat_request(
                span,
                model=self._model,
                max_tokens=1024,
                system=SYSTEM,
                messages=messages,
                capture_content=self._capture,
            )
            span.set_attribute("gen_ai.output.type", "json")
            if self._client is None:
                result = mock_triage(ticket)
                response = build_message(
                    model=self._model,
                    text=result.model_dump_json(),
                    input_tokens=estimate_tokens(SYSTEM) + estimate_tokens(ticket) + 180,
                )
                await self._clock.sleep_ms(
                    latency_ms(self._model, response.usage.output_tokens, response.usage.input_tokens)
                    * self._rng.uniform(0.8, 1.3)
                )
            else:
                parsed = await self._client.messages.parse(
                    model=self._model, max_tokens=1024, system=SYSTEM, messages=messages, output_format=Triage
                )
                if parsed.parsed_output is None:
                    raise ValueError("model returned no structured triage")
                result = parsed.parsed_output
                response = parsed
            record_chat_response(span, response, capture_content=self._capture)
            span.set_attribute("app.ticket.category", result.category)
            return result, current_trace_id()
