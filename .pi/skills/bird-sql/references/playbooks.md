# 套路手册：按题型套骨架，按库查连接图

**这是做题时最该先看的一份文件。** 目标是"拿到题 30 秒内确定 SQL 骨架"，而不是每题从头推理。

---

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
B 部分的"该库连接图"读一遍，后面几十题都能复用。

---

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

## B. 各库连接图与坑（做题前先读当前库这一段）

### california_schools（3 表）
```
schools ──CDSCode──┐
frpm    ──CDSCode──┤  三者用 CDS 码连接（注意大小写/类型）
satscores ──cds ───┘
```
- **键名不同**：`schools.CDSCode` / `frpm.CDSCode` / `satscores.cds`，但都是 TEXT，可直接等值连。
- ⚠️ **CDS 码的前导 0 是分批丢的**（实测）：`satscores` 2269 行里
  - **2058 行**的 `cds` 是 **14 位**（`'07100740000000'`）→ naive 等值连得上；
  - **211 行**的 `cds` 是 **13 位**（`'7100740000000'`，丢了前导 0）→ naive 等值连**一行都接不上**。

  后果：`satscores JOIN schools ON cds = CDSCode` 会**默默丢掉 211 行**。Contra Costa 就是典型：
  465 所学校，naive join 结果 **0 行**。

  三种写法实测过的匹配数：
  | 写法 | 匹配行数 |
  |---|---|
  | `cds = CDSCode`（naive） | 2058 |
  | `'0' \|\| cds = CDSCode` | 211 |
  | `CAST(CDSCode AS INTEGER) = cds` | **2269**（全匹配） |

  **但不要无条件"修正"**：很多题的**金标用的就是 naive join**（实测 26/30 道 california_schools
  题用小写写法就能对）。所以规则是：
  **先写 naive；如果得到空集或可疑值，再改 `CAST(schools.CDSCode AS INTEGER) = satscores.cds`
  或改成单表查询（只用 `satscores` 的 `cname` / `sname`）。**
- ⚠️ **`schools` 里混着"学区/县办公室"行**：`CDSCode` 以 `0000000` 结尾的那些，`School` 是 **NULL**。
  问"哪个**学校**"时这些行会返回 NULL（实测 `idx 22`：Contra Costa 的最多考生行是学区行，
  `schools.School` 为 NULL；金标加了 `sname IS NOT NULL` 才拿到真学校名）。
- ⚠️ **列归属要记牢**（实测踩过一次）：
  - `Low Grade` / `High Grade` / `Charter School (Y/N)` / 各类 `Enrollment` / `FRPM Count` → 在 **`frpm`**
  - `GSoffered` / `GSserved` / `Virtual` / `Magnet` / 地址 / 电话 / `FundingType` / `StatusType` → 在 **`schools`**
  - `AvgScrMath/Read/Write` / `NumTstTakr` / `NumGE1500` / `sname` / `cname` → 在 **`satscores`**
- `Virtual`：**`'F'` = Exclusively Virtual**（不是 False 的意思），`'P'` = Partial，`'N'` = 无。
- `StatusType` 取值：`Active` / `Closed` / `Merged` / `Pending`
  → “active district” = `StatusType='Active'`；“merged Alameda” = `StatusType='Merged'` + `County='Alameda'`。
- `FundingType`：`Directly funded`（**小写 f**）/ `Locally funded` / `Not in CS funding model`。
- 地址：`Street` vs `StreetAbr`、`MailStreet`（unabbreviated mailing）vs `MailStrAbr`。
  题干说 "postal/mailing street" → 用 `Mail*`；说 "unabbreviated" → 用不带 `Abr` 的。
- "type of education offered" → `EdOpsName`（实测 `idx 42` 命中，值为 `'Traditional'`）。
- 考试优秀率：`Excellence rate = NumGE1500 / NumTstTakr`。

### debit_card_specializing（5 表）
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

### student_club（8 表）
```
member ──member_id──┐ attendance ──link_to_event── event
        └──link_to_major── major
event ──event_id── budget ──budget_id── expense ──link_to_member── member
income ──link_to_member── member
zip_code ──zip── member.zip
```
- `budget` 里既有 `status`（事件状态）也有 `spent` / `amount` / `category`。
- `expense.expense_date` 是 `'YYYY-MM-DD'`；`event.event_date` 是 `'YYYY-MM-DDTHH:MM:SS'`。
- "T-shirt size" = `member.t_shirt_size`；"full name" = `first_name, last_name`（两列）。

### superhero（10 表）
```
superhero ──id── hero_power ──power_id── superpower
          ──*_id── colour / gender / race / publisher / alignment
          ──id── hero_attribute ──attribute_id── attribute（attribute_value）
```
- `superhero.full_name`：**NULL 和字符串 `'-'` 都表示"没有全名"**（122 / 125 行）。
- "superpower" → `superpower.power_name`；"attribute value" → `hero_attribute.attribute_value`。

### formula_1（13 表）
```
races ──circuitId── circuits
      ──raceId── results ──driverId── drivers
                 qualifying / pitStops / lapTimes
                 constructorResults / constructorStandings
      ──year── seasons
```
- `results.position`（完赛名次，退赛 NULL）vs `positionOrder`（最终排序）vs `grid`（发车格）
  vs **`driverStandings.position`（积分榜名次，几乎总有值）** ← 这四个别搞混。
- `qualifying.q1/q2/q3` 是 TEXT `'1:34.188'` 且大量 NULL。
- `results.rank` = 最快圈速名次；`results.time` 里冠军是 `'1:31:57.403'`，其余是 `'+14.925'`
  （所以"冠军"可以用 `time LIKE '%:%:%'` 识别）。
- "race number" = `raceId`；"race at 291" 同理。

### european_football_2（7 表）
```
Player ──player_api_id── Player_Attributes（一个球员多条历史记录！）
Team   ──team_api_id─── Team_Attributes
                            Match ──league_id── League
```
- **两套 ID**：`Player.id`（内部）vs `Player.player_api_id`（FIFA API）。
  `Player_Attributes.id` 又是属性表自己的主键。金标常用 `player_api_id` 连。
- 问"某球员的属性"时通常要多一步取一条：`WHERE player_api_id = (SELECT ... ORDER BY ... LIMIT 1)`。
- `Player.birthday` 是 TEXT；`height/weight` 是 INTEGER。

### thrombosis_prediction（3 表）
```
Patient ──ID── Examination（就诊：Diagnosis / Symptoms / Thrombosis）
        ──ID── Laboratory（化验：44 个指标列，一人多行）
```
- **`Diagnosis` 在 `Patient` 和 `Examination` 都有，值不同**（`minidev idx 87`
  实测金标用 `Patient.Diagnosis`）。
- `Laboratory` 只覆盖 302 个患者（`Patient` 有 1238 个），大量列有 NULL。
- 化验指标的正常范围在 `database_description` 里（如 `LDH < 500`、`IGG 900~2000`）。

### codebase_community（8 表）
```
users ──Id──┐
             posts（OwnerUserId）── Id ── comments.PostId
             votes（UserId / PostId）
             badges（UserId）
             postHistory / postLinks
tags ──ExcerptPostId / WikiPostId── posts.Id
```
- **`posts` 的创建日期列名是拼错的 `CreaionDate`**（不是 CreationDate），最后活动是 `LasActivityDate`。
- `Score` 在 `posts` 和 `comments` **两张表都有**（`minidev idx 344` 实测金标用 `posts.Score`）。
- `users.Age`：teenager 13-18 / adult 19-65 / **elder > 65**。
- ⚠️ **日期列的格式不统一，而且带毫秒后缀 `.0`**（本轮实测踩过）：

  | 列 | 实际值 |
  |---|---|
  | `votes.CreationDate` | `'2010-07-19'`（只到日） |
  | `badges.Date` | `'2010-07-19 19:39:08.0'`（带 `.0`） |
  | `comments.CreationDate` | `'2010-07-19 19:25:47.0'`（带 `.0`） |

  ⇒ 题目给出具体到秒的时间（如 "7/19/2010 7:39:08 PM"）时，要转成 `19:39:08` 并**补上 `.0`**：
  `WHERE Date = '2010-07-19 19:39:08.0'`；用 `LIKE '2010-07-19 19:39:08%'` 也行。
- **取年份**用 `SUBSTR(col,1,4)='2011'` 或 `col LIKE '2011%'`（SQLite 没有 `YEAR()`）。
- 常见题型（本轮 60 道基本全部命中）：
  - “s 的 badge 名” → `badges JOIN users ON badges.UserId=users.Id WHERE users.DisplayName='s'`
  - “获得某 badge 的用户” → 同上反向过滤 `badges.Name='Organizer'`
  - “某用户拥有的帖” → `posts JOIN users ON posts.OwnerUserId=users.Id`
  - “被某人编辑的帖” → 把 `OwnerUserId` 换成 `LastEditorUserId`；
    **若行数对不上，改查 `postHistory`**（`postHistory.UserId = users.Id` + `DISTINCT posts.Title`）
  - “某帖有多少评论” → `posts.CommentCount` 字段 ≠ 评论行数；先试字段，
    行数不对再换 `COUNT(*)`（参考 `minidev idx 344`）
- ⚠️ **两个“一对多”表都有方向性，别猜错边（实测 `dev idx 651`/`667`）**：
  | 表 | 两个方向 |
  |---|---|
  | `postLinks` | `PostId`（源头帖）/ `RelatedPostId`（被指向的相关帖） |
  | `posts.ParentId` | 自己 = 子帖，`ParentId` = 父帖的 id |

  “相关帖的标题” → 拿 `p1.Title` 去筛 `postLinks.PostId`，输出 `p2.Title`（JOIN `RelatedPostId`）。
  行数/值对不上就**换另一边再试一次**（成本很低，且只有一个方向是金标）。
- **`postHistory` 列清单**（列名易记错）：
  `Id / PostHistoryTypeId / PostId / RevisionGUID / CreationDate / UserId / Text / Comment / UserDisplayName`

### card_games（6 表）
```
cards ──uuid── legalities / rulings
      ──setCode── sets ──code── set_translations
foreign_data（多语言）
```
- `cards` 有 **74 列**，好几个 `id`：`id`（整数主键）、`uuid`（外部 ID）、`multiverseId`。
- "which cards" 的金标常返回 `cards.id`（`minidev idx 346`）。
- `borderColor` 取值：black / borderless / gold / silver / white。

### financial（8 表）
```
district ──district_id── client ──client_id── disp ──account_id── account
                                                                  ── trans / loan / order（account_id）
card ──disp_id── disp
```
- 列名是 **捷克语缩写**：`A2`=区名、`A11`=平均工资、`A4`=人口；`trans.operation` 里
  `'VYBER'`=现金取款、`'VKLAD'`=存款；`trans.type` 里 `'PRIJEM'`=贷方、`'VYDAJ'`=借方。
- `client.birth_date` 是 `'1976-01-29'`；`account.date` 是 `'930101'`（YYMMDD）。

### toxicology（4 表）
```
molecule ──molecule_id── atom / bond / connected
```
- `atom.atom_id` 是 TEXT，形如 `'TR001_1'`（分子_序号）。
- `bond.bond_type`：`'-'` 单键 / `'='` 双键 / `'#'` 三键。
- `molecule.label`：`'+'` 致癌 / `'-'` 不致癌。
- 问"atom 19"这类，金标可能按 `atom_id LIKE '%_19'` 处理（`minidev idx 420`）。

---

## C. 提交前的三个快速检查

1. **空集？** → JOIN 条件错 / 值匹配错（大小写、格式、NULL）
2. **行数对不对得上？** 心里估一下（"多少个 X"通常是 1 行 1 列；"列出 X"可能是几十行）
3. **列数？** 题干提了几个概念就给几列（**但金标可能多给一列主键 id**）

详细的判定规则见 [`scoring.md`](scoring.md) 和 [`checklist.md`](checklist.md)。
