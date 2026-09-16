# debit_card_specializing （5 表） · simple EX 79.1% (34/43)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

1. **时间条件可能落两张表**：`yearmonth.Date` 是 `'YYYYMM'`（2011–2013 月度）、
   `transactions_1k.Date` 是 `'YYYY-MM-DD'`（只有 2012-08 四天）。两者范围不重叠，
   问 2013 年的交易 → 金标常硬连 `yearmonth` 与 `transactions_1k`。
2. **`Price` 是单价**，交易总额 = `Amount * Price`；月度消费看 `yearmonth.Consumption`（一人一月一行）。
3. `Currency` 只有 `'CZK'`/`'EUR'`；`customers.Segment` 是 `LAM`/`SME`/`KAM`；
   加油站 `Country` 用 `'CZE'`；"premium/value for money" 在 `gasstations.Segment`。

## 连接图与坑

```
customers ──CustomerID──┐
                        ├── transactions_1k（Date 'YYYY-MM-DD'，只有 2012-08 四天）
gasstations ─GasStationID┘   └── products
yearmonth ──CustomerID──── customers（Date 'YYYYMM'，覆盖 2011-2013）
```
- **时间条件可能落在 `yearmonth`**（月度）或 `transactions_1k`（日度）；两者数据范围不重叠。
  问 2013 年的交易 → 金标常用 `yearmonth` 硬连 `transactions_1k`（见 A8）。
- 消费额 `yearmonth.Consumption`（一人一月一行）；交易金额 = `Amount * Price`
  （`Price` 是单价，不是总价）。
- `Currency` 只有 `'CZK'` / `'EUR'`；`Segment` 是 `LAM`/`SME`/`KAM`。

⚠️ **日度交易在 `transactions_1k`，不是 `transactions`**（实测 `1511`/`1512`/`1524`）：
- 库里只有 `customers / gasstations / products / transactions_1k / yearmonth`
- `yearmonth.Date` **只有月度**（`'YYYY-MM'`）→ 题干给到具体某一天（如 `2012/8/25`）时必须用
  `transactions_1k`（列：`TransactionID, Date, Time, CustomerID, CardID, GasStationID, ProductID, Amount, Price`）
- 我写 `FROM transactions` 直接 `no such table`，用 `yearmonth` 查某天 → **0 行**（空集是硬触发器）
- `gasstations.Segment` 取值只有：`Value for money` / `Premium` / `Other` / `Noname` / `Discount`
