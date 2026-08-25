"""A deterministic stand-in for Claude that drives the support agent without an API key.

It reads the same MessageParam history the real model would see and answers with real
SDK Message objects, including tool_use blocks, so the agent loop and its telemetry are
exercised exactly as in production.
"""

import json
import random
import re
from datetime import date
from typing import Any

from anthropic.types import Message, MessageParam, ToolParam

from demo_apps.clock import Clock
from demo_apps.llm import TransientModelError, build_message, estimate_tokens, latency_ms
from demo_apps.support_agent.prompts import ROUTER_SYSTEM
from demo_apps.telemetry import block_dict

ORDER_ID = re.compile(r"#?\b(\d{5})\b")
_REFUND_WORDS = ("refund", "return", "money back", "send it back", "send back")
_STATUS_WORDS = ("where", "track", "status", "arrive", "shipped", "deliver", "late", "hasn't come")
_POLICY_WORDS = (
    "policy", "shipping", "warranty", "exchange", "international", "customs", "how long", "price",
    "sale", "broken", "defect", "size",
)  # fmt: skip
_TOOLS_TOKENS = 460


def classify(text: str) -> str:
    lowered = text.lower()
    has_order = ORDER_ID.search(text) is not None
    if any(w in lowered for w in _REFUND_WORDS) and has_order:
        return "refund"
    if has_order or any(w in lowered for w in _STATUS_WORDS[:3]):
        return "order_status" if has_order else "other"
    if any(w in lowered for w in _POLICY_WORDS) or any(w in lowered for w in _REFUND_WORDS):
        return "policy"
    return "other"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        data = block_dict(block)
        if data.get("type") == "text":
            parts.append(data["text"])
    return " ".join(parts)


def _tool_results(message: MessageParam) -> list[dict[str, Any]]:
    content = message["content"]
    if isinstance(content, str):
        return []
    return [d for d in (block_dict(b) for b in content) if d.get("type") == "tool_result"]


def _tool_uses(messages: list[MessageParam]) -> dict[str, tuple[str, dict[str, Any]]]:
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    for message in messages:
        if message["role"] != "assistant" or isinstance(message["content"], str):
            continue
        for block in message["content"]:
            data = block_dict(block)
            if data.get("type") == "tool_use":
                calls[data["id"]] = (data["name"], data["input"])
    return calls


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _human_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}"


class MockSupportModel:
    def __init__(
        self,
        clock: Clock,
        *,
        variant: str = "v1",
        overload_rate: float = 0.0,
        rng: random.Random | None = None,
    ):
        self._clock = clock
        self._variant = variant
        self._overload_rate = overload_rate
        self._rng = rng or random.Random(0)

    async def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[MessageParam],
        tools: list[ToolParam] | None = None,
    ) -> Message:
        prompt_tokens = estimate_tokens(system) + sum(estimate_tokens(m["content"]) for m in messages)
        if tools:
            prompt_tokens += _TOOLS_TOKENS
        if self._rng.random() < self._overload_rate:
            await self._clock.sleep_ms(self._rng.uniform(80, 400))
            raise TransientModelError("overloaded_error", "Overloaded")
        cached = estimate_tokens(system) + _TOOLS_TOKENS if tools and len(messages) > 1 else 0
        if system == ROUTER_SYSTEM:
            response = build_message(
                model=model, text=classify(_text_of(messages[-1]["content"])), input_tokens=prompt_tokens
            )
        else:
            response = self._agent_turn(model, messages, prompt_tokens, cached)
        await self._clock.sleep_ms(
            latency_ms(model, response.usage.output_tokens, prompt_tokens) * self._rng.uniform(0.75, 1.45)
        )
        return response

    def _agent_turn(self, model: str, messages: list[MessageParam], prompt_tokens: int, cached: int) -> Message:
        question = next(
            _text_of(m["content"]) for m in reversed(messages) if m["role"] == "user" and not _tool_results(m)
        )
        intent = classify(question)
        order_match = ORDER_ID.search(question)
        order_id = order_match.group(1) if order_match else None
        uses = _tool_uses(messages)
        last = messages[-1]
        results = _tool_results(last) if last["role"] == "user" else []

        def reply(text: str) -> Message:
            return build_message(model=model, text=text, input_tokens=prompt_tokens, cache_read_tokens=cached)

        def call(name: str, arguments: dict[str, Any], preface: str | None = None) -> Message:
            return build_message(
                model=model,
                text=preface,
                tool_calls=[(name, arguments)],
                input_tokens=prompt_tokens,
                cache_read_tokens=cached,
            )

        if not results:
            if intent in {"refund", "order_status"} and order_id:
                return call("lookup_order", {"order_id": order_id}, "Let me pull up that order.")
            if intent == "policy":
                return call("search_policy", {"query": question})
            if intent == "refund" or "order" in question.lower():
                return reply("I can help with that. What's your 5-digit order number? It's in your confirmation email.")
            return reply(
                "I can help with order tracking, returns and refunds, shipping and warranty questions. "
                "What can I do for you?"
            )

        result = results[-1]
        tool_name, arguments = uses.get(result["tool_use_id"], ("", {}))
        payload_raw = result.get("content", "")
        failed = bool(result.get("is_error"))
        lookups = sum(1 for name, _ in uses.values() if name == "lookup_order")

        if tool_name == "lookup_order":
            if failed:
                if "OrderNotFound" in str(payload_raw):
                    return reply(f"I couldn't find an order numbered {order_id}. Could you double-check the number?")
                if lookups < 2:
                    return call("lookup_order", arguments, "That timed out, trying once more.")
                return reply(
                    "I'm having trouble reaching our order system right now. Please try again in a few minutes, "
                    "or reply here and a teammate will follow up by email."
                )
            order = json.loads(str(payload_raw))
            if intent == "refund":
                if order["status"] != "delivered":
                    return reply(
                        f"Order {order['order_id']} hasn't been delivered yet, so it can't be refunded. "
                        "Once it arrives you'll have 30 days to start a return."
                    )
                return call("create_refund", {"order_id": order["order_id"], "reason": "customer request"})
            return reply(self._status_text(order))

        if tool_name == "create_refund":
            if failed:
                if "outside the 30-day" in str(payload_raw):
                    return reply(
                        f"Order {arguments.get('order_id')} was delivered more than 30 days ago, so it's outside our "
                        "return window. If the item is defective, our 2-year warranty still covers it."
                    )
                return reply(
                    "The refund didn't go through on our side. I've flagged it and a teammate will email you today."
                )
            refund = json.loads(str(payload_raw))
            if self._variant == "v2":
                return reply("Done, your refund request has been submitted.")
            return reply(
                f"I've issued a refund of {_money(refund['amount'])} for order {refund['order_id']} "
                f"(refund {refund['refund_id']}). It will reach your original payment method in 5-7 business days."
            )

        if tool_name == "search_policy":
            articles = json.loads(str(payload_raw))
            best = articles[0]
            if self._variant == "v2":
                return reply(best["text"].split(". ")[0] + ".")
            return reply(best["text"])

        return reply("Sorry, something went wrong on my side. Could you rephrase that?")

    @staticmethod
    def _status_text(order: dict[str, Any]) -> str:
        items = ", ".join(order["items"])
        match order["status"]:
            case "shipped":
                return (
                    f"Order {order['order_id']} ({items}) shipped with {order['carrier']} and should arrive by "
                    f"{_human_date(order['estimated_delivery'])}. Tracking number: {order['tracking_number']}."
                )
            case "delivered":
                return (
                    f"Order {order['order_id']} ({items}) was delivered on {_human_date(order['delivered_on'])} "
                    f"via {order['carrier']}."
                )
            case _:
                return f"Order {order['order_id']} ({items}) is being packed and will ship within 1 business day."
