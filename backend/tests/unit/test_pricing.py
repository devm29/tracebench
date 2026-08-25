from datetime import timedelta
from decimal import Decimal

from tests.factories import T0, model_price, price_version, span, usage
from tracebench.pricing.book import PriceBook, compute_cost
from tracebench.pricing.models import MatchKind


def test_cost_bills_cached_tokens_at_their_own_rate() -> None:
    price = model_price("claude-sonnet-5-5", "2", "10", cache_read_per_mtok="0.20", cache_write_per_mtok="2.50")
    cost = compute_cost(usage(inp=10_000, out=1_000, cache_read=6_000, cache_write=1_000), price)
    # 3k uncached * $2 + 6k cache reads * $0.20 + 1k cache writes * $2.50 + 1k output * $10, per million
    assert cost == Decimal("0.0197")


def test_missing_cache_rates_fall_back_to_input_rate() -> None:
    price = model_price("gpt-4o", "2.5", "10")
    assert compute_cost(usage(inp=1000, cache_read=1000), price) == Decimal("0.0025")


def test_version_effective_at_span_start_is_used() -> None:
    book = PriceBook(
        [
            price_version(1, T0 - timedelta(days=10), [model_price("m", "1", "1")]),
            price_version(2, T0 + timedelta(hours=1), [model_price("m", "2", "2")]),
        ]
    )
    before = book.apply(span("1" * 16, request_model="m", usage=usage(inp=1_000_000)))
    after = book.apply(span("2" * 16, request_model="m", usage=usage(inp=1_000_000), offset_ms=2 * 3600 * 1000))
    assert (before.cost_usd, before.price_version) == (Decimal(1), 1)
    assert (after.cost_usd, after.price_version) == (Decimal(2), 2)


def test_exact_match_beats_prefix_and_longest_prefix_wins() -> None:
    book = PriceBook(
        [
            price_version(
                1,
                T0 - timedelta(days=1),
                [
                    model_price("gpt-4o", "2.5", "10", match=MatchKind.PREFIX),
                    model_price("gpt-4o-mini", "0.15", "0.6", match=MatchKind.PREFIX),
                    model_price("gpt-4o-2024-05-13", "5", "15"),
                ],
            )
        ]
    )
    found = book.lookup("gpt-4o-mini-2024-07-18", T0)
    assert found is not None and found[0].model == "gpt-4o-mini"
    exact = book.lookup("gpt-4o-2024-05-13", T0)
    assert exact is not None and exact[0].input_per_mtok == Decimal(5)


def test_unknown_models_and_spans_before_any_version_are_unpriced() -> None:
    book = PriceBook([price_version(1, T0, [model_price("m", "1", "1")])])
    assert book.apply(span("3" * 16, request_model="other", usage=usage(inp=10))).price_version == 0
    early = span("4" * 16, request_model="m", usage=usage(inp=10), offset_ms=-1000)
    assert book.apply(early).cost_usd == 0
    assert book.apply(span("5" * 16, request_model="m")).price_version == 0


def test_partial_version_inherits_models_it_does_not_list() -> None:
    book = PriceBook(
        [
            price_version(1, T0 - timedelta(days=10), [model_price("a", "1", "1"), model_price("b", "3", "3")]),
            price_version(2, T0 - timedelta(days=1), [model_price("a", "2", "2")]),
        ]
    )
    a = book.apply(span("6" * 16, request_model="a", usage=usage(inp=1_000_000)))
    b = book.apply(span("7" * 16, request_model="b", usage=usage(inp=1_000_000)))
    assert (a.cost_usd, a.price_version) == (Decimal(2), 2)
    assert (b.cost_usd, b.price_version) == (Decimal(3), 2)
    current = book.version_at(T0)
    assert current is not None and [p.model for p in current.prices] == ["a", "b"]
