"""Arbitrage detection: exact-zero, tiny-positive, disconnected, unreachable."""
from decimal import Decimal
from fractions import Fraction

import pytest

from fx import ArbitrageError, FxEngine, Quote, Side

D = Decimal


def _check_witness(cycle, quotes_by_pair):
    """Closed loop, product > 1, every leg recomputable from raw quotes."""
    legs = cycle.legs
    assert len(legs) >= 2
    assert legs[0].from_ccy == legs[-1].to_ccy
    for prev, cur in zip(legs, legs[1:]):
        assert prev.to_ccy == cur.from_ccy
    product = Fraction(1)
    for leg in legs:
        if leg.side is Side.BID:
            q = quotes_by_pair[(leg.provider, leg.from_ccy, leg.to_ccy)]
            assert leg.bid == q.bid and leg.rate == Fraction(q.bid)
        else:
            q = quotes_by_pair[(leg.provider, leg.to_ccy, leg.from_ccy)]
            assert leg.ask == q.ask and leg.rate == 1 / Fraction(q.ask)
        product *= leg.rate
    assert product == cycle.rate
    assert cycle.rate > 1


def _quote_map(quotes):
    return {(q.provider, q.base, q.quote): q for q in quotes}


def test_cycle_exactly_one_is_not_arbitrage():
    eng = FxEngine()
    quotes = [
        Quote("p1", "A", "B", D("1.100000"), D("1.100001")),
        Quote("p1", "B", "C", D("1.200000"), D("1.200001")),
        Quote("p1", "A", "C", D("1.320000"), D("1.320000")),
    ]
    eng.load_snapshot(quotes)
    # A->B->C->A = 1.1 * 1.2 / 1.32 == 1 exactly: normal quote expected.
    r = eng.query("A", "C")
    assert r.bid == D("1.320000")
    assert r.ask == D("1.320000")


def test_tiny_positive_cycle_triggers_arbitrage():
    # product = 1.000001^2 / 1.000002 = 1 + 1/1000002000000 (>1, gain < 1e-12)
    quotes = [
        Quote("p1", "A", "B", D("1.000001"), D("1.000001")),
        Quote("p1", "B", "C", D("1.000001"), D("1.000001")),
        Quote("p1", "A", "C", D("0.999998"), D("1.000002")),
    ]
    eng = FxEngine()
    eng.load_snapshot(quotes)
    with pytest.raises(ArbitrageError) as exc:
        eng.query("A", "B")
    cycle = exc.value.cycle
    _check_witness(cycle, _quote_map(quotes))
    assert cycle.rate == Fraction(1000001**2, 1000002 * 10**6)
    assert 0 < cycle.rate - 1 < Fraction(1, 10**12)


def test_disconnected_profitable_cycle_does_not_affect_query():
    quotes = [
        # profitable cycle X->Y->Z->X, disconnected from A/B
        Quote("p1", "X", "Y", D("1.100000"), D("1.100000")),
        Quote("p1", "Y", "Z", D("1.100000"), D("1.100000")),
        Quote("p1", "X", "Z", D("1.100000"), D("1.100000")),
        Quote("p2", "A", "B", D("2.000000"), D("2.000000")),
    ]
    eng = FxEngine()
    eng.load_snapshot(quotes)
    r = eng.query("A", "B")
    assert r.bid == D("2.000000")
    assert r.ask == D("2.000000")


def test_cycle_reaches_target_via_reverse_edges():
    # Every quote creates both directed edges, so the profitable C1/C2 cycle
    # can return to A (reverse of A/C1) and continue to T: arbitrage applies.
    quotes = [
        Quote("p1", "C1", "C2", D("1.100000"), D("1.100000")),
        Quote("p1", "C2", "C1", D("1.000000"), D("1.000000")),
        Quote("p1", "A", "C1", D("1.000000"), D("1.000000")),
        Quote("p1", "A", "T", D("3.000000"), D("3.000000")),
        Quote("p1", "T", "A", D("0.300000"), D("0.300000")),
    ]
    eng = FxEngine()
    eng.load_snapshot(quotes)
    with pytest.raises(ArbitrageError) as exc:
        eng.query("A", "T")
    _check_witness(exc.value.cycle, _quote_map(quotes))
    # a query disconnected from the cycle is unaffected
    quotes2 = quotes + [Quote("p2", "U", "V", D("5.000000"), D("5.000000"))]
    eng.load_snapshot(quotes2)
    assert eng.query("U", "V").bid == D("5.000000")
    with pytest.raises(ArbitrageError):
        eng.query("A", "C2")


def test_arbitrage_applies_even_with_direct_quote():
    quotes = [
        Quote("p1", "A", "B", D("1.100000"), D("1.100000")),
        Quote("p1", "B", "A", D("0.910000"), D("0.910000")),
    ]
    eng = FxEngine()
    eng.load_snapshot(quotes)
    # 1.1 * 0.91 = 1.001 > 1 despite the direct A/B quote
    with pytest.raises(ArbitrageError) as exc:
        eng.query("A", "B")
    _check_witness(exc.value.cycle, _quote_map(quotes))
