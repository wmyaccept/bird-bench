# SQLite 方言、脏数据、大 schema

## 一、SQLite 方言（Mini-Dev 的 SQLite 版和 MySQL/PostgreSQL 版不同）

| 需求 | SQLite 写法 | 不要用 |
|---|---|---|
| 条件求和 | `SUM(IIF(cond, 1, 0))` 或 `SUM(CASE WHEN cond THEN 1 ELSE 0 END)` | `SUM(IF(...))` 只有 MySQL 有 |
| 转浮点 | `CAST(x AS FLOAT)` / `CAST(x AS REAL)` | PostgreSQL 的 `::float` |
| 取子串 | `SUBSTR(s, 1, 4)` | `LEFT(s,4)`（SQLite 没有） |
| 日期年 | `SUBSTR(Date, 1, 4)` 或 `STRFTIME('%Y', Date)` | `YEAR(Date)` / `EXTRACT(...)` |
| 字符串拼接 | `a \|\| b` | `CONCAT(a,b)` |
| 除零 | `CAST(a AS FLOAT) / NULLIF(b, 0)` | 直接相除 |
| 去重计数 | `COUNT(DISTINCT x)` | — |
| 窗口函数 | 支持 `RANK() / ROW_NUMBER() / ROW_NUMBER() OVER (PARTITION BY ...)` | — |
| 取极值所在行 | `WHERE col = (SELECT MAX(col) FROM t)`（返回全部并列）<br>或 `ORDER BY col DESC LIMIT 1`（只返回一行） | — |
| 看列类型 | `SELECT TYPEOF(col), COUNT(*) FROM t GROUP BY 1` | — |
| 看表结构 | `SELECT name, type FROM pragma_table_info('t')` | — |

**⚠️ NULL 在排序里是最小值 —— `ORDER BY col ASC LIMIT 1` 会命中 NULL 行**
（实测踩过 `dev idx 663`）：`users.Age` 里有大量 NULL，“最年轻的用户”写成
`ORDER BY Age ASC LIMIT 1` 返回的是 `Id = -1`（Age 为 NULL），不是真正的 13 岁用户（`Id = 805`）。

| 写法 | 结果 |
|---|---|
| `ORDER BY Age ASC LIMIT 1` | ❌ 命中 Age=NULL 的行 |
| `WHERE Age = (SELECT MIN(Age) FROM users)` | ✅ NULL 被 MIN 忽略 |
| `WHERE Age IS NOT NULL ORDER BY Age ASC LIMIT 1` | ✅ |

⇒ 取“最小/最年轻/最早”时，**首选 `WHERE col = (SELECT MIN(col) ...)`**，不要靠 `ORDER BY ASC LIMIT 1`。
反向的 `MAX` / `ORDER BY DESC` 一般安全（NULL 排最后），但统一用 `MIN/MAX` 子查询最稳。

**整数除法陷阱**：`1/2` 在 SQLite 里等于 `0`。算比率、平均值、百分比时一定要先把一边
`CAST(... AS FLOAT)`。

**保留字坑**：`between`、`order`、`group`、`left`、`index` 等不能直接当别名，
别名踩到保留字会报 `near "...": syntax error`（实测踩过）。

**SUM/COUNT 混用的分母**：`SUM(x)*1.0/COUNT(*)` 与 `AVG(x)` 不等价——
`AVG` 忽略 NULL，`COUNT(*)` 不忽略。`idx 283` 的 evidence 明写
"DIVIDE(SUM(height_cm), COUNT(all heros))"，答案就是 `SUM/COUNT(*)` 而不是 `AVG`。

## 二、脏数据（BIRD 三大难点之一）

库里的值是真实世界抓来的，格式不统一。**写 SQL 前先去现场看一眼实际长什么样**：

```sql
SELECT DISTINCT status FROM ...                             -- 'Finished' / 'finished' / 'DNF ' ?
SELECT DISTINCT Date FROM ...                               -- 格式有几种？
SELECT TYPEOF(col), COUNT(*), COUNT(col) FROM ... GROUP BY TYPEOF(col)
                                                            -- 混着 TEXT 和 INTEGER？NULL 占比多少？
```

已知的实测例子：

- `european_football_2.Player.birthday` 是 TEXT：`'1992-02-29 00:00:00'` → 取年月用 `SUBSTR(birthday, 1, 7)`。
- `formula_1.qualifying.q2` 是 TEXT 的 `'1:34.188'`，且**大量 NULL**；
  字典序和数值序在这里恰好一致，但 NULL 排序的坑见 `gold-style.md` 第 3 条。
- `formula_1.results.position` 对退赛车手是 **NULL**（不是 0）→ 数"完赛/未完赛"
  要用 `time IS NULL` 或 `position IS NOT NULL`，别用 `= 0`。
- `thrombosis_prediction.Laboratory.IGG`：13,908 行里有 11,228 行是 NULL，只有 2,680 行有值；
  整个 `Laboratory` 表只覆盖 302 个患者（`Patient` 有 1238 个）。
- `superhero.superhero.full_name` 有 122 行是 NULL、**另有 125 行是字符串 `'-'`**
  —— "没有名字"有两种写法。
- `debit_card_specializing.transactions_1k` 只覆盖 **2012-08-23 ~ 08-26** 四天（1000 行）；
  问 2013 年交易的题目在这个库里**根本没有数据**（金标往往是空集或靠别的表硬连）。
- 有的字段是**同一个词的变体**：`'School Appropration'`（拼错）、`'Sander Boschker'` 这类大小写、
  名字里的变音符（`'Räikkönen'`）。

## 三、大 schema

单个库可能上百列（`european_football_2.Match` 有 115 列，`card_games.cards` 有 74 列）。
别一上来全读，用 `bird_schema` 逐层收敛：

```
先看表名和行数  →  猜候选表  →  只看候选表的列  →  再试跑
```

**先搞清连接键**：见 [`naming-traps.md`](naming-traps.md) 第四节（多套 ID 体系）。

## 四、evidence 的用法（BIRD 三大难点之二）

evidence 可能补充：计算口径、单位换算、字段业务含义、阈值、值的拆解规则。
**把 evidence 当成题面的一部分**，它说的口径要一字不差地落到 SQL 里。
漏读 evidence 是 BIRD 上最常见的失分原因。

但它也会错 —— 因为它是对着金标 SQL **事后生成**的：

✅ `idx 205` 的 evidence 写的是 `track number less than **10** refers to position < **20**`，
而题干问的是 `track number less than **20**` —— 前后一个 10 一个 20，**evidence 自己就是错的**。

用法总结：

- **数字/阈值会错，甚至和题干矛盾** → 以题干为准。
- 但它提到的**列名、表名、函数名仍是有用线索** → 说明金标 SQL 里确实出现了那个东西。
  `idx 205` 里的 "position" 不是凭空来的，只是它属于 `driverStandings` 而不是 `results`。
- 它也会**漏掉**金标实际没用、但题干写了的条件（见 `gold-style.md` 第 4 条）。

> 把 evidence 当"**金标 SQL 的一份不准的摘要**"来读，而不是当权威定义。
