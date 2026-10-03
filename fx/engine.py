"""FxEngine: snapshot loading and cross-rate queries."""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from . import graph
from .models import (
    ArbitrageError,
    Leg,
    NoRouteError,
    Quote,
    QuoteResult,
    Route,
)

_SCALE = 10**6


def _floor6(rate: Fraction) -> Decimal:
    scaled = rate * _SCALE
    return Decimal(scaled.numerator // scaled.denominator) / _SCALE


def _ceil6(rate: Fraction) -> Decimal:
    scaled = rate * _SCALE
    return Decimal(-(-scaled.numerator // scaled.denominator)) / _SCALE


class FxEngine:
    """In-memory FX cross-rate calculator. Calls are expected to be serial."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._index: dict[str, int] = {}
        self._currencies: list[str] = []
        self._edges: list[graph.Edge] = []
        self._edge_map: dict[tuple[int, int], graph.Edge] = {}
        self._rate = None
        self._nxt = None
        self._reach: list[int] = []
        self._cycle_nodes: set[int] = set()
        self._witness_cache: dict[int, Route] = {}

    def load_snapshot(self, quotes: list[Quote]) -> None:
        """Replace any previous snapshot with the given full quote set."""
        self._reset()
        self._currencies = sorted({q.base for q in quotes} | {q.quote for q in quotes})
        self._index = {c: i for i, c in enumerate(self._currencies)}
        n = len(self._currencies)
        self._edges = graph.build_best_edges(quotes, self._index)
        self._edge_map = {(e.src, e.dst): e for e in self._edges}
        self._rate, _hops, self._nxt = graph.all_pairs_best(n, self._edges)
        self._reach = graph.reachability(n, self._edges)
        self._cycle_nodes = graph.positive_cycle_nodes(self._rate)

    def _build_route(self, src: int, dst: int) -> Route:
        legs: list[Leg] = []
        rate = Fraction(1)
        node = src
        while node != dst:
            nxt = self._nxt[node][dst]
            if nxt is None:
                raise NoRouteError("route reconstruction failed")
            e = self._edge_map[(node, nxt)]
            legs.append(
                Leg(
                    from_ccy=self._currencies[e.src],
                    to_ccy=self._currencies[e.dst],
                    provider=e.provider,
                    side=e.side,
                    bid=e.bid,
                    ask=e.ask,
                    rate=e.rate,
                )
            )
            rate *= e.rate
            node = nxt
        return Route(legs=tuple(legs), rate=rate)

    def _witness_route(self, start: int) -> Route:
        cached = self._witness_cache.get(start)
        if cached is not None:
            return cached
        cycle_edges = graph.extract_witness_cycle(
            len(self._currencies), self._edges, start
        )
        legs = tuple(
            Leg(
                from_ccy=self._currencies[e.src],
                to_ccy=self._currencies[e.dst],
                provider=e.provider,
                side=e.side,
                bid=e.bid,
                ask=e.ask,
                rate=e.rate,
            )
            for e in cycle_edges
        )
        rate = Fraction(1)
        for e in cycle_edges:
            rate *= e.rate
        route = Route(legs=legs, rate=rate)
        self._witness_cache[start] = route
        return route

    def query(self, base: str, quote: str) -> QuoteResult:
        """Synthetic quote for base/quote.

        Raises ArbitrageError if a profitable closed route is reachable from
        ``base`` and can still reach ``quote``; NoRouteError if unreachable.
        """
        if base == quote:
            raise ValueError("base and quote currencies must differ")
        i = self._index.get(base)
        j = self._index.get(quote)
        if i is None or j is None:
            raise NoRouteError(f"unknown currency in {base}/{quote}")

        for c in sorted(self._cycle_nodes):
            if (self._reach[i] >> c) & 1 and (self._reach[c] >> j) & 1:
                raise ArbitrageError(base, quote, self._witness_route(c))

        if self._rate[i][j] is None or self._rate[j][i] is None:
            raise NoRouteError(f"no route for {base}/{quote}")

        bid_route = self._build_route(i, j)
        ask_route = self._build_route(j, i)
        return QuoteResult(
            base=base,
            quote=quote,
            bid=_floor6(bid_route.rate),
            ask=_ceil6(1 / ask_route.rate),
            bid_route=bid_route,
            ask_route=ask_route,
        )
