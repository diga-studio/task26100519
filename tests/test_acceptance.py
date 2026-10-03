"""验收示例：EUR/USD、USD/JPY、EUR/JPY 三报价。"""
from decimal import Decimal
from fractions import Fraction

import pytest

from fxrates import FXCalculator, Quote
from tests.helpers import check_path

D = Decimal


def make_calc() -> FXCalculator:
    calc = FXCalculator()
    calc.load_snapshot([
        Quote("p1", "EUR", "USD", D("1.100000"), D("1.110000")),
        Quote("p1", "USD", "JPY", D("150.000000"), D("151.000000")),
        Quote("p1", "EUR", "JPY", D("164.000000"), D("167.000000")),
    ])
    return calc


def test_eur_jpy_bid_uses_indirect_route():
    r = make_calc().query("EUR", "JPY")
    assert r.bid == D("165.000000")
    assert [leg.to_currency for leg in r.bid_path] == ["USD", "JPY"]
    assert check_path(r.bid_path, "EUR", "JPY") == Fraction(165)


def test_eur_jpy_ask_uses_direct_route():
    r = make_calc().query("EUR", "JPY")
    assert r.ask == D("167.000000")
    assert len(r.ask_path) == 1
    leg = r.ask_path[0]
    assert (leg.from_currency, leg.to_currency) == ("JPY", "EUR")
    assert leg.source_quote.base == "EUR" and leg.source_quote.quote == "JPY"
    assert check_path(r.ask_path, "JPY", "EUR") == Fraction(1, 167)


def test_reverse_query_reciprocal_and_outward_rounding():
    r = make_calc().query("JPY", "EUR")
    # 1/167 = 0.00598802... 向下 -> 0.005988
    assert r.bid == D("0.005988")
    # 1/165 = 0.00606060... 向上 -> 0.006061
    assert r.ask == D("0.006061")
    assert check_path(r.bid_path, "JPY", "EUR") == Fraction(1, 167)
    assert check_path(r.ask_path, "EUR", "JPY") == Fraction(165)


def test_same_currency_rejected():
    with pytest.raises(ValueError):
        make_calc().query("EUR", "EUR")
