"""公共类型定义：报价、路线段、查询结果与异常。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction


@dataclass(frozen=True)
class Quote:
    """一条原始报价：一单位 base 对应多少 quote。"""

    provider: str
    base: str
    quote: str
    bid: Decimal
    ask: Decimal


@dataclass(frozen=True)
class Leg:
    """换汇路线的一段：用 provider 的 source_quote 把 from_currency 换成 to_currency。

    rate 为该段的精确倍率（来自 bid 或 1/ask，不舍入）。
    """

    from_currency: str
    to_currency: str
    provider: str
    rate: Fraction
    source_quote: Quote


@dataclass(frozen=True)
class CrossRate:
    """A/B 查询结果。bid 路径为 A->B 路线，ask 路径为 B->A 路线。"""

    base: str
    quote: str
    bid: Decimal
    ask: Decimal
    bid_path: tuple[Leg, ...]
    ask_path: tuple[Leg, ...]


class UnquotableError(Exception):
    """两个币种之间不存在可达路线。"""


class ArbitrageError(Exception):
    """存在与本次查询连通的闭合获利路线。

    cycle 为可由原始报价复算的闭合路线（首尾币种相同），
    product 为该闭合路线的精确倍率（严格大于 1）。
    """

    def __init__(self, base: str, quote: str, cycle: tuple[Leg, ...], product: Fraction):
        self.base = base
        self.quote = quote
        self.cycle = cycle
        self.product = product
        super().__init__(
            f"arbitrage reachable on {base}/{quote}: "
            f"cycle product={float(product)} via "
            + " -> ".join([cycle[0].from_currency] + [leg.to_currency for leg in cycle])
        )
