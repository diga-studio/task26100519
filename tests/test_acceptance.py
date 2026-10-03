"""Acceptance case from the specification, plus reciprocal rounding."""
from decimal import Decimal
from fractions import Fraction

from fx import FxEngine, Quote, Side

D = Decimal


def _engine() -> FxEngine:
    eng = FxEngine()
    eng.load_snapshot(
        [
            Quote("p1", "EUR", "USD", D("1.100000"), D("1.110000")),
            Quote("p1", "USD", "JPY", D("150.000000"), D("151.000000")),
            Quote("p1", "EUR", "JPY", D("164.000000"), D("167.000000")),
        ]
    )
    return eng


def test_eur_jpy_bid_uses_indirect_ask_uses_direct():
    r = _engine().query("EUR", "JPY")
    assert r.bid == D("165.000000")
    assert r.ask == D("167.000000")

    bid_path = [(l.from_ccy, l.to_ccy) for l in r.bid_route.legs]
    assert bid_path == [("EUR", "USD"), ("USD", "JPY")]
    assert all(l.side is Side.BID for l in r.bid_route.legs)
    assert r.bid_route.rate == Fraction(165, 1)

    ask_path = [(l.from_ccy, l.to_ccy) for l in r.ask_route.legs]
    assert ask_path == [("JPY", "EUR")]
    assert r.ask_route.legs[0].side is Side.ASK_INVERSE
    assert r.ask_route.rate == Fraction(1, 167)


def test_reverse_query_reciprocal_and_outward_rounding():
    r = _engine().query("JPY", "EUR")
    # best JPY->EUR is the direct 1/167, rounded DOWN
    assert r.bid == D("0.005988")
    assert r.bid_route.rate == Fraction(1, 167)
    # best EUR->JPY is 165 via EUR->USD->JPY; ask = ceil(1/165)
    assert r.ask == D("0.006061")
    ask_path = [(l.from_ccy, l.to_ccy) for l in r.ask_route.legs]
    assert ask_path == [("EUR", "USD"), ("USD", "JPY")]
    assert r.ask_route.rate == Fraction(165, 1)
