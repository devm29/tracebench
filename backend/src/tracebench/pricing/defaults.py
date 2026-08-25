from datetime import UTC, datetime
from decimal import Decimal

from tracebench.pricing.models import MatchKind, ModelPrice, PriceVersionCreate


def _p(
    provider: str,
    model: str,
    inp: str,
    out: str,
    cache_read: str | None = None,
    cache_write: str | None = None,
    match: MatchKind = MatchKind.EXACT,
) -> ModelPrice:
    return ModelPrice(
        provider=provider,
        model=model,
        match=match,
        input_per_mtok=Decimal(inp),
        output_per_mtok=Decimal(out),
        cache_read_per_mtok=Decimal(cache_read) if cache_read else None,
        cache_write_per_mtok=Decimal(cache_write) if cache_write else None,
    )


DEFAULT_PRICES = PriceVersionCreate(
    label="List prices",
    effective_from=datetime(2024, 1, 1, tzinfo=UTC),
    prices=[
        _p("anthropic", "claude-opus-5-5", "4", "20", "0.20", "5"),
        _p("anthropic", "claude-opus-5", "5", "25", "0.50", "6.25"),
        _p("anthropic", "claude-sonnet-5-5", "2", "10", "0.20", "2.50"),
        _p("anthropic", "claude-sonnet-5", "2", "10", "0.20", "2.50"),
        _p("anthropic", "claude-sonnet-4-6", "3", "15", "0.30", "3.75"),
        _p("anthropic", "claude-haiku-4-5", "1", "5", "0.10", "1.25", MatchKind.PREFIX),
        _p("anthropic", "claude-opus-4", "5", "25", "0.50", "6.25", MatchKind.PREFIX),
        _p("openai", "gpt-4o", "2.50", "10", "1.25", None, MatchKind.PREFIX),
        _p("openai", "gpt-4o-mini", "0.15", "0.60", "0.075", None, MatchKind.PREFIX),
        _p("openai", "text-embedding-3-small", "0.02", "0"),
    ],
)
