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
B 部分的“该库连接图”读一遍，后面几十题都能复用。

⚠️ **换库的第一件事：把关键列的取值 `SELECT DISTINCT` 看一眼。**
每一库的“值风格”不同，凭印象写必错（实测两边都踩过）：

| 库 | 坑 | 实测 |
|---|---|---|
| card_games | 首字母大写 | `status='restricted'` → **0 行**；`'Restricted'` → 636 |
| california_schools | 小写 f | `'Directly funded'`（不是 `'Funded'`） |

同理，**列名也要先核实**（evidence 里的概念名未必是列名，见 B 部分 card_games）。

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
  ⚠️ 实测列名是 **`budget.event_status`**（不是 `status`；`status` 只在 `event` 表上）。
- `expense.expense_date` 是 `'YYYY-MM-DD'`；`event.event_date` 是 `'YYYY-MM-DDTHH:MM:SS'`。
- "T-shirt size" = `member.t_shirt_size`；"full name" = `first_name, last_name`（两列）。

**主力连接（首批 13 道 12 对，全靠这四条）**：
```sql
member.link_to_major = major.major_id      -- 学院 / 专业 / department
member.zip           = zip_code.zip_code   -- 城市 / 县 / 州（“grew up in …”）
attendance.link_to_member = member.member_id   -- 某人参加过的活动
event.event_id            = attendance.link_to_event
```
“哪个学院 / 什么专业 / 哪个城市”类题 = `member` + `major` / `zip_code` 两表 JOIN，几乎不会错。

⚠️ **“最高出勤 / 最多 X”类题先查并列**（`dev idx 1318` 实测）：
`Registration` 与 `Yearly Kickoff` **都是 30 人并列第一**，金标取的是后者，
而 `ORDER BY COUNT(*) DESC LIMIT 1` 在我这里返回前者 → 形状对、值不对。
这种并列只能靠运气，**不要在同一题上反复换写法**。

**实测全量：113 道 103 对 / 10 错（91.2%，目前最好的库）**。补充实测坑：
- **`zip_code` 没有 `country` 列**（只有 `zip_code, type, city, county, state, short_state`）——
  `1433` 问“which countries”我写了 `country` 直接报错；该库“国家”概念实际落在 `state` 上。
- **`event` 没有 `url` 列**（只有 `event_id, event_name, event_date, type, notes, location, status`）——
  “links to events”类要回到外键 `budget.link_to_event`（`1436` 实测）。
- ⚠️ **`SUM(...)` 旁边带非聚合列时必须 `GROUP BY`**：`1467`（“total amount spent on
  speaker gifts **and list the event name**”）我写成了全表聚合 → 1 行，金标 **7 行**。
- **“full name” 没 evidence 时可能是 1 列**：`1366`“List all the members”金标 1 列（我给了
  `first_name, last_name` 两列）；而 `1414` 的 evidence 明写“full name refers to first_name, last_name”（两列）。
  ⇒ **evidence 写了就按 evidence，没写就两种都可能。**

### superhero（10 表）
```
superhero ──id── hero_power ──power_id── superpower
          ──*_id── colour / gender / race / publisher / alignment
          ──id── hero_attribute ──attribute_id── attribute（attribute_value）
```
- `superhero.full_name`：**NULL 和字符串 `'-'` 都表示"没有全名"**（122 / 125 行）。
- "superpower" → `superpower.power_name`；"attribute value" → `hero_attribute.attribute_value`。
- ⚠️ **`superpower.power_name` 首字母大写**（`idx 803` 实测：evidence 写 `'cryokinesis'`，
  库里是 `'Cryokinesis'`，小写直接 0 行）。
- ⚠️ **取最小/最大属性值时先查并列**：`idx 837`（“lowest attribute value”）用
  `ORDER BY … ASC LIMIT 1` 得 1 行，金标是 **10 行** —— `MIN(attribute_value)=5` 有 10 个英雄并列。
  ⇒ 按 A2 的备用写法：`WHERE attribute_value = (SELECT MIN(attribute_value) FROM hero_attribute)`。
- 实测全量：**81 道 75 对 / 6 错（92.6%）**。未解的四道都是口径类：
  `720`（“over 15 powers”：金标 71 行 vs 我 102 行，已确认 `hero_power` 无重复行 —— 仍未解释）、
  `741`/`767`/`791`（极值/均值口径）。

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

**⚠️ 首批 13 道实测（8 对 / 5 错）——先记住下面两条**

1. ⚠️ **本库的输出粒度是混合的，不要无脑加 `DISTINCT`**（这条通则本轮被自己的数据证伪）：

   | idx | 题干 | 金标行数 | 加 DISTINCT 后 | 结论 |
   |---|---|---|---|---|
   | 851 | Renault 造的 circuit 的 position | 18 | 20 | 去重 + 排 NULL（可能） |
   | 956 | born after 1975 ranked 2 的 driver | **224** | 11 | **行级**，金标没去重 |
   | 974 | 最快圈速的赛季 | **5268** | 1 | 行级 |
   | 1010 | Lewis Hamilton 的圈速记录 | **11340** | 1 | 行级 |
   | 849/855/921 | “Where can X be found” → url | **1** | 27/19/51 | 只有 1 行（未解释） |

   ⇒ “Which/Who 谁是…” 先按**去重**写；一旦 detail 显示金标行数是几百上千，就是行级题。
   **不要因为 card_games 的经验给 formula_1 无脑加 `DISTINCT`**（两个库粒度相反）。
2. ⚠️ **`qualifying.q1/q2/q3` 的格式是 `'1:40.318'`（分:秒.毫秒），没有前导 `0:`**：
   evidence 里写的 `'0:01:40'`（H:MM:SS）**不能直接拿去 `=`**（实测 0 行），
   要用前缀匹配：
   ```sql
   WHERE qualifying.raceId=355 AND qualifying.q2 LIKE '1:40%'
   ```
   （实测 `q2 LIKE '%1:40%'` 全库 68 行；`q2='1:40.000'` 0 行。）
   同类：`results.time` / `pitStops.time` 也是 `'1:31:57.403'` 这种写法。
3. **“Where can the introduction/information of the races held on X be found?” → `races.url`**，
   但金标只给 **1 行**（`849`: 27 个 url、`855`: 19 个 url、`921` 同型，金标都是 1 行）—— 疑似省略了聚合，暂无法稳定复现。
4. ⚠️ **实测取值（evidence 常写错）**：
   - `drivers.nationality` 是 **`'American'`**（evidence 写成 `'America'`，照抄会得 0 行 —— `964` 实测）
   - 阿布扎比的赛道叫 **`'Yas Marina Circuit'`**（不是 “Abu Dhabi Circuit”，`922` 实测）
   - `qualifying.q1/q2/q3` 是 `'1:40.318'`，注意与 `results.time` 的 `'1:31:57.403'` 时长格式不同
5. ⚠️ **`position` 至少在四张表都有，语义不同**：`results`（完赛名次）/ `driverStandings`（积分榜）/
   `constructorStandings`（积分榜）/ `qualifying`（排位赛）→ “ranked Nth”类题先想是哪一张（`956` 就栽在这）。
6. **金标倾向少列**：`986`（“indicate the time in milliseconds”→ 只给 `milliseconds`）、
   `1009`（“list the time each driver spent”→ 只给 `duration`）、`1000`（“full location”→ 金标 1 列）。
   ⇒ “列出 X 的 Y” 类题，**只给 Y**，别把 X 的 id 也带上。

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
- ⚠️ **`posts` 表没有 `BountyAmount`**，它在 **`votes`** 表上（实测踩过 `dev idx 700`：写成 `posts.BountyAmount`
  直接报 `no such column`）。类似地：`CommentCount / FavoriteCount / ViewCount / Score` 在 `posts`，
  `BountyAmount` 只在 `votes`。
- ⚠️ **“last edited by / last to edit” 不要用 `posts.LastEditorUserId`**：该列有 **47361 行是 NULL**
  （实测），JOIN `users` 会直接得空集（`dev idx 689` 我交了个 0 行的答案）。
  正确做法是走 **`postHistory`**：
  ```sql
  SELECT users.DisplayName, users.Location FROM postHistory
  JOIN users ON postHistory.UserId = users.Id
  WHERE postHistory.PostId = 183
  ORDER BY postHistory.CreationDate DESC LIMIT 1
  ```
  实测结果：`('Vitor De Mario', 'Rio de Janeiro')`。evidence 里的
  `last to edit refers to MAX(LastEditDate)` 说的就是这个“按时间取最后一条编辑记录”。
- ⚠️ **“count the number of posts with tag X”，若 evidence 点名 `TagName`，金标就在 `tags` 表上数**：
  `dev idx 696`（'careers'）实测 ——
  `SELECT COUNT(*) FROM tags WHERE TagName='careers'` = **1**（金标）
  vs `SELECT COUNT(*) FROM posts WHERE Tags LIKE '%<careers>%'` = 22（**错**）。
  ⇒ **evidence 点到哪张表的哪个列，就用那个列**，不要自己找“等价”的写法（详见 `naming-traps.md`）。

### card_games（6 表）
```
cards ──uuid── legalities / rulings / foreign_data
      ──setCode── sets ──code── set_translations
```
- `cards` 有 **74 列**，好几个 `id`：`id`（整数主键）、`uuid`（外部 ID）、`multiverseId`。
- “which cards” 的金标常返回 `cards.id`（`minidev idx 346`）。
- `borderColor` 取值：black / borderless / gold / silver / white。

**⚠️ 实测坑（dev 342–363 一批 13 道错 8 道，全部踩在下面这几条）**

1. **列名是 camelCase，evidence 里的概念名不是列名**：

   | evidence 里写的 | 真实列名 |
   |---|---|
   | EDHRec | **`edhrecRank`** |
   | “卡片类型” | `cards.type`（粗）/ `cards.types`（细）—— **两个都有** |
   | 文字框 | `isTextless`（0/1） |
   | 先手包 | `isStarter`（0/1） |

   ⇒ 写之前先用 `SELECT name FROM pragma_table_info('cards') WHERE name LIKE '%关键词%'` 核对（实测：
   写 `cards.EDHRec` 直接 `no such column`）。
2. ⚠️ **这一库的取值首字母大写，小写几乎全不匹配（大小写敏感）**：

   | 你可能会写 | 实际值 | 行数对比 |
   |---|---|---|
   | `legalities.status = 'restricted'` | `'Restricted'` | **0 vs 636** |
   | `cards.name = 'annul'` | `'Annul'` | **0 vs 正常** |

   `status` 只有三个值：`Legal` / `Banned` / `Restricted`。
   （与 california_schools 的 `'Directly funded'`（小写 f）正好相反 —— 所以**每换一个库都要先
   `SELECT DISTINCT` 看一眼真值**，不要凭印象写。）
3. **同名卡有多个版本（按 `uuid` 区分）**：`WHERE name='Duress'` → 29 行；`name='Annul'` → 多个 number。
   输出**属性列**时通常要 `DISTINCT`（实测 `idx 357`：`DISTINCT promoTypes` = 4 = 金标行数）。
4. 连接键：`legalities.uuid = cards.uuid`、`rulings.uuid = cards.uuid`、
   `foreign_data.uuid = cards.uuid`、`set_translations.setCode = sets.code`。
5. `cards.faceConvertedManaCost` 是 **real**（数值），最大值 7.0 **有 22 张并列** ——
   这类题的 `ORDER BY ... DESC LIMIT 1` 撞对撞错靠运气（`idx 342` 就错了），不要指望。
6. ⚠️ **“Name all cards X” 的金标也可能返回 `cards.id` 而不是 `name`**
   （`idx 343` 行数对、集合不对的疑似原因 —— 它是“帧版本”题，654 行两边一样）。

**⚠️⚠️ 第二批实测（dev 342–526 全 123 道：76 对 / 47 错）—— 下面两条是最大的失分源**

7. **`cards` 是一卡一印刷版本一行（同 `name` 多行）⇒ 输出列一律先加 `DISTINCT`。**
   金标给的总是**去重后的值集合**：

   | idx | 题干 | 我（未去重） | 金标 |
   |---|---|---|---|
   | 387 | OGW 的卡的颜色 | 187 | **10** |
   | 399 | arena 卡的 subtypes+supertypes | 999 | **46** |
   | 444 | boros watermark 卡的外语名 | 1052 | **95** |
   | 448 | abzan watermark 卡的外语名 | 480 | **47** |
   | 442 | Masques/Mirage block 的 set | 9 | **3** |

   ⇒ 这一库的“List / What are the …”题，**先在输出列上加 `DISTINCT`**，再去想别的。
8. ⚠️ **多值串列（`keywords` / `subtypes` / `colors` / `promoTypes`）先试精确匹配 `=`，再试 `LIKE`**
   （实测 `idx 376`）：

   | 写法 | 行数 |
   |---|---|
   | `keywords = 'Flying'` | **3088**（金标） |
   | `keywords LIKE '%flying%'` | 5039（**错**，把 `Flying,Flash` 等也算了） |
9. ⚠️ **“How many X ? List out the id” 类题金标只输出 id（1 列）**，不要在前面加 `COUNT(*)`：
   实测 `435`（black border，49729 行）/ `436`（extendedart，383 行），金标都是 **1 列**，我给了 2 列。
   同类：“State/List the X” 就只给 X，不要把题干里的修饰问句也算成列。
10. **`set_translations` 只覆盖 121 个 set（sets 有 551 个）**：`setCode='M13'/'4BB'/'J14'`
    实测都是 **0 行** → 涉及“某个 set 的语言”时不要假设有翻译行（`428/429/438/519` 四道都因此 0 行）。
11. **取值参考（都是实测）**：
    - `sets.type`：`core / expansion / commander / promo / masters / token / …`（**下划线形式，没有** `expansion commander`）
    - `sets.block`：`Mirage / Masques / …`
    - `legalities.status`：`Legal / Banned / Restricted`
    - `legalities.format`：小写（`legacy` / `oldschool` / `duel` / `pauper` …）
12. **`faceConvertedManaCost` 最大值 7.0 有 22 张并列**；`convertedManaCost` 同理 ——
    “最高 X 的前 N 张”类题排序不稳定，`514`/`392`/`342` 都因并列而错。

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
- 问“atom 19”这类，金标可能按 `atom_id LIKE '%_19'` 处理（`minidev idx 420`）。

**⚠️ 首批 13 道（11 对）实测到的关键坑：**
- ⚠️⚠️ **`connected` 表是双向存储的：每个 bond 存两行（`A→B` 和 `B→A`）**
  - `WHERE bond_id='TR001_2_6'` 实测返回 **2 行**（`TR001_2|TR001_6` 与 `TR001_6|TR001_2`）
  - 全库连接行数 = **10882**，而实际无向连接只有 **5441**（正好一半）
  - `idx 221`（“TR001 里 bond_id=TR001_2_6 的原子”）金标 **1 行**，我给了 2 行
  ⇒ 凡是数“连接/键”的题，**行数先除以 2 看看合不合理**；输出原子对时先想“金标是不是只要一侧”。
- **`idx 211` 实测**（“非致癌分子里连接的原子”）：金标是
  `SELECT DISTINCT connected.atom_id` —— **1 列、5399 行**（我给了 `atom_id, atom_id2` 两列 10882 行）。
  ⇒ 卡方（1 列 vs 2 列）在这里是常见失分点，“connected atoms”不一定给两个 atom_id。

**⚠️ 全量实测（76 道 → 63 对 / 13 错，82.9%）：13 道错题里 7 道是“列数”错**

这个库的列数倾向跟别的库相反 —— **金标爱多给列**：

| idx | 题干 | 我给的 | 金标 |
|---|---|---|---|
| 264 | “What are the labels for TR000, TR001 and TR002?” | 1 列（label） | **2 列**（molecule_id + label） |
| 252 | “What are the atoms that can bond with … lead?” | 1 列（atom_id2） | **2 列** |
| 223 | “What are the atom IDs of the bond TR000_2_5?” | 1 行 2 列 | **2 行 1 列** |
| 309 | TR346 的 atom id + 可建 bond 类型数 | 8 行 2 列 | 5 行 **3 列** |

⇒ **两条经验**：
1. 题干里列了好几个具体实体（“for TR000, TR001 and TR002”、“atom X and atom Y”）时，
   金标通常把**实体 id 也输出一列**（跟 `naming-traps.md`“list 不一定返回名字”同源）。
2. 问“一个 bond 的两端原子”时，金标可能是 **2 行 × 1 列**（顺着 `connected` 的行结构），
   而不是 1 行 × 2 列 —— **不要自作主张加 `LIMIT 1`**（`223` 就是因此错的）。

---

## C. 提交前的三个快速检查

1. **空集？** → JOIN 条件错 / 值匹配错（大小写、格式、NULL）
2. **行数对不对得上？** 心里估一下（"多少个 X"通常是 1 行 1 列；"列出 X"可能是几十行）
3. **列数？** 题干提了几个概念就给几列（**但金标可能多给一列主键 id**）

详细的判定规则见 [`scoring.md`](scoring.md) 和 [`checklist.md`](checklist.md)。
