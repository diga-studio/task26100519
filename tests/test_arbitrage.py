"""套利判定：恰为 1 的环、微小正收益环、与查询不连通的环。"""
from decimal import Decimal
from fractions import Fraction

import pytest

from fxrates import ArbitrageError, FXCalculator, Quote, UnquotableError
from tests.helpers import check_leg

D = Decimal


def test_cycle_product_exactly_one_is_not_arbitrage():
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "A", "B", D("2.000000"), D("2.100000")),
        Quote("p2", "A", "B", D("1.900000"), D("2.000000")),
    ])
    # A->B 经 p1 bid=2，B->A 经 p2 ask=2 -> 环倍率恰为 1
    r = calc.query("A", "B")
    assert r.bid == D("2.000000")
    assert r.ask == D("2.000000")


def test_tiny_positive_cycle_raises_arbitrage():
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "A", "B", D("10000000.000001"), D("10000000.000002")),
        Quote("p2", "A", "B", D("9999999.999998"), D("10000000.000000")),
    ])
    # 环倍率 = 10000000.000001 / 10000000.000000 = 1 + 1e-13，小于万亿分之一但严格为正
    with pytest.raises(ArbitrageError) as excinfo:
        calc.query("A", "B")
    err = excinfo.value
    assert err.product == Fraction(10000000000001, 10000000000000)
    assert err.product > 1
    assert err.product - 1 < Fraction(1, 10**12)
    # 见证环可由原始报价逐段复算
    assert err.cycle[0].from_currency == err.cycle[-1].to_currency
    product = Fraction(1)
    node = err.cycle[0].from_currency
    for leg in err.cycle:
        check_leg(leg)
        assert leg.from_currency == node
        product *= leg.rate
        node = leg.to_currency
    assert node == err.cycle[0].from_currency
    assert product == err.product


def test_arbitrage_applies_even_with_direct_quote():
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "A", "B", D("1.000001"), D("1.000002")),
        Quote("p2", "A", "B", D("0.999999"), D("1.000000")),
    ])
    with pytest.raises(ArbitrageError):
        calc.query("A", "B")
    with pytest.raises(ArbitrageError):
        calc.query("B", "A")


def test_disconnected_profitable_cycle_does_not_affect_query():
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "A", "B", D("1.500000"), D("1.600000")),
        Quote("p2", "C", "D", D("1.000001"), D("1.000002")),
        Quote("p3", "C", "D", D("0.999999"), D("1.000000")),
    ])
    r = calc.query("A", "B")
    assert r.bid == D("1.500000")
    assert r.ask == D("1.600000")


def test_cycle_in_other_component_leaves_unquotable_query_unquotable():
    # C/D 环与 A 连通，但 B 不在该连通分量内：查询 A/B 不可报价而非套利
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "A", "C", D("1.000000"), D("1.000000")),
        Quote("p2", "C", "D", D("1.000001"), D("1.000002")),
        Quote("p3", "C", "D", D("0.999999"), D("1.000000")),
        Quote("p4", "B", "E", D("2.000000"), D("2.000000")),
    ])
    with pytest.raises(UnquotableError):
        calc.query("A", "B")
    # 查询 A/C 与 A/D 应报套利（环可达且能到达目标）
    with pytest.raises(ArbitrageError):
        calc.query("A", "C")
    with pytest.raises(ArbitrageError):
        calc.query("A", "D")
