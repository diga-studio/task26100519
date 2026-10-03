"""测试辅助：独立暴力核算最优倍率、可达性与套利结论。"""
from __future__ import annotations

from collections import deque
from fractions import Fraction

from fxrates.types import Leg, Quote


def directed_edges(quotes: list[Quote]) -> dict[tuple[str, str], Fraction]:
    """每个有向货币对的最优倍率（与实现无关的独立计算）。"""
    best: dict[tuple[str, str], Fraction] = {}
    for q in quotes:
        fwd = Fraction(q.bid)
        bwd = Fraction(1, 1) / Fraction(q.ask)
        if (q.base, q.quote) not in best or fwd > best[(q.base, q.quote)]:
            best[(q.base, q.quote)] = fwd
        if (q.quote, q.base) not in best or bwd > best[(q.quote, q.base)]:
            best[(q.quote, q.base)] = bwd
    return best


def reachable(edges: dict[tuple[str, str], Fraction], src: str) -> set[str]:
    seen = {src}
    queue = deque([src])
    adjacency: dict[str, list[str]] = {}
    for u, v in edges:
        adjacency.setdefault(u, []).append(v)
    while queue:
        u = queue.popleft()
        for v in adjacency.get(u, []):
            if v not in seen:
                seen.add(v)
                queue.append(v)
    return seen


def brute_force_best(
    edges: dict[tuple[str, str], Fraction], src: str, dst: str
) -> tuple[Fraction, int] | None:
    """枚举全部简单路径，返回 (最大倍率, 该倍率下的最少段数)。"""
    best: tuple[Fraction, int] | None = None

    def dfs(node: str, acc: Fraction, depth: int, visited: set[str]) -> None:
        nonlocal best
        if node == dst:
            if best is None or acc > best[0] or (acc == best[0] and depth < best[1]):
                best = (acc, depth)
            return
        for (u, v), rate in edges.items():
            if u == node and v not in visited:
                visited.add(v)
                dfs(v, acc * rate, depth + 1, visited)
                visited.discard(v)

    dfs(src, Fraction(1), 0, {src})
    return best


def brute_force_cycles(
    edges: dict[tuple[str, str], Fraction]
) -> list[tuple[list[str], Fraction]]:
    """枚举全部简单环及其精确倍率（仅用于小规模）。"""
    nodes = sorted({u for u, _ in edges} | {v for _, v in edges})
    adjacency: dict[str, list[str]] = {}
    for u, v in edges:
        adjacency.setdefault(u, []).append(v)
    cycles: list[tuple[list[str], Fraction]] = []
    for start in nodes:
        stack: list[tuple[str, Fraction]] = [(start, Fraction(1))]
        visited = {start}
        path = [start]

        def dfs(node: str, acc: Fraction) -> None:
            for nxt in adjacency.get(node, []):
                rate = acc * edges[(node, nxt)]
                if nxt == start:
                    cycles.append((path[:], rate))
                elif nxt not in visited and nxt >= start:
                    visited.add(nxt)
                    path.append(nxt)
                    dfs(nxt, rate)
                    path.pop()
                    visited.discard(nxt)

        dfs(start, Fraction(1))
    return cycles


def brute_force_query_arbitrage(
    edges: dict[tuple[str, str], Fraction], src: str, dst: str
) -> bool:
    """是否存在从 src 可达、且之后仍可到达 dst 的正收益环。"""
    from_src = reachable(edges, src)
    all_nodes = {u for u, _ in edges} | {v for _, v in edges}
    to_dst = {node for node in all_nodes if dst in reachable(edges, node)}
    for nodes, product in brute_force_cycles(edges):
        if product > 1 and any(n in from_src and n in to_dst for n in nodes):
            return True
    return False


def check_leg(leg: Leg) -> None:
    """逐段校验：方向、供应商报价与倍率一致。"""
    q = leg.source_quote
    assert leg.provider == q.provider
    if q.base == leg.from_currency and q.quote == leg.to_currency:
        assert leg.rate == Fraction(q.bid)
    elif q.base == leg.to_currency and q.quote == leg.from_currency:
        assert leg.rate == Fraction(1, 1) / Fraction(q.ask)
    else:
        raise AssertionError(f"leg currencies do not match quote: {leg}")


def check_path(legs: tuple[Leg, ...], src: str, dst: str) -> Fraction:
    """逐段复算路线倍率，校验首尾衔接。"""
    product = Fraction(1)
    node = src
    for leg in legs:
        check_leg(leg)
        assert leg.from_currency == node
        product *= leg.rate
        node = leg.to_currency
    assert node == dst
    return product
