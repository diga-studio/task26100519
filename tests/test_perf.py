"""Dense-scale performance: 48 currencies, 20 providers, 20000 quotes."""
import random
import time
from decimal import Decimal

from fx import FxEngine, Quote, QuoteResult

D = Decimal
SCALE = 10**6


def _dense_snapshot(seed=7):
    rng = random.Random(seed)
    ccy = [f"C{i:02d}" for i in range(48)]
    providers = [f"p{i:02d}" for i in range(20)]
    # latent values keep the snapshot arbitrage-free: spreads >= 0.2% dwarf
    # the <=5e-7 relative rounding of 6-decimal prices.
    latent = {c: rng.uniform(0.5, 200.0) for c in ccy}
    quotes = []
    used = set()
    while len(quotes) < 20000:
        a, b = rng.sample(ccy, 2)
        p = rng.choice(providers)
        if (p, a, b) in used:
            continue
        used.add((p, a, b))
        mid = latent[b] / latent[a]
        spread = rng.uniform(0.002, 0.01)
        bid = D(int(mid * (1 - spread) * SCALE)) / SCALE
        ask = D(int(mid * (1 + spread) * SCALE) + 1) / SCALE
        quotes.append(Quote(p, a, b, bid, ask))
    return quotes, ccy


def test_dense_snapshot_all_pairs_within_budget():
    quotes, ccy = _dense_snapshot()
    assert len(quotes) == 20000
    eng = FxEngine()
    start = time.perf_counter()
    eng.load_snapshot(quotes)
    count = 0
    for a in ccy:
        for b in ccy:
            if a == b:
                continue
            r = eng.query(a, b)
            assert isinstance(r, QuoteResult)
            assert r.bid > 0 and r.ask > 0
            assert r.bid_route.legs and r.ask_route.legs
            count += 1
    elapsed = time.perf_counter() - start
    assert count == 2256
    assert elapsed < 15.0, f"load + {count} queries took {elapsed:.2f}s"
    print(f"\nload + {count} queries: {elapsed:.2f}s")
