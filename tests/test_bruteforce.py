"""Independent brute-force cross-check on small random snapshots."""
import itertools
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from fx import ArbitrageError, FxEngine, NoRouteError, Quote, Side

D = Decimal
SCALE = 10**6


def _floor6(rate):
    scaled = rate * SCALE
    return D(scaled.numerator // scaled.denominator) / SCALE


def _ceil6(rate):
    scaled = rate * SCALE
    return D(-(-scaled.numerator // scaled.denominator)) / SCALE


def _best_edges(quotes):
    best = {}
    for q in quotes:
        for u, v, r in (
            (q.base, q.quote, Fraction(q.bid)),
            (q.quote, q.base, 1 / Fraction(q.ask)),
        ):
            if r > best.get((u, v), Fraction(0)):
                best[(u, v)] = r
    return best


def _brute_best(best, s, t):
    """Exact max product over simple paths; None if unreachable."""
    nodes = {u for u, _ in best} | {v for _, v in best}
    adj = {c: [] for c in nodes}
    for (u, v), r in best.items():
        adj[u].append((v, r))
    ans = None

    def dfs(node, seen, acc):
        nonlocal ans
        if node == t:
            if ans is None or acc > ans:
                ans = acc
            return
        for v, r in adj[node]:
            if v not in seen:
                dfs(v, seen | {v}, acc * r)

    dfs(s, {s}, Fraction(1))
    return ans


def _brute_cycles(best):
    """All simple cycles (as canonical node tuples) with product > 1."""
    nodes = sorted({u for u, _ in best} | {v for _, v in best})
    adj = {c: [] for c in nodes}
    for (u, v), r in best.items():
        adj[u].append((v, r))
    found = []

    def dfs(start, node, seen, acc):
        for v, r in adj[node]:
            if v == start and len(seen) >= 2:
                if acc * r > 1:
                    found.append(tuple(seen))
            elif v not in seen and v > start:
                dfs(start, v, seen + [v], acc * r)

    for s in nodes:
        dfs(s, s, [s], Fraction(1))
    return found


def _reachable(best, s, t):
    seen = {s}
    stack = [s]
    while stack:
        u = stack.pop()
        for (a, b) in best:
            if a == u and b not in seen:
                seen.add(b)
                stack.append(b)
    return t in seen


def _random_snapshot(rng):
    n = rng.randint(3, 6)
    ccy = [f"C{i}" for i in range(n)]
    providers = [f"p{i}" for i in range(rng.randint(1, 3))]
    quotes = []
    for a, b in itertools.permutations(ccy, 2):
        for p in providers:
            if rng.random() < 0.35:
                bid = D(rng.randint(500000, 2000000)) / SCALE
                ask = bid + D(rng.randint(0, 50000)) / SCALE
                quotes.append(Quote(p, a, b, bid, ask))
    return quotes


def _check_route_legs(route, quotes):
    raw = {(q.provider, q.base, q.quote): q for q in quotes}
    product = Fraction(1)
    for leg in route.legs:
        if leg.side is Side.BID:
            q = raw[(leg.provider, leg.from_ccy, leg.to_ccy)]
            assert leg.rate == Fraction(q.bid)
        else:
            q = raw[(leg.provider, leg.to_ccy, leg.from_ccy)]
            assert leg.rate == 1 / Fraction(q.ask)
        product *= leg.rate
    assert product == route.rate


@pytest.mark.parametrize("seed", range(40))
def test_against_brute_force(seed):
    rng = random.Random(seed)
    quotes = _random_snapshot(rng)
    eng = FxEngine()
    eng.load_snapshot(quotes)
    best = _best_edges(quotes)
    cycles = _brute_cycles(best)
    ccy = sorted({q.base for q in quotes} | {q.quote for q in quotes})

    for s, t in itertools.permutations(ccy, 2):
        # brute-force arbitrage verdict
        arb = any(
            _reachable(best, s, c[0]) and _reachable(best, c[0], t)
            for c in cycles
        )
        if arb:
            with pytest.raises(ArbitrageError) as exc:
                eng.query(s, t)
            _check_route_legs(exc.value.cycle, quotes)
            assert exc.value.cycle.rate > 1
            continue
        fwd = _brute_best(best, s, t)
        rev = _brute_best(best, t, s)
        if fwd is None or rev is None:
            with pytest.raises(NoRouteError):
                eng.query(s, t)
            continue
        r = eng.query(s, t)
        assert r.bid == _floor6(fwd), f"{s}/{t} seed={seed}"
        assert r.ask == _ceil6(1 / rev), f"{s}/{t} seed={seed}"
        assert r.bid_route.rate == fwd
        assert r.ask_route.rate == rev
        _check_route_legs(r.bid_route, quotes)
        _check_route_legs(r.ask_route, quotes)


@pytest.mark.parametrize("seed", range(10))
def test_input_order_invariance(seed):
    rng = random.Random(1000 + seed)
    quotes = _random_snapshot(rng)
    shuffled = quotes[:]
    rng.shuffle(shuffled)

    def conclusions(qs):
        eng = FxEngine()
        eng.load_snapshot(qs)
        best = _best_edges(qs)
        ccy = sorted({q.base for q in qs} | {q.quote for q in qs})
        out = {}
        for s, t in itertools.permutations(ccy, 2):
            try:
                r = eng.query(s, t)
                out[(s, t)] = ("ok", r.bid, r.ask)
            except ArbitrageError:
                out[(s, t)] = ("arb",)
            except NoRouteError:
                out[(s, t)] = ("none",)
        return out

    assert conclusions(quotes) == conclusions(shuffled)
