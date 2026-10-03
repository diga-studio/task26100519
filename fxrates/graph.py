"""把报价快照折叠成每个有向货币对的最优边。"""
from __future__ import annotations

from fractions import Fraction

from fxrates.types import Quote


class EdgeIndex:
    """币种编号映射 + 每个有向货币对的最优边（倍率最大者）。"""

    def __init__(self) -> None:
        self.currencies: list[str] = []
        self.index_of: dict[str, int] = {}
        # best_rate[i][j]: Fraction 或 None；best_quote[i][j]: 对应该倍率的原始 Quote
        self.best_rate: list[list[Fraction | None]] = []
        self.best_quote: list[list[Quote | None]] = []

    def _intern(self, currency: str) -> int:
        idx = self.index_of.get(currency)
        if idx is None:
            idx = len(self.currencies)
            self.currencies.append(currency)
            self.index_of[currency] = idx
            for row in self.best_rate:
                row.append(None)
            for row in self.best_quote:
                row.append(None)
            self.best_rate.append([None] * (idx + 1))
            self.best_quote.append([None] * (idx + 1))
        return idx

    def _offer(self, src: int, dst: int, rate: Fraction, quote: Quote) -> None:
        current = self.best_rate[src][dst]
        if current is None or rate > current:
            self.best_rate[src][dst] = rate
            self.best_quote[src][dst] = quote


def build_edges(quotes: list[Quote]) -> EdgeIndex:
    """装载整份快照，返回最优边索引。

    A/B 报价给出两条有向边：A->B 倍率为 bid，B->A 倍率为 1/ask。
    同一有向货币对只保留倍率最大的供应商报价。
    """
    edges = EdgeIndex()
    for quote in quotes:
        src = edges._intern(quote.base)
        dst = edges._intern(quote.quote)
        edges._offer(src, dst, Fraction(quote.bid), quote)
        edges._offer(dst, src, Fraction(1, 1) / Fraction(quote.ask), quote)
    return edges
