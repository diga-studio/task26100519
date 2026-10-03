"""Route shape: long chains, snapshot replacement, no-route, tie-breaks."""
from decimal import Decimal
from fractions import Fraction

import pytest

from fx import FxEngine, NoRouteError, Quote

D = Decimal


def test_optimal_route_longer_than_ten_legs():
    # chain C0 -> C1 -> ... -> C12, each leg at rate 1.5 (total > 10 legs)
    quotes = []
    for i in range(12):
        quotes.append(Quote("p1", f"C{i}", f"C{i+1}", D("1.500000"), D("1.600000")))
    # a much worse direct quote that must lose
    quotes.append(Quote("p1", "C0", "C12", D("100.000000"), D("200.000000")))
    eng = FxEngine()
    eng.load_snapshot(quotes)
    r = eng.query("C0", "C12")
    assert len(r.bid_route.legs) == 12
    assert r.bid_route.rate == Fraction(3, 2) ** 12
    assert r.bid == D("129.746337")  # floor(1.5^12 * 1e6) / 1e6
    hops = [(l.from_ccy, l.to_ccy) for l in r.bid_route.legs]
    assert hops == [(f"C{i}", f"C{i+1}") for i in range(12)]


def test_snapshot_replacement_invalidates_old_routes():
    eng = FxEngine()
    eng.load_snapshot([Quote("p1", "A", "B", D("2.000000"), D("2.000000"))])
    assert eng.query("A", "B").bid == D("2.000000")
    eng.load_snapshot([Quote("p1", "A", "B", D("3.000000"), D("3.000000"))])
    r = eng.query("A", "B")
    assert r.bid == D("3.000000")
    # old snapshot's currencies must not leak into the new one
    eng.load_snapshot([Quote("p1", "X", "Y", D("1.000000"), D("1.000000"))])
    with pytest.raises(NoRouteError):
        eng.query("A", "B")


def test_no_route():
    eng = FxEngine()
    eng.load_snapshot(
        [
            Quote("p1", "A", "B", D("1.000000"), D("1.000000")),
            Quote("p1", "C", "D", D("1.000000"), D("1.000000")),
        ]
    )
    with pytest.raises(NoRouteError):
        eng.query("A", "C")
    with pytest.raises(NoRouteError):
        eng.query("A", "ZZZ")


def test_same_currency_rejected():
    eng = FxEngine()
    eng.load_snapshot([Quote("p1", "A", "B", D("1.0"), D("1.0"))])
    with pytest.raises(ValueError):
        eng.query("A", "A")


def test_equal_rate_prefers_fewer_hops():
    # direct A->B at 2.0 and two-hop A->M->B at 1.414214^2 ~ 1.99999..: use
    # exact tie instead: A->M 2.0, M->B 1.0 gives exactly 2.0 in 2 hops.
    quotes = [
        Quote("p1", "A", "B", D("2.000000"), D("2.000000")),
        Quote("p1", "A", "M", D("2.000000"), D("2.000000")),
        Quote("p1", "M", "B", D("1.000000"), D("1.000000")),
    ]
    eng = FxEngine()
    eng.load_snapshot(quotes)
    r = eng.query("A", "B")
    assert r.bid_route.rate == Fraction(2)
    assert len(r.bid_route.legs) == 1


def test_best_edge_selected_across_providers():
    quotes = [
        Quote("p1", "A", "B", D("1.900000"), D("2.100000")),
        Quote("p2", "A", "B", D("2.000000"), D("2.200000")),
        Quote("p3", "A", "B", D("1.800000"), D("2.050000")),
    ]
    eng = FxEngine()
    eng.load_snapshot(quotes)
    r = eng.query("A", "B")
    assert r.bid == D("2.000000")
    assert r.bid_route.legs[0].provider == "p2"
    # ask side: B->A best is 1/2.05 (p3) -> ask = 2.05
    assert r.ask == D("2.050000")
    assert r.ask_route.legs[0].provider == "p3"
