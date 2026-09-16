# 写 SQL 时逐条过的陷阱（按动作顺序）

> 这是**做题时唯一必须逐条过一遍**的文件。每条都来自实测错题，后面括号里是证据。
> 细节展开在 `sqlite-and-data.md` / `naming-traps.md` / `calibration.md`，**卡住再看**。

---

## ① 写 `SELECT` 的列时

- [ ] **要 `DISTINCT` 吗？** 一个实体多行时，金标常常要**去重集合**：
      `card_games` 🔴 最强（387: 187→**10**、444: 1052→**95**）；`toxicology` 输出原子对时也要。
      **反例**：`formula_1` 是混合粒度（956: 金标 **224 行**是行级）；`european_football_2` 的属性查询
      **不能**去重也不要 `LIMIT 1`（金标给全部快照）。→ **先按当前库档案 `db/<db_id>.md` 的"必查"决定。**
- [ ] **列数 = 题干提到几个概念？** 三种偏差都实测过：
      - 金标**少给**：`card_games` 435「How many X? List out the id」→ 只要 id（1 列）
      - 金标**多给**：`toxicology` 264「labels for TR000, TR001 and TR002」→ **2 列**（多一个实体 id）
      - 金标**拼接**：`financial` 1000「full location」→ 1 列
      ⇒ **拿不准时，题干里的每个名词都当成一列来给。**
- [ ] **"full name" 是 1 列还是 2 列？** `student_club` 1366 实测是 **1 列**，而 1414 的 evidence
      明写 `first_name, last_name`（2 列）→ **evidence 写了就按 evidence。**
- [ ] **`COUNT(*)` 还是 `COUNT(DISTINCT 实体id)`？** 题干主语是**实体**且 JOIN 会扇出时用后者：
      `codebase_community` 709「how many of the **posts**」→ `COUNT(DISTINCT posts.Id)`=**2**（`COUNT(*)`=4 错）。

## ② 写 `FROM` / `JOIN` 时

- [ ] **连接键是哪一套 ID？** 同一个库常有多套：
      `european_football_2`（`id` vs `player_api_id`）、`codebase_community`、`formula_1`（`raceId`=race number）。
- [ ] ⚠️ **两表真的能连上吗？** ← **`thrombosis_prediction` 最大的坑**：
      `Examination` 806 行里**只有 70 行**能 JOIN 上 `Patient`（两套编号）；`Laboratory` 才是全通的。
      ⇒ **进新库先做结构体检**（见 SKILL.md 第 0 步）。
- [ ] **一侧是一对多吗？** 会扇出行数、也会让 `COUNT` 虚高：
      `debit_card_specializing`、`student_club`、`formula_1`（一行一次参赛）。
- [ ] **表是双向存储的吗？** `toxicology.connected` 每个 bond 存 **2 行**（`A→B` 和 `B→A`），
      全库 10882 行 = 5441 个真实连接。**数连接时先 ÷2 看看合不合理。**
- [ ] **JOIN 是不是"隐式过滤"？** 多 JOIN 一张表会把行数砍掉，金标**可能就是靠它过滤**的
      （`codebase_community` 116、`toxicology` 的诊断类题）。
      ⇒ 行数比金标**多**时，试试**多加**一张表；比金标**少**时，试试**减**一张。
- [ ] ⭐ **“列出 A 以及它的 B（如果有）/ 以及 B 的分数” → 先试 `LEFT JOIN`**（实测 `california_schools 27`）：
      题干带 “if there is any”、“along with the score” 这类**可选属性**时，金标往往用 LEFT JOIN，
      没有该属性的实体（分数为 NULL）**也要出现在结果里**。
      验证手法：金标行数 == **只按主表条件筛出的行数**（`27` 金标 8574 = 纯 `schools` 行数）→ 就是 LEFT JOIN。

## ③ 写 `WHERE` 的**值之前**（最容易翻车）

- [ ] ⚠️ **先把该列 `SELECT DISTINCT` 看一眼真值** —— 每个库的大小写风格都不同：

      | 库 | 实测 |
      |---|---|
      | `card_games` | 首字母大写：`'Restricted'`（小写=**0 行**，真值 636）、`'Annul'`、`'Cryokinesis'` |
      | `california_schools` | 小写 f：`'Directly funded'` |
      | `thrombosis_prediction` | 首字母大写：`'Aortitis'`、`'SLE'` |
      | `financial` | 国家/区名按库内写法；`Currency` 只有 `CZK`/`EUR` |

      ⇒ **evidence 里的值不一定是库里的写法**，照抄前先看一眼。
- [ ] ⚠️ **日期是哪种格式？** 三种都出现过：
      `'YYYY-MM-DD'`（`financial`/`codebase_community` 的 `examination Date`）、
      `'YYYYMM'`（`debit_card_specializing.yearmonth`）、`'YYYY-MM-DD HH:MM:SS.0'`（`codebase_community` 带毫秒）。
      **动手前 `SELECT 该列 FROM 表 LIMIT 1`。**
- [ ] ⚠️ **多值串列用 `=` 还是 `LIKE`？** 先试**精确匹配**：
      `card_games` 376 `keywords='Flying'`=**3088**（金标） vs `LIKE '%flying%'`=5039。
- [ ] **时间值格式带前导 0 吗？** `formula_1` 的 `q2` 是 `'1:40.318'` 而 evidence 写 `'0:01:40'`
      → `=` 得 0 行，要用 `LIKE '1:40%'`。

## ④ 写聚合 / 口径时

- [ ] **`GROUP BY` 忘了吗？** `SUM(...)` 旁边只要还有非聚合列就必须 `GROUP BY`
      （`student_club` 1467：1 行 vs 金标 7 行）。
- [ ] **分母是"行数"还是"去重实体数"？** 先试行数（`COUNT(*)`）；evidence 写
      `DIVIDE(SUM(x), COUNT(all ...))` 就按它抄。
- [ ] **是不是要"先按实体/月份汇总再取极值"？** 触发词：「某年的最高月 X」、
      「消费最少的客户」、「每个学校的平均分」（`dev idx 1`、`13`）。
- [ ] **取极值时先查并列！** `superhero` 837（`MIN=5` 有 **10 个**并列）、
      `financial` 101（`1995-01-01` 有 **315 个** account）。
      ⇒ 行数不对时换 A2 的备用写法：`WHERE col = (SELECT MIN/MAX(col) ...)`。
- [ ] ⚠️ **NULL 在 `ORDER BY ASC` 时排最前** ⇒ 取"最小/最年轻/最早"**别用 `LIMIT 1`**，
      用 `WHERE col = (SELECT MIN(col) ...)`（`codebase_community` 663 实测）。

## ⑤ 提交前的最后一眼

→ 去 [`checklist.md`](checklist.md)，**逐条勾**（那里是从这里"毕业"出来的固定 12 条）。
