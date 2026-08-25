import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from tracebench.ingest.models import SpanRecord, TokenUsage
from tracebench.pricing.models import MatchKind, ModelPrice, PriceVersion

_MTOK = Decimal(1_000_000)
_QUANTUM = Decimal("0.000000001")


@dataclass(frozen=True, slots=True)
class PricedUsage:
    cost_usd: Decimal
    price_version: int


def compute_cost(usage: TokenUsage, price: ModelPrice) -> Decimal:
    cache_read_rate = price.cache_read_per_mtok if price.cache_read_per_mtok is not None else price.input_per_mtok
    cache_write_rate = price.cache_write_per_mtok if price.cache_write_per_mtok is not None else price.input_per_mtok
    total = (
        usage.uncached_input_tokens * price.input_per_mtok
        + usage.cache_read_tokens * cache_read_rate
        + usage.cache_write_tokens * cache_write_rate
        + usage.output_tokens * price.output_per_mtok
    ) / _MTOK
    return total.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _merge(previous: PriceVersion | None, version: PriceVersion) -> PriceVersion:
    if previous is None:
        return version
    prices = {(p.model, p.match): p for p in previous.prices}
    prices.update({(p.model, p.match): p for p in version.prices})
    return version.model_copy(update={"prices": sorted(prices.values(), key=lambda p: (p.model, p.match))})


class PriceBook:
    """Immutable, time-aware view over all price versions.

    A span is priced with the version that was effective when the span started, so
    a price change never rewrites historical cost. Versions are deltas: a model a
    version does not list keeps the price it had in the version before.
    """

    def __init__(self, versions: Sequence[PriceVersion]) -> None:
        ordered = sorted(versions, key=lambda v: (v.effective_from, v.id))
        self._versions: list[PriceVersion] = []
        for version in ordered:
            self._versions.append(_merge(self._versions[-1] if self._versions else None, version))
        self._starts = [v.effective_from for v in self._versions]

    @property
    def versions(self) -> list[PriceVersion]:
        return list(self._versions)

    def version_at(self, at: datetime) -> PriceVersion | None:
        """The version in effect at `at`, with prices inherited from earlier versions filled in."""
        index = bisect.bisect_right(self._starts, at) - 1
        return self._versions[index] if index >= 0 else None

    def lookup(self, model: str, at: datetime) -> tuple[ModelPrice, PriceVersion] | None:
        if not model:
            return None
        version = self.version_at(at)
        if version is None:
            return None
        exact = next((p for p in version.prices if p.match is MatchKind.EXACT and p.model == model), None)
        if exact is not None:
            return exact, version
        prefixes = [p for p in version.prices if p.match is MatchKind.PREFIX and p.matches(model)]
        if not prefixes:
            return None
        return max(prefixes, key=lambda p: len(p.model)), version

    def price(self, span: SpanRecord) -> PricedUsage:
        if span.usage.total_tokens == 0:
            return PricedUsage(Decimal(0), 0)
        found = self.lookup(span.model, span.start_time)
        if found is None:
            return PricedUsage(Decimal(0), 0)
        model_price, version = found
        return PricedUsage(compute_cost(span.usage, model_price), version.id)

    def apply(self, span: SpanRecord) -> SpanRecord:
        priced = self.price(span)
        if priced.price_version == 0:
            return span
        return span.model_copy(update={"cost_usd": priced.cost_usd, "price_version": priced.price_version})
