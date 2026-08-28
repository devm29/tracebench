import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from anthropic.types import ToolParam

from demo_apps.clock import Clock

TOOLS: list[ToolParam] = [
    {
        "name": "lookup_order",
        "description": "Fetch an order's status, items, carrier and delivery dates by its 5-digit order number.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "5-digit order number"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_policy",
        "description": "Search the help center for store policies (returns, shipping, warranty, exchanges).",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_refund",
        "description": "Issue a refund for a delivered order that is inside the 30-day return window.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["order_id", "reason"],
            "additionalProperties": False,
        },
    },
]

POLICIES: list[dict[str, str]] = [
    {
        "id": "kb-101",
        "title": "Returns and refunds",
        "keywords": "return refund money back window days unworn label",
        "answer": "You can return unused items within 30 days of delivery for a full refund. "
        "Start a return from your order page and we'll email a prepaid label; refunds land 5-7 business days "
        "after the item reaches us.",
    },
    {
        "id": "kb-102",
        "title": "Shipping times",
        "keywords": "shipping ship delivery how long arrive standard express days",
        "answer": "Standard shipping takes 3-5 business days and is free over $75. Express shipping takes "
        "1-2 business days for $14.",
    },
    {
        "id": "kb-103",
        "title": "International orders",
        "keywords": "international internationally country abroad customs duties canada europe uk",
        "answer": "We ship to 38 countries. International orders arrive in 7-12 business days, and duties are "
        "calculated and prepaid at checkout so there are no surprise fees on delivery.",
    },
    {
        "id": "kb-104",
        "title": "Warranty",
        "keywords": "warranty broken defect faulty repair zipper seam guarantee",
        "answer": "All Lumen gear has a 2-year warranty against defects in materials and workmanship. "
        "Send us a photo of the issue and we'll repair or replace the item at no cost.",
    },
    {
        "id": "kb-105",
        "title": "Exchanges",
        "keywords": "exchange size swap different color fit",
        "answer": "Exchanges for a different size or color are free within 30 days. Start the exchange from your "
        "order page and we'll ship the replacement as soon as the original is scanned by the carrier.",
    },
    {
        "id": "kb-106",
        "title": "Price adjustments",
        "keywords": "price drop sale adjustment discount cheaper",
        "answer": "If an item you bought goes on sale within 14 days, contact us and we'll refund the difference "
        "to your original payment method.",
    },
]

_PRODUCTS = [
    ("Ridgeline 40L Pack", 189.00),
    ("Alpine Down Jacket", 279.00),
    ("Trailrunner GTX Shoes", 154.00),
    ("Merino Base Layer", 89.00),
    ("Summit Trekking Poles", 119.00),
    ("Basecamp 2P Tent", 349.00),
    ("Insulated Bottle 1L", 39.00),
    ("Storm Shell Rain Jacket", 219.00),
]
_CARRIERS = ["UPS", "FedEx", "USPS"]


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    status: str
    items: list[str]
    total: float
    carrier: str
    tracking: str
    shipped_on: date | None
    delivered_on: date | None
    eta: date | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status,
            "items": self.items,
            "total": round(self.total, 2),
            "carrier": self.carrier,
            "tracking_number": self.tracking,
            "shipped_on": self.shipped_on.isoformat() if self.shipped_on else None,
            "delivered_on": self.delivered_on.isoformat() if self.delivered_on else None,
            "estimated_delivery": self.eta.isoformat() if self.eta else None,
        }


def build_orders(today: date, count: int = 48) -> dict[str, Order]:
    # Delivery ages avoid the 30-day boundary so refund eligibility is stable for a week of replays.
    rng = random.Random(1729)
    orders: dict[str, Order] = {}
    for index in range(count):
        order_id = str(48100 + index * 37)
        picks = rng.sample(_PRODUCTS, k=rng.choice([1, 1, 2, 3]))
        status = ["delivered", "delivered", "delivered", "shipped", "processing", "delivered_old"][index % 6]
        carrier = rng.choice(_CARRIERS)
        tracking = f"{carrier[:2].upper()}{rng.randint(10**9, 10**10 - 1)}"
        shipped = delivered = eta = None
        if status == "delivered":
            delivered = today - timedelta(days=rng.randint(4, 16))
            shipped = delivered - timedelta(days=rng.randint(2, 4))
        elif status == "delivered_old":
            status = "delivered"
            delivered = today - timedelta(days=rng.randint(48, 90))
            shipped = delivered - timedelta(days=3)
        elif status == "shipped":
            shipped = today - timedelta(days=rng.randint(1, 2))
            eta = today + timedelta(days=rng.randint(2, 4))
        orders[order_id] = Order(
            order_id=order_id,
            status=status,
            items=[name for name, _ in picks],
            total=sum(price for _, price in picks),
            carrier=carrier,
            tracking=tracking,
            shipped_on=shipped,
            delivered_on=delivered,
            eta=eta,
        )
    return orders


class ToolError(RuntimeError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


def search(query: str, limit: int = 2) -> list[dict[str, str]]:
    words = set(query.lower().replace("?", " ").split())
    scored = sorted(
        ((len(words & set(p["keywords"].split())), p) for p in POLICIES),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [{"id": p["id"], "title": p["title"], "text": p["answer"]} for score, p in scored[:limit] if score > 0] or [
        {"id": POLICIES[0]["id"], "title": POLICIES[0]["title"], "text": POLICIES[0]["answer"]}
    ]


class ToolRuntime:
    """Executes the agent's tools against an in-memory store with realistic latency and failures."""

    def __init__(
        self,
        clock: Clock,
        *,
        today: date | None = None,
        failure_rate: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        self._clock = clock
        self._today = today or datetime.now(UTC).date()
        self.orders = build_orders(self._today)
        self.failure_rate = failure_rate
        self._rng = rng or random.Random(0)

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | list[dict[str, str]]:
        match name:
            case "lookup_order":
                await self._clock.sleep_ms(self._rng.uniform(70, 260))
                if self._rng.random() < self.failure_rate:
                    await self._clock.sleep_ms(2500)
                    raise ToolError("TimeoutError", "order service did not respond within 2.5s")
                order = self.orders.get(str(arguments.get("order_id", "")).strip("#"))
                if order is None:
                    raise ToolError("OrderNotFound", f"no order {arguments.get('order_id')!r}")
                return order.as_dict()
            case "search_policy":
                await self._clock.sleep_ms(self._rng.uniform(35, 110))
                return search(str(arguments.get("query", "")))
            case "create_refund":
                await self._clock.sleep_ms(self._rng.uniform(140, 380))
                if self._rng.random() < self.failure_rate / 2:
                    raise ToolError("PaymentGatewayError", "payment provider returned 502")
                order = self.orders.get(str(arguments.get("order_id", "")))
                if order is None or order.delivered_on is None:
                    raise ToolError("NotRefundable", "order has not been delivered")
                if (self._today - order.delivered_on).days > 30:
                    raise ToolError("NotRefundable", "order is outside the 30-day return window")
                refund_id = f"RF-{int(order.order_id) * 7 % 100000:05d}"
                return {
                    "refund_id": refund_id,
                    "order_id": order.order_id,
                    "amount": round(order.total, 2),
                    "status": "issued",
                }
            case _:
                raise ToolError("UnknownTool", f"unknown tool {name}")
