"""Public data model for the FX cross-rate library."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction


class Side(Enum):
    """Which side of a stored quote a route leg consumes."""

    BID = "bid"  # base -> quote at the quoted bid
    ASK_INVERSE = "ask_inverse"  # quote -> base at 1 / ask


@dataclass(frozen=True)
class Quote:
    """One input quote: 1 unit of ``base`` is worth ``bid``/``ask`` of ``quote``."""

    provider: str
    base: str
    quote: str
    bid: Decimal
    ask: Decimal


@dataclass(frozen=True)
class Leg:
    """One conversion step of a route, traceable to an original quote."""

    from_ccy: str
    to_ccy: str
    provider: str
    side: Side
    bid: Decimal
    ask: Decimal
    rate: Fraction  # exact multiplier applied by this leg


@dataclass(frozen=True)
class Route:
    """An ordered list of legs plus the exact overall multiplier."""

    legs: tuple[Leg, ...]
    rate: Fraction  # exact product of leg rates, before any rounding


@dataclass(frozen=True)
class QuoteResult:
    """Synthetic quote for base/quote with witness routes for both sides."""

    base: str
    quote: str
    bid: Decimal  # rounded DOWN to 6 decimals
    ask: Decimal  # rounded UP to 6 decimals
    bid_route: Route  # base -> quote at the pre-rounding optimal rate
    ask_route: Route  # quote -> base; ask == 1 / ask_route.rate rounded up


class FxError(Exception):
    """Base class for library errors."""


class NoRouteError(FxError):
    """Raised when no conversion route exists between the two currencies."""


class ArbitrageError(FxError):
    """Raised when a profitable closed route is reachable and can reach the target."""

    def __init__(self, base: str, quote: str, cycle: Route) -> None:
        self.base = base
        self.quote = quote
        self.cycle = cycle
        super().__init__(
            f"arbitrage on {base}/{quote}: closed route with exact rate "
            f"{float(cycle.rate):.12f} > 1"
        )
