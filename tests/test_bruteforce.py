"""随机小规模快照：与独立暴力核算逐对比较数值、路径与套利结论。"""
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from fxrates import ArbitrageError, FXCalculator, Quote, UnquotableError
from tests.helpers import (
    brute_force_best,
    brute_force_query_arbitrage,
    check_path,
    directed_edges,
    reachable,
)

D = Decimal
_SCALE = 1_000_000


def floor6(rate: Fraction) -> Decimal:
    return Decimal((rate.numerator * _SCALE) // rate.denominator).scaleb(-6)


def ceil6(rate: Fraction) -> Decimal:
    return Decimal(-((-rate.numerator * _SCALE) // rate.denominator)).scaleb(-6)


def random_snapshot(rng: random.Random) -> list[Quote]:
    currencies = [f"C{k}" for k in range(rng.randint(3, 6))]
    providers = [f"p{k}" for k in range(rng.randint(1, 3))]
    values = {c: rng.uniform(0.5, 2.0) for c in currencies}
    quotes = []
    for _ in range(rng.randint(4, 14)):
        base, quote = rng.sample(currencies, 2)
        provider = rng.choice(providers)
        # 同一供应商同一有向对至多一条
        if any(q.provider == provider and q.base == base and q.quote == quote for q in quotes):
            continue
        # 逐报价抖动 mid，使部分快照出现跨供应商套利环
        mid = values[quote] / values[base] * (1 + rng.uniform(-0.03, 0.03))
        bid = D(str(round(mid * (1 + rng.uniform(-0.005, 0.0)), 6)))
        ask = D(str(round(mid * (1 + rng.uniform(0.0, 0.005)), 6)))
        if bid <= 0 or ask <= 0 or bid > ask:
            continue
        quotes.append(Quote(provider, base, quote, bid, ask))
    return quotes


def check_witness(err: ArbitrageError, edges, src: str, dst: str) -> None:
    assert err.product > 1
    cycle = err.cycle
    assert cycle[0].from_currency == cycle[-1].to_currency
    product = Fraction(1)
    node = cycle[0].from_currency
    nodes_in_cycle = set()
    for leg in cycle:
        assert leg.from_currency == node
        assert leg.rate == edges[(leg.from_currency, leg.to_currency)]
        product *= leg.rate
        node = leg.to_currency
        nodes_in_cycle.add(node)
    assert product == err.product
    # 环可从 src 到达，且之后仍可到达 dst
    from_src = reachable(edges, src)
    assert nodes_in_cycle & from_src
    assert any(dst in reachable(edges, n) for n in nodes_in_cycle)


@pytest.mark.parametrize("seed", range(60))
def test_against_brute_force(seed: int):
    rng = random.Random(seed)
    quotes = random_snapshot(rng)
    if not quotes:
        pytest.skip("empty snapshot")
    edges = directed_edges(quotes)
    currencies = sorted({q.base for q in quotes} | {q.quote for q in quotes})
    calc = FXCalculator()
    calc.load_snapshot(quotes)
    for src in currencies:
        for dst in currencies:
            if src == dst:
                continue
            if brute_force_query_arbitrage(edges, src, dst):
                with pytest.raises(ArbitrageError) as excinfo:
                    calc.query(src, dst)
                check_witness(excinfo.value, edges, src, dst)
                continue
            forward = brute_force_best(edges, src, dst)
            if forward is None:
                with pytest.raises(UnquotableError):
                    calc.query(src, dst)
                continue
            backward = brute_force_best(edges, dst, src)
            assert backward is not None  # 可达性对称
            result = calc.query(src, dst)
            assert result.bid == floor6(forward[0]), (src, dst, seed)
            assert result.ask == ceil6(Fraction(1, 1) / backward[0]), (src, dst, seed)
            # 返回路线逐段复算后等于舍入前的最优倍率，且段数最少
            assert check_path(result.bid_path, src, dst) == forward[0]
            assert len(result.bid_path) == forward[1]
            assert check_path(result.ask_path, dst, src) == backward[0]
            assert len(result.ask_path) == backward[1]


@pytest.mark.parametrize("seed", range(20))
def test_input_order_does_not_change_results(seed: int):
    rng = random.Random(1000 + seed)
    quotes = random_snapshot(rng)
    if not quotes:
        pytest.skip("empty snapshot")
    shuffled = quotes[:]
    rng.shuffle(shuffled)
    currencies = sorted({q.base for q in quotes} | {q.quote for q in quotes})
    results = []
    for snapshot in (quotes, shuffled):
        calc = FXCalculator()
        calc.load_snapshot(snapshot)
        per_pair = {}
        for src in currencies:
            for dst in currencies:
                if src == dst:
                    continue
                try:
                    r = calc.query(src, dst)
                    per_pair[(src, dst)] = ("ok", r.bid, r.ask)
                except ArbitrageError:
                    per_pair[(src, dst)] = ("arb",)
                except UnquotableError:
                    per_pair[(src, dst)] = ("unquotable",)
        results.append(per_pair)
    assert results[0] == results[1]
