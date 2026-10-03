# fxrates — FX 交叉汇率计算库

纯 Python、零依赖的进程内交叉汇率库：装载整份报价快照，查询任意两个不同币种之间的
合成 bid/ask 与完整换汇路线；对与查询连通的正收益环返回套利异常。所有选路与套利
判断基于输入十进制的精确值（`fractions.Fraction`），中间步骤不舍入；最终 bid 向下、
ask 向上保留六位小数。

## 环境要求

- Python 3.10+（开发验证于 3.14）
- 运行库本身无第三方依赖；跑测试需要 `pytest`

## 快速开始

```python
from decimal import Decimal
from fxrates import FXCalculator, Quote, ArbitrageError, UnquotableError

calc = FXCalculator()
calc.load_snapshot([
    Quote("p1", "EUR", "USD", Decimal("1.100000"), Decimal("1.110000")),
    Quote("p1", "USD", "JPY", Decimal("150.000000"), Decimal("151.000000")),
    Quote("p1", "EUR", "JPY", Decimal("164.000000"), Decimal("167.000000")),
])

try:
    r = calc.query("EUR", "JPY")
except ArbitrageError as err:
    # err.cycle: 闭合获利路线（Leg 序列，可逐段复算）；err.product: 精确倍率
    ...
except UnquotableError:
    ...  # 无可达路线

r.bid        # Decimal('165.000000')，A->B 最大倍率向下六位
r.ask        # Decimal('167.000000')，B->A 最大倍率的倒数向上六位
r.bid_path   # EUR->USD->JPY 的 Leg 序列（间接路线更优）
r.ask_path   # JPY->EUR 的 Leg 序列（直接报价的反向）
```

每个 `Leg` 携带 `from_currency` / `to_currency` / `provider` / 精确倍率 `rate`
以及原始报价 `source_quote`，可逐段追溯币种、方向与供应商报价。

## 语义要点

- `load_snapshot` 整体替换旧快照；同一有向货币对取各供应商中倍率最大的一条边。
- A/B 报价给出两段倍率：A->B 为 `bid`，B->A 为 `1/ask`；路线倍率为各段乘积。
- 合成 bid 是 A->B 的最大倍率，合成 ask 是 B->A 最大倍率的倒数；两侧路线可不同，
  直接报价参与比较；倍率相同取换汇次数最少者。
- 若存在从 base 可达、且之后仍可到达 quote 的闭合路线且精确倍率严格大于 1，
  查询抛出 `ArbitrageError`（即使有直接报价）；倍率恰为 1 的环不算套利；
  与查询不连通的获利环不影响结果。

## 运行测试

```bash
cd 项目根目录
python3 -m pytest tests/ -q
```

性能验收（48 币种 / 20 供应商 / 20000 条报价的密集无套利快照，装载 + 全部
2256 个有序对查询，含完整路线）：

```bash
python3 -m pytest tests/test_performance.py -q -s
```

本机实测约 0.2 秒（预算 15 秒）。

## 代码结构

- `fxrates/types.py` — `Quote` / `Leg` / `CrossRate` / 异常类型
- `fxrates/graph.py` — 快照折叠为每个有向货币对的最优边
- `fxrates/solver.py` — Floyd-Warshall 全源最优倍率（精确 Fraction）、正收益环标记与环见证提取
- `fxrates/calculator.py` — `FXCalculator` 对外 API、六位小数向外舍入、路径重建
- `tests/` — 验收示例、套利判定、路线形态、随机小图暴力对拍、输入顺序不变性、密集规模性能
