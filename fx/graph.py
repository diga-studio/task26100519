"""Internal exact-arithmetic graph algorithms (not part of the public API)."""
from __future__ import annotations

from fractions import Fraction

from .models import Quote, Side


class Edge:
    """Best available directed conversion between two currency indices."""

    __slots__ = ("src", "dst", "rate", "provider", "side", "bid", "ask")

    def __init__(self, src, dst, rate, provider, side, bid, ask):
        self.src = src
        self.dst = dst
        self.rate = rate
        self.provider = provider
        self.side = side
        self.bid = bid
        self.ask = ask


def build_best_edges(quotes: list[Quote], index: dict[str, int]) -> list[Edge]:
    """Keep only the best-rate edge per ordered currency pair."""
    best: dict[tuple[int, int], Edge] = {}
    for q in quotes:
        a = index[q.base]
        b = index[q.quote]
        for src, dst, rate, side in (
            (a, b, Fraction(q.bid), Side.BID),
            (b, a, 1 / Fraction(q.ask), Side.ASK_INVERSE),
        ):
            key = (src, dst)
            cur = best.get(key)
            if cur is None or rate > cur.rate:
                best[key] = Edge(src, dst, rate, q.provider, side, q.bid, q.ask)
    return list(best.values())


def all_pairs_best(n: int, edges: list[Edge]):
    """Floyd-Warshall max-product with fewest-hop tie-break.

    Returns (rate, hops, nxt) matrices; rate[i][j] is None if unreachable.
    With no positive cycles in the snapshot, rate[i][j] is the exact optimal
    multiplier and nxt supports reconstruction of a route attaining it.
    """
    rate: list[list[Fraction | None]] = [[None] * n for _ in range(n)]
    hops: list[list[int]] = [[0] * n for _ in range(n)]
    nxt: list[list[int | None]] = [[None] * n for _ in range(n)]
    for i in range(n):
        rate[i][i] = Fraction(1)
        nxt[i][i] = i
    for e in edges:
        if rate[e.src][e.dst] is None or e.rate > rate[e.src][e.dst]:
            rate[e.src][e.dst] = e.rate
            hops[e.src][e.dst] = 1
            nxt[e.src][e.dst] = e.dst
    for k in range(n):
        rate_k = rate[k]
        hops_k = hops[k]
        for i in range(n):
            rate_ik = rate[i][k]
            if rate_ik is None:
                continue
            hops_ik = hops[i][k]
            rate_i = rate[i]
            hops_i = hops[i]
            nxt_i = nxt[i]
            nxt_ik = nxt[i][k]
            for j in range(n):
                rate_kj = rate_k[j]
                if rate_kj is None:
                    continue
                cand = rate_ik * rate_kj
                cur = rate_i[j]
                if cur is None or cand > cur:
                    rate_i[j] = cand
                    hops_i[j] = hops_ik + hops_k[j]
                    nxt_i[j] = nxt_ik
                elif cand == cur and hops_ik + hops_k[j] < hops_i[j]:
                    hops_i[j] = hops_ik + hops_k[j]
                    nxt_i[j] = nxt_ik
    return rate, hops, nxt


def reachability(n: int, edges: list[Edge]) -> list[int]:
    """Bitset per node of reachable nodes (including itself)."""
    reach = [1 << i for i in range(n)]
    for e in edges:
        reach[e.src] |= 1 << e.dst
    for k in range(n):
        bit_k = 1 << k
        reach_k = reach[k]
        for i in range(n):
            if reach[i] & bit_k:
                reach[i] |= reach_k
    return reach


def positive_cycle_nodes(rate) -> set[int]:
    """Nodes lying on a closed walk with exact product strictly > 1."""
    n = len(rate)
    return {i for i in range(n) if rate[i][i] is not None and rate[i][i] > 1}


def extract_witness_cycle(n: int, edges: list[Edge], start: int) -> list[Edge]:
    """A simple cycle whose exact product is > 1, reachable from ``start``.

    ``start`` must lie on a positive closed walk. Double-buffered
    Bellman-Ford from ``start`` for n rounds yields a closed walk through
    ``start`` with product > 1; it is then decomposed into simple cycles,
    at least one of which beats 1.
    """
    dist: dict[int, Fraction] = {start: Fraction(1)}
    layers: list[dict[int, Edge]] = []
    for _ in range(n):
        new_dist = dict(dist)
        layer: dict[int, Edge] = {}
        for e in edges:
            d = dist.get(e.src)
            if d is None:
                continue
            cand = d * e.rate
            if e.dst not in new_dist or cand > new_dist[e.dst]:
                new_dist[e.dst] = cand
                layer[e.dst] = e
        layers.append(layer)
        dist = new_dist
    if dist[start] <= 1:
        raise ValueError("no positive closed walk through start")

    # Walk predecessors backwards; update layers strictly decrease, and only
    # ``start`` has an initial distance, so the chain ends at ``start``.
    chain: list[Edge] = []
    node = start
    for t in range(n - 1, -1, -1):
        e = layers[t].get(node)
        if e is None:
            continue
        chain.append(e)
        node = e.src
    if node != start:
        raise ValueError("predecessor chain did not close at start")
    walk = list(reversed(chain))

    # Decompose into simple cycles; the total product exceeds 1, so some
    # simple cycle must exceed 1 as well.
    seq = [start] + [e.dst for e in walk]
    while True:
        seen: dict[int, int] = {}
        cut = None
        for j, v in enumerate(seq):
            if v in seen:
                cut = (seen[v], j)
                break
            seen[v] = j
        if cut is None:
            break
        a, b = cut
        product = Fraction(1)
        for e in walk[a:b]:
            product *= e.rate
        if product > 1:
            return walk[a:b]
        seq = seq[:a] + seq[b:]
        walk = walk[:a] + walk[b:]
    raise ValueError("closed walk decomposition found no positive cycle")
