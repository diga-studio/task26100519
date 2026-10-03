"""路线形态：长链最优路线、快照替换、逐段复算。"""
from decimal import Decimal
from fractions import Fraction

import pytest

from fxrates import FXCalculator, Quote, UnquotableError
from tests.helpers import check_path

D = Decimal


def test_optimal_route_longer_than_ten_legs():
    # C0 -> C1 -> ... -> C12 共 12 段，每段 bid=1.001；直接报价更差
    quotes = []
    for k in range(12):
        quotes.append(Quote(f"p{k}", f"C{k}", f"C{k+1}", D("1.001000"), D("1.002000")))
    quotes.append(Quote("direct", "C0", "C12", D("1.010000"), D("1.020000")))
    calc = FXCalculator()
    calc.load_snapshot(quotes)
    r = calc.query("C0", "C12")
    assert len(r.bid_path) == 12
    expected = Fraction(1001, 1000) ** 12
    assert check_path(r.bid_path, "C0", "C12") == expected
    assert r.bid == D("1.012066")  # floor(1.001^12)
    # 每个中间币种按顺序出现
    assert [leg.from_currency for leg in r.bid_path] == [f"C{k}" for k in range(12)]
    # ask 侧走直接报价的反向（1/1.02 优于 1.002^12 的倒数）
    assert len(r.ask_path) == 1
    assert r.ask == D("1.020000")


def test_snapshot_replacement_invalidates_old_routes():
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("old", "A", "B", D("2.000000"), D("2.000000")),
        Quote("old", "B", "C", D("3.000000"), D("3.000000")),
    ])
    r1 = calc.query("A", "C")
    assert r1.bid == D("6.000000")
    assert all(leg.provider == "old" for leg in r1.bid_path)

    calc.load_snapshot([
        Quote("new", "A", "C", D("5.000000"), D("5.100000")),
        Quote("new", "X", "Y", D("1.000000"), D("1.000000")),
    ])
    r2 = calc.query("A", "C")
    assert r2.bid == D("5.000000")
    assert all(leg.provider == "new" for leg in r2.bid_path)
    # 旧快照的币种不再参与查询
    with pytest.raises(UnquotableError):
        calc.query("A", "B")
    with pytest.raises(UnquotableError):
        calc.query("B", "C")


def test_leg_traceability():
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "EUR", "USD", D("1.100000"), D("1.110000")),
        Quote("p2", "USD", "JPY", D("150.000000"), D("151.000000")),
    ])
    r = calc.query("EUR", "JPY")
    for leg in r.bid_path:
        q = leg.source_quote
        assert leg.provider == q.provider
        # 方向可追溯到原始报价
        assert {leg.from_currency, leg.to_currency} == {q.base, q.quote}
    assert check_path(r.bid_path, "EUR", "JPY") == Fraction(165)
