"""对外 API：装载快照、查询交叉汇率。"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from fxrates.graph import EdgeIndex, build_edges
from fxrates.solver import Solution, extract_cycle, solve_all_pairs
from fxrates.types import ArbitrageError, CrossRate, Leg, Quote, UnquotableError

_SCALE = 1_000_000


def _floor6(rate: Fraction) -> Decimal:
    """向下保留六位小数。"""
    scaled = (rate.numerator * _SCALE) // rate.denominator
    return Decimal(scaled).scaleb(-6)


def _ceil6(rate: Fraction) -> Decimal:
    """向上保留六位小数。"""
    scaled = -((-rate.numerator * _SCALE) // rate.denominator)
    return Decimal(scaled).scaleb(-6)


class FXCalculator:
    """进程内存中的交叉汇率计算器。调用串行发生。"""

    def __init__(self) -> None:
        self._edges: EdgeIndex | None = None
        self._solution: Solution | None = None
        self._cycle_cache: dict[int, tuple[tuple[Leg, ...], Fraction]] = {}

    def load_snapshot(self, quotes: list[Quote]) -> None:
        """装载整份报价快照，旧快照不再参与查询。"""
        self._edges = build_edges(quotes)
        self._solution = solve_all_pairs(self._edges)
        self._cycle_cache = {}

    def query(self, base: str, quote: str) -> CrossRate:
        """查询 base/quote 的合成 bid/ask 及两侧完整路线。"""
        if self._edges is None or self._solution is None:
            raise RuntimeError("no snapshot loaded")
        if base == quote:
            raise ValueError("base and quote must differ")
        edges = self._edges
        sol = self._solution
        i = edges.index_of.get(base)
        j = edges.index_of.get(quote)
        if i is None or j is None:
            raise UnquotableError(f"unknown currency: {base if i is None else quote}")
        for node in sorted(sol.arb_nodes):
            if sol.rate[i][node] is not None and sol.rate[node][j] is not None:
                cycle, product = self._witness_cycle(node)
                raise ArbitrageError(base, quote, cycle, product)
        if sol.rate[i][j] is None:
            raise UnquotableError(f"no route from {base} to {quote}")
        bid_rate = sol.rate[i][j]
        ask_rate = Fraction(1, 1) / sol.rate[j][i]
        return CrossRate(
            base=base,
            quote=quote,
            bid=_floor6(bid_rate),
            ask=_ceil6(ask_rate),
            bid_path=tuple(self._build_path(i, j)),
            ask_path=tuple(self._build_path(j, i)),
        )

    def _witness_cycle(self, node: int) -> tuple[tuple[Leg, ...], Fraction]:
        cached = self._cycle_cache.get(node)
        if cached is None:
            cycle_edges, product = extract_cycle(self._edges, node)
            legs = tuple(
                self._make_leg(src, dst) for src, dst in cycle_edges
            )
            cached = (legs, product)
            self._cycle_cache[node] = cached
        return cached

    def _make_leg(self, src: int, dst: int) -> Leg:
        edges = self._edges
        source = edges.best_quote[src][dst]
        return Leg(
            from_currency=edges.currencies[src],
            to_currency=edges.currencies[dst],
            provider=source.provider,
            rate=edges.best_rate[src][dst],
            source_quote=source,
        )

    def _build_path(self, start: int, end: int) -> list[Leg]:
        sol = self._solution
        n = len(self._edges.currencies)
        legs: list[Leg] = []
        cur = start
        while cur != end:
            if len(legs) >= n:
                raise RuntimeError("corrupted path reconstruction")
            nxt = sol.next_hop[cur][end]
            legs.append(self._make_leg(cur, nxt))
            cur = nxt
        return legs
