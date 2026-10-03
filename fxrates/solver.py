"""全源最优倍率求解与套利检测（精确 Fraction 运算）。"""
from __future__ import annotations

from fractions import Fraction

from fxrates.graph import EdgeIndex


class Solution:
    """全源求解结果。"""

    def __init__(self) -> None:
        self.rate: list[list[Fraction | None]] = []  # 最优倍率，不可达为 None
        self.hops: list[list[int]] = []              # 最优倍率下的最少段数
        self.next_hop: list[list[int]] = []          # 路径重建用下一跳
        self.arb_nodes: set[int] = set()             # 位于正收益环上的币种编号


def solve_all_pairs(edges: EdgeIndex) -> Solution:
    """Floyd-Warshall 求全源最优倍率，并标记正收益环上的节点。

    倍率比较用精确 Fraction；倍率相同取段数更少者。
    """
    n = len(edges.currencies)
    sol = Solution()
    rate: list[list[Fraction | None]] = [[None] * n for _ in range(n)]
    hops = [[0] * n for _ in range(n)]
    next_hop = [[j for j in range(n)] for _ in range(n)]
    for i in range(n):
        rate[i][i] = Fraction(1)
        for j in range(n):
            edge = edges.best_rate[i][j]
            if edge is not None:
                rate[i][j] = edge
                hops[i][j] = 1
    for k in range(n):
        rate_k = rate[k]
        for i in range(n):
            rate_ik = rate[i][k]
            if rate_ik is None:
                continue
            row_i = rate[i]
            hops_i = hops[i]
            for j in range(n):
                rate_kj = rate_k[j]
                if rate_kj is None:
                    continue
                cand = rate_ik * rate_kj
                current = row_i[j]
                cand_hops = hops_i[k] + hops[k][j]
                if current is None or cand > current or (
                    cand == current and cand_hops < hops_i[j]
                ):
                    row_i[j] = cand
                    hops_i[j] = cand_hops
                    next_hop[i][j] = next_hop[i][k]
    sol.rate = rate
    sol.hops = hops
    sol.next_hop = next_hop
    sol.arb_nodes = {i for i in range(n) if rate[i][i] > 1}
    return sol


def extract_cycle(edges: EdgeIndex, start: int) -> tuple[list[tuple[int, int]], Fraction]:
    """从 start 出发用 Bellman-Ford 提取一条经过 start 可达闭环的正收益环。

    返回 (环的有向边序列, 精确倍率)。调用前需保证 start 位于正收益环上。
    """
    n = len(edges.currencies)
    dist: list[Fraction | None] = [None] * n
    pred = [-1] * n
    dist[start] = Fraction(1)
    changed = -1
    for _ in range(n):
        changed = -1
        for u in range(n):
            dist_u = dist[u]
            if dist_u is None:
                continue
            row = edges.best_rate[u]
            for v in range(n):
                edge = row[v]
                if edge is None:
                    continue
                cand = dist_u * edge
                if dist[v] is None or cand > dist[v]:
                    dist[v] = cand
                    pred[v] = u
                    changed = v
        if changed == -1:
            break
    if changed == -1:
        raise RuntimeError("no profitable cycle reachable")
    node = changed
    for _ in range(n):
        node = pred[node]
    cycle_edges: list[tuple[int, int]] = []
    product = Fraction(1)
    cur = node
    while True:
        prev = pred[cur]
        cycle_edges.append((prev, cur))
        product *= edges.best_rate[prev][cur]
        cur = prev
        if cur == node:
            break
    cycle_edges.reverse()
    return cycle_edges, product
