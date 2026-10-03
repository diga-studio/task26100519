"""密集无套利快照：48 币种、20 供应商、20000 条报价，2256 对查询总耗时 < 15 秒。"""
import random
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from fractions import Fraction

from fxrates import FXCalculator, Quote
from tests.helpers import check_path

D = Decimal
_6DP = D("0.000001")
N_CURRENCIES = 48
N_PROVIDERS = 20
N_QUOTES = 20000
TIME_BUDGET_SECONDS = 15


def dense_arbitrage_free_snapshot(seed: int = 7) -> tuple[list[str], list[Quote]]:
    """每个币种一个内在价值，所有报价围绕一致 mid 上下展开，保证无套利。"""
    rng = random.Random(seed)
    currencies = [f"CCY{k:02d}" for k in range(N_CURRENCIES)]
    providers = [f"PROV{k:02d}" for k in range(N_PROVIDERS)]
    values = {c: rng.uniform(0.3, 3.0) for c in currencies}
    spreads = {p: rng.uniform(0.0005, 0.005) for p in providers}
    pairs = [(a, b) for a in currencies for b in currencies if a != b]
    used: set[tuple[str, str, str]] = set()
    quotes: list[Quote] = []
    while len(quotes) < N_QUOTES:
        base, quote = pairs[rng.randrange(len(pairs))]
        provider = providers[rng.randrange(N_PROVIDERS)]
        if (provider, base, quote) in used:
            continue
        used.add((provider, base, quote))
        mid = D(str(values[quote] / values[base]))
        spread = D(str(spreads[provider]))
        bid = (mid * (1 - spread)).quantize(_6DP, rounding=ROUND_FLOOR)
        ask = (mid * (1 + spread)).quantize(_6DP, rounding=ROUND_CEILING)
        quotes.append(Quote(provider, base, quote, bid, ask))
    return currencies, quotes


def test_dense_snapshot_load_and_all_pairs_query():
    currencies, quotes = dense_arbitrage_free_snapshot()
    assert len(quotes) == N_QUOTES
    calc = FXCalculator()
    start = time.perf_counter()
    calc.load_snapshot(quotes)
    total_legs = 0
    results = {}
    for base in currencies:
        for quote in currencies:
            if base == quote:
                continue
            r = calc.query(base, quote)
            results[(base, quote)] = r
            total_legs += len(r.bid_path) + len(r.ask_path)
            # 路线逐段复算后与返回价格一致（舍入规则）
            bid_exact = check_path(r.bid_path, base, quote)
            ask_exact = check_path(r.ask_path, quote, base)
            assert r.bid == D(
                (bid_exact.numerator * 1_000_000) // bid_exact.denominator
            ).scaleb(-6)
            assert r.ask == D(
                -((-ask_exact.denominator * 1_000_000) // ask_exact.numerator)
            ).scaleb(-6)
    elapsed = time.perf_counter() - start
    assert len(results) == N_CURRENCIES * (N_CURRENCIES - 1) == 2256
    print(f"\nload + 2256 queries: {elapsed:.2f}s, total legs: {total_legs}")
    assert elapsed < TIME_BUDGET_SECONDS
