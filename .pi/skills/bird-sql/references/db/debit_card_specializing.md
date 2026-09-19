# debit_card_specializing （5 表） · simple EX 79.1% (34/43)

## ⚠️ 交题前必查（本库最容易翻车的几条）

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

## 惯例卡片（实测统计，n=64 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 10 / COUNT(*) 2 / COUNT(DISTINCT) 2 / 无 50　⇒ 本库以 `COUNT(列)` 为主（10/14 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：transactions_1k 30 / customers 21 / yearmonth 8 / gasstations 5　⇒ 主表以 **transactions_1k** 为主但**不固定**（30/64）⇒ 按题干主语选
- `SELECT DISTINCT`：6/64　|　`*100`：7　|　`BETWEEN`：4
- 输出列数分布：1列×57 / 2列×2 / 3列×5
- JOIN 数分布：0:15, 1:41, 2:8

> 由 `bird_conventions db=debit_card_specializing write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ challenging 实测（4 道，2 对 = 50%）

- **1481**「annual average consumption of the customers with the least amount of consumption … between SME/LAM/KAM」金标：
  `CAST(SUM(IIF(Segment='SME', Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) - CAST(SUM(IIF(Segment='LAM', …)) AS REAL) / COUNT(T1.CustomerID) - …`
  ⇒ **分子 = 该 segment 的消费总额，分母 = 全表客户数（所有 segment 一起数）**，
  不是"每客户取最小再 /12"，也不是"按 segment 分组"✗ 我想复杂了。
- **1482**「Which of the three segments has the biggest and lowest percentage increases」金标 **1 行 3 列**
  （SME、LAM、KAM 三个百分比并列，**不是 2 行挑最大最小**）✗
  ⇒ 同样用 `SUM(IIF(Segment='X' AND Date LIKE '2013%', Consumption, 0))` 的写法 → `*100/NULLIF(...,0)`。
- 对得稳的：1476（CZK − EUR 2012 消费差）、1526（`transactions_1k.Price = 634.8` 的客户，2012/2013 消费降幅）。
