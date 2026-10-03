# fx — 进程内 FX 交叉汇率计算库

纯 Python、零依赖（仅标准库），由上层直接调用。报价快照与计算结果只
保存在进程内存中；所有选路、收益比较与套利判断均基于输入十进制数的
精确值（`fractions.Fraction`），中间换汇步骤不舍入。

## 快速开始

```python
from decimal import Decimal
from fx import FxEngine, Quote, ArbitrageError, NoRouteError

eng = FxEngine()
eng.load_snapshot([
    Quote("p1", "EUR", "USD", Decimal("1.100000"), Decimal("1.110000")),
    Quote("p1", "USD", "JPY", Decimal("150.000000"), Decimal("151.000000")),
    Quote("p1", "EUR", "JPY", Decimal("164.000000"), Decimal("167.000000")),
])

r = eng.query("EUR", "JPY")
r.bid          # Decimal('165.000000')，向下保留六位
r.ask          # Decimal('167.000000')，向上保留六位
r.bid_route    # EUR->USD->JPY，逐段含币种、方向、供应商与原始 bid/ask
r.ask_route    # JPY->EUR 直接路线；ask == 1 / ask_route.rate 向上舍入
```

## API

- `FxEngine.load_snapshot(quotes)`：整份替换快照；旧快照不再参与查询。
  每条 `Quote(provider, base, quote, bid, ask)` 表示一单位 base 对应
  多少 quote，价格为六位小数。同一供应商对同一有向货币对至多一条。
- `FxEngine.query(base, quote)` -> `QuoteResult`：
  - `bid` = base 换 quote 的最大精确倍率，向下保留六位小数；
  - `ask` = quote 换 base 最大精确倍率的倒数，向上保留六位小数；
  - `bid_route` / `ask_route` 为两侧各自的完整换汇路线（`Route.legs`
    逐段给出 `from_ccy`/`to_ccy`/`provider`/`side`/原始 `bid`/`ask` 及
    精确 `rate`），路线对应舍入前的最优倍率；收益相同时换汇次数最少。
- 异常：
  - `ArbitrageError`：存在从 base 可到达、且之后仍可到达 quote 的闭合
    获利路线（精确倍率严格大于 1）。`exc.cycle` 给出可由原始报价复算
    的闭合路线。即使 base/quote 有直接报价也优先返回套利异常。
  - `NoRouteError`：两个方向之一不可达。
  - `ValueError`：base 与 quote 相同。

## 语义要点

- 使用 A/B 报价时，A→B 倍率为 `bid`，B→A 倍率为 `1/ask`；可逐段选用
  不同供应商，不计算手续费、成交量与滑点，不使用 mid。
- 倍率恰好等于 1 的环不是套利；与查询不连通的获利环不影响结果。
- 输入排列顺序不改变最优数值与套利结论（货币按名称排序后计算）。

## 运行测试

```bash
python3 -m pytest tests/ -q
```

覆盖：验收案例（EUR/JPY 合成 bid 走间接、ask 走直接，反向查询遵守
倒数与向外舍入）、倍率恰为 1 的环、收益小于万亿分之一的正环、不连通
获利环、超过 10 段的最优路线、快照替换后旧路线失效、小规模独立暴力
核算（逐段复算路线与价格）、输入顺序不变性，以及 48 币种 / 20 供应商
/ 20000 报价下装载加全部 2256 个有序对查询 < 15 秒（实测约 0.2 秒）。

## 实现说明

- `fx/models.py`：公开数据模型（Quote/Leg/Route/QuoteResult/异常）。
- `fx/graph.py`：内部精确算法——每有向货币对只保留最优边；
  Floyd-Warshall 最大乘积（跳数最少平局）求全对精确倍率与下一跳；
  位集传递闭包求可达性；对角线 `rate[v][v] > 1` 判定正环节点；
  双缓冲 Bellman-Ford 提取闭合路线并分解出简单正环作为套利见证。
- `fx/engine.py`：快照装载与查询编排、六位小数向外舍入。
