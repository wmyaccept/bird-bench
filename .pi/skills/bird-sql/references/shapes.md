# 题型骨架（拿到题先认类型）

> **配套**：具体某个库的连接图与坑 → [`db/<db_id>.md`](db/)（**只读当前库那一个文件**）。
> 写 SQL 时的通用陷阱 → [`traps.md`](traps.md)。提交前 → [`checklist.md`](checklist.md)。

---

<!-- push step=2 -->
## A. 拿到题先做的固定动作（30 秒决策）

```
1. 读 evidence        → 它常直接给出：口径、阈值、列名、单位
2. 认出题型            → 从下表选骨架（A 部分）
3. 确定"一行代表什么"   → 决定 行级 vs 实体级（见 A3/A4）
4. 查日期/值格式        → bird_schema table=... 看 samples（见 A7）
5. 选输出列            → id 还是 name？（见 A5）
6. 写完先跑一遍         → 空集？行数合理？再提交
```

**注意**：Dev 的题目**按数据库聚集**（一个库几十道连在一起）。所以进一个库时先把
**当前库的档案 `db/<db_id>.md`** 读一遍，后面几十题都能复用。

⚠️ **换库的第一件事：把关键列的取值 `SELECT DISTINCT` 看一眼。**
每一库的“值风格”不同，凭印象写必错（实测两边都踩过）：

| 库 | 坑 | 实测 |
|---|---|---|
| card_games | 首字母大写 | `status='restricted'` → **0 行**；`'Restricted'` → 636 |
| california_schools | 小写 f | `'Directly funded'`（不是 `'Funded'`） |

同理，**列名也要先核实**（evidence 里的概念名未必是列名，见 `db/card_games.md`）。

---
<!-- /push -->

## A1. 单属性查询 —— "What is the ⟨属性⟩ of the ⟨实体⟩ that ⟨条件⟩?"

最常见的一类。骨架就是"沿外键走，取目标列"。

```sql
SELECT 目标列
FROM 主表 A
JOIN 维表 B ON A.外键 = B.主键
WHERE ⟨实体条件⟩;
```

判断顺序：**目标列在哪张表 → 需要几跳 JOIN → 条件列在哪张表**。
实测：`dev idx 3`（unabbreviated mailing street）、`idx 10`（FRPM %）、`idx 19`（phone）。

## A2. 极值 + 属性 —— "⟨属性⟩ of the 最高/最低 ⟨指标⟩ 的实体"

```sql
-- 先试这个（金标最常用，且能自然处理"并列只取一个"）
SELECT 目标列 FROM ... ORDER BY 指标 DESC LIMIT 1;

-- 若上面的行数不对，改这个（返回全部并列）
SELECT 目标列 FROM ... WHERE 指标 = (SELECT MAX(指标) FROM ...);
```

⚠️ 三个必查（`gold-style.md` / `sqlite-and-data.md` 有实测案例）：
- **该列有 NULL 吗？**（`SELECT COUNT(*) FROM t WHERE col IS NULL`）SQLite 里 NULL 最小，
  `ORDER BY col ASC LIMIT 1` 会取到 NULL 行（实测 `dev idx 663`：`users.Age` 大量 NULL，
  最年轻用户写到 `Id=-1`）。⇒ 取最小/最早首选 `WHERE col = (SELECT MIN(col) ...)`。
- **并列有几个？**（`SELECT COUNT(*) FROM t WHERE 指标 = MAX`）
- **“最高”是不是要先聚合？** 见 A3。

## A3. 时间维度的极值 —— 题干出现"某年/某月" + "最…"

**先问一句：是不是要先按实体/月份汇总再取极值？** 这是踩过两次的坑。

```sql
-- ❌ 单行极值
SELECT MAX( Consumption ) FROM yearmonth WHERE SUBSTR(Date,1,4)='2012'
-- ✅ 先按月份汇总，再取最大月
SELECT MAX(total) FROM (SELECT SUM(Consumption) AS total FROM yearmonth
                        WHERE SUBSTR(Date,1,4)='2012' GROUP BY Date)
```

实测：`minidev idx 13`（最高月消费 → 按月汇总）、`idx 1`（某年消费最少 → 按客户汇总全年）。
**触发词**："某年的最高月 X"、"某年消费最少的客户"、"年级平均分"、"每场比赛的观众数"。

## A4. 计数 —— "How many ⟨实体⟩ ⟨条件⟩?"

**唯一的决策点：数实体还是数记录？**

| 题干主语 | 先试 | 例子 |
|---|---|---|
| "how many schools/customers/users"（数实体） | `COUNT(DISTINCT 实体ID)` | `dev idx 5` |
| "how many transactions/comments/attendance"（数记录） | `COUNT(*)` | `idx 29`（"give their Y" 也是行级） |

判错了的表现是"1 行 1 列但取值不同"（差 1、差几十）。**先试行级，错了换实体级**——
实测 gold 更常用行级（`minidev idx 16`、`idx 24`、`idx 26`）。

## A5. 列表类 —— "List the ⟨列⟩ of ⟨实体⟩"

两个决策点：

1. **输出哪一列？** 用金标行数反推：
   ```sql
   SELECT COUNT(DISTINCT 候选列) FROM ... WHERE ⟨条件⟩   -- 哪个等于金标行数就是它
   ```
   实测 `idx 346`：金标 25061 行，`name` 只有 17544 个不同值 ⇒ 金标给的是 `id`。
   **"which cards / which posts" 这类，金标常常给 id 而不是 name。**
2. **要不要带上实体的 id？** 题干 "give their Y" → **只给 Y**，别顺手带 id（实测 `idx 29`）。
3. `DISTINCT` 不影响判定，但**影响你发现行数不一致**——先按行级写，不行再加。

## A6. 占比 / 比率 —— "percentage / ratio / proportion"

```sql
SELECT CAST(分子 AS FLOAT) * 100 / 分母 FROM ...      -- 百分比
SELECT CAST(分子 AS FLOAT) / 分母 FROM ...             -- 比率
```

- **整数除法陷阱**：`1/2` = 0，必须 CAST。
- **分母口径**：先试**行数**（`COUNT(*)` / `SUM(CASE WHEN cond THEN 1 ELSE 0 END)`），
  失败再换**去重实体数**。实测 `minidev idx 24`、`idx 26` 都是行数口径。
- 有时是"两个子查询相除/相减"：`SELECT (SELECT ...) / (SELECT ...)`。
- 要求保留小数位时用 `ROUND(x, 3)`（实测 `minidev idx 413`）。

### ⚠️ SQLite 陷阱：双引号包一个**不存在的列名不会报错**

```sql
SELECT schools."Low Grade" FROM schools LIMIT 1;   -- 不报错！返回字符串 'Low Grade' 本身
```

SQLite 把 `"xxx"` 当不了列名时就当**字符串字面量**。所以"用引号试一下列存不存在"会**静默返回常量**，
而不是报错。这个坑实测踩过（以为 `Low Grade` 在 `schools`，实际在 `frpm`，结果是 17686 行全是 'Low Grade'）。

**防范**：列名（尤其带空格/括号的）先用 `pragma_table_info` 列一遍再写：

```sql
SELECT name FROM pragma_table_info('frpm');
```

### A7. 日期与"脏值" —— 每条 SQL 之前都该扫一眼

```sql
SELECT DISTINCT Date FROM t LIMIT 5;                        -- 格式长什么样
SELECT TYPEOF(col), COUNT(*), COUNT(col) FROM t GROUP BY 1; -- 有没有混类型/NULL
```

已知格式：

| 库/列 | 格式 | 正确写法 |
|---|---|---|
| `debit_card.yearmonth.Date` | `'201202'` | `SUBSTR(Date,1,4)='2012'`、`Date BETWEEN '201301' AND '201312'` |
| `debit_card.transactions_1k.Date` | `'2012-08-25'` | `Date > '2012-01-01'` |
| `european_football_2.Player.birthday` | `'1992-02-29 00:00:00'` | `SUBSTR(birthday,1,7)='1970-10'` |
| `formula_1.races.date` | `'2005-09-04'` | `LIKE '2005-09%'` |
| `codebase_community.users.CreationDate` | `'2011-08-01 14:00:00'` | `LIKE '2011%'` |
| `student_club.event.event_date` | `'2019-09-03T12:00:00'` | `LIKE '2019-10-08%'` |

**SQLite 没有 `YEAR()`/`MONTH()`**，用 `SUBSTR` 或 `STRFTIME`。

## A8. 条件在表 A、结果列在表 B ⇒ 用共同外键硬连

题干给的条件落在某张表，而要输出的列在另一张表，且两表**没有直接外键**时，
金标会用它们**共有的那个 key** 连过去（哪怕语义上不自然）。

实测 `minidev idx 14`：时间条件在 `yearmonth`，商品描述在 `products`，
金标用两表共有的 `CustomerID` 连到 `transactions_1k` 再连 `products`。
`dev idx 15` 同型。

**反推方法**：金标行数是已知的，把候选 JOIN 路径的行数各算一遍，命中那个数就锁定了。

## A9. 差值 / 比较 —— "difference between A and B"、"Did X?"

```sql
-- 差/比值：两个子查询
SELECT (SELECT ... ) - (SELECT ...);
-- 比较两个实体：排序后取第一个
SELECT 名字 FROM t WHERE 名字 IN ('A','B') ORDER BY 指标 DESC LIMIT 1;
-- 是/否类：金标往往返回"被问的那个属性值"而不是 True/False
```

实测 `minidev idx 9`（多少家之差）、`idx 38`（两年支出之差）、`idx 146`（谁更老）。

## A10. 排名 —— 题干出现 "rank / top N"

- **top N**：`ORDER BY 指标 DESC LIMIT N`
- **rank 列**：金标可能把 `RANK() OVER (ORDER BY 指标 DESC)` **作为输出列**（`minidev idx 441`）
- 别忘了 `LIMIT` 之前先确认排序键和并列情况。

---

## A11. 多维度 Profile —— 题干出现 "comprehensive profile / overall statistics / segmented by"

> ★ **这是新版 dev2025 新增的主力题型**（旧版 simple 被改写后大量变成它，多为 challenging）。
> 🔴 **做题顺序：改写题里先做 `difficulty=='simple'` 的（实测 86% 对），
> 这些 challenging 的 Profile 题放最后做（实测 5% 对）。**
> 实测 5 道（financial 92/96/97/103/104）：**行数/粒度大多对，但金标列数是我猜的 2–3 倍**。

**先定粒度（这部分容易对）：**

| 题干信号 | 粒度 |
|---|---|
| "overall statistics" | **聚合成 1 行**（我给了 21 行 → 金标 **1 行**） |
| "segmented by / breakdown by X, Y, Z" | `GROUP BY X, Y, Z`（我 `GROUP BY` 对了 → 行数刚好 30/14） |
| "ranked by … within …" | `ROW_NUMBER/RANK() OVER (PARTITION BY …)`，但**行数不变** |

**再定列数（这部分是失分主因，已实测）—— 必须先交出一张「属性清单」，再写 SQL。**

> 🔴 **实测（dev2025 全量已答 1112 道）：列数错 103 道，其中 85 道是我「少给列」——61 道是 challenging，
> 金标 9–21 列而我给了 1 列。这不是「读不到金标」，而是读题阶段**没有把题干属性变成产物**。**

**⛳ 落笔前的硬产物：属性清单**（写在作答推理里，写在 `/* shape: … */` 之前）

```
属性清单（列数 = 清单行数）：
| 题干属性词        | 取值来源（表.列）        |
|------------------|--------------------------|
| name             | clients.client_name      |
| loan statistics  | → loan_count, total_amount, avg_amount, status（4 列） |
| …                | …                        |
```

- **列数 = 清单行数**（词袋型维度按展开后的列数算）。
- 写完 SQL 回头数一遍：`SELECT` 里的列数 **<** 清单行数 ⇒ **回去补列，别交**。
- 这一步**只在题干侧、不依赖金标** —— 是「少列」这类错唯一能在落笔前自检的地方。
- ⭐ **它现在是机器闸门**：清单原样写进 `answer --attrs "属性1|属性2|…"`（每条抄题干原文片段，
  **条数必须 == SELECT 列数**），且列数不得低于 `bird.py attrs <idx>` 报出的**列数下界**（闸门 4）。
  先看先验再写 SQL：`attrs` 会摆出“同模板已提交题给了几列”与“本库×难度金标列数分布”。
- checklist 第 1 条 / 第 13b 条就是这个自检（**都是核心条目**）。

金标会把每个维度「展开」成多个字段：

实测的金标列数 —— 都远超“一个维度一个值”的直觉：

| idx | 题干里的维度 | 我给的列 | **金标列数** |
|---|---|---|---|
| 96 | 3 个分段 + financial profile | 6 | **11** |
| 97 | loan + transaction + card + usage | 7 | **18** |
| 103 | personal + banking + loan + district | 11 | **14** |
| 104 | 7 个具体概念 | 7 | **14** |

⇒ **动作：题干里每出现一个维度，就把该维度在这张表里能拿到的字段都列上**。
例如：
- "loan statistics" → `loan_count` + `total_amount` + `avg_amount` + `status`（不是只给一个 count）
- "transaction activity" → `trans_count` + `total_volume` + `income` + `expense` + `first_date` + `last_date`
- "credit card information" → `card_count` + `card_type` + `issued`
- "personal information" → `client_id` + `gender` + `birth_date`（+ 算出来的 age）

**辅助特征**：
- 条件多且互相嵌套（"average salary between 6,000 and 10,000, ranking in the top 3 **within their region**, having at least 5 female clients"）
  → 用 CTE 分层：先筛 → 再窗口函数排名 → 再过滤。
- evidence 常直接定义**分类规则**（"Young borrower means age < 30 with at least one loan"）
  → 分类列用 `CASE WHEN`，名字题里怎么写就怎么写（`'Young borrower'` / `'Mature borrower'`）。
- ⚠️ 这类题**列数几乎无法精确猜中**，先把粒度做对、再把字段尽量展开，剩下的靠复盘积累。

### 📊 实测校准（两批 11 道，dev2025）

**① 粒度（行数）是能练对的：**

| 题干信号 | 实测 |
|---|---|
| “overall/comprehensive **statistics**” | **聚合成 1 行**（92: 我 21 行→金标 1 行；111: 我 6 行→金标 1 行） |
| “**segmented/breakdown** by X,Y,Z” | `GROUP BY` 后行数刚好对（96: 30=30） |
| “for **each**/all accounts …” | 行级，我 55 行 = 金标 55 行 ✓（121） |

**② 列数：分两种题干形态，差异极大（第三版，实测 16 道）**

| 题干形态 | 列数规律 | 实测 |
|---|---|---|
| **“including A, B, C, and D”**（列举**具体概念**） | **精确 = 列举个数**，多给反而错 | 134: 题干列了 6 个（name/region/population/crimes/pct increase/accounts）→ 金标 **正好 6 列**（我给了 8 → 错） |
| **“including client demographics, transaction activity, …”**（**维度词组**） | 每个维度展开 **3-5 列** | 127: 4 个维度 → 金标 **21 列**（我只给了 14） |

⇒ **动作：先数字符串里的概念个数。**
- 能数出**具体名词**（name / region / count / ratio / status）→ **一个名词一列，不要自行添加 id**。
- 数不出（demographics / activity / details / profile 这种“词袋”）→ 把该维度在表里能拿的字段**尽可能铺开**。

其它实测差数：122 (18→15)、124 (13→**17**)、126 (8→**9**)、105 (11→15)、112 (9→14)。

**③ 粒度（第四版，已验证稳）**：16 道里行数全对的占多数，再确认一遍信号：

| 题干信号 | 粒度 |
|---|---|
| “overall/comprehensive **statistics**” | **聚合成 1 行**（92、111） |
| “for loan ID X / for the client who …”（单实体） | **1 行** |
| “**segmented/breakdown** by X,Y,Z” | `GROUP BY X,Y,Z`（96: 30 行 ✓） |
| “for accounts with … / for all …” | 行级（124: 122 行 ✓；127: 4167 行 ✓；121: 55 行 ✓） |
| “**top N … in each district**” | `ROW_NUMBER() OVER (PARTITION BY district_id ORDER BY amount DESC)` 后取 `<= N`（124 ✓） |

**⑤ EX 判定是 `set(预测) == set(金标)`（官方 + 本地同口径）—— 列数必须精确相等。**

⇒ **不存在“多给几列保险”这回事**：多给、少给、换顺序都是 0 分。
⇒ 所以 A11 的动作顺序是：**先把粒度做对（已能稳），再押列集合**；
   列集合押不中就一个字都不差。列数 > 10 的词袋型题目**本质上不可猜**，
   别在同一题上反复试 —— 把力气花在**列举型**（能数出个数的那种）。

**⑥ 实操中的坑：**
- 相关子查询写多了会**超时**（121 第一次 `interrupted`）→ 改成 **CTE 预聚合 + LEFT JOIN**：
  ```sql
  WITH ta AS (SELECT account_id, COUNT(*) n, SUM(...) inc FROM trans GROUP BY account_id)
  SELECT ... FROM base b LEFT JOIN ta ON ta.account_id=b.account_id
  ```
- 分类列的名字**照抄 evidence**（`'High Activity'`/`'Loan Customer'`/`'Active Customer'`/`'Regular Customer'`）。

---
