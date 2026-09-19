# 写 SQL 时逐条过的陷阱（按动作顺序）

> 这是**做题时唯一必须逐条过一遍**的文件。每条都来自实测错题，后面括号里是证据。
> 细节展开在 `sqlite-and-data.md` / `naming-traps.md` / `calibration.md`，**卡住再看**。

---

<!-- push step=4 -->
## ⓪ 落笔之前：概念先定位（列名靠猜 = 最贵的错）

- [ ] ⭐ **题干里的概念名词，查过库了吗？** 别用英文语感猜列名。实测教训：
      我把「type of educational option」猜成 `schools.EdOpsName`（金标 `frpm."Educational Option Type"`）、
      「district code」猜成 `schools.DOC`（金标 `frpm."District Code"`）、
      「locally funded charter」猜成 `frpm` 那套（金标 `schools.Charter=1 + schools.FundingType`）。
      - 概念以**值**存在于库里 → `bird_find <db> <词>`（报出命中列 + 真值样本 + 命中行数）
      - 概念是**列名**（“district code”搜不到值） → ⭐ **`bird.py cols <db> "code|type|option"`**
        （一次列出所有匹配的 `表.列` + **非空行数 / 去重数**）；`bird_schema <db> table=<表>` 通读列名也行，
        但只 grep `%Type%` 会漏掉 `District Code` —— **grep 关键词不算读过列名**。
      - 概念是**库级写法**（该不该 DISTINCT / 主表是谁 / 计数怎么写） → `bird.py conventions --db <db>`
        （**换库必跑**；实测 `COUNT(列)` 是 11 库的绝对主流，`COUNT(DISTINCT)` 只在 financial、thrombosis 常见）
      - ⭐ **命中 ≥2 列时先比“非空行数”**：行数差得远 ⇒ 是**不同粒度**的两列，选与题干实体粒度一致的那列。
- [ ] ⭐ **`bird_find` 命中 ≥2 列怎么选？**
      ① evidence 点名 → 用它；② 只有一列命中 → 用它；
      ③ 多列命中但**行集合相同** → 任选（差异一定在别处）：实测 `california_schools` 1
      的 `frpm."School Type" LIKE '%Continuation%'` 与 `"Educational Option Type"='Continuation School'`
      **都是 459 行、diff=0** —— 我当时把错因归到列上，真实错因是 **NULL 未排除**；
      ④ 否则选**更专门**的那列（命中行数更少 / 取值集合更窄），**并把结论写进 `db/<库>.md`**。
<!-- /push -->

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
- [ ] ⭐⭐ **计数形态三选一：默认 `COUNT(主表.主键列)`**（不是 `COUNT(*)`、也不是 `COUNT(DISTINCT)`）。
      实测 11 库 1057 道已提交题的金标：`COUNT(列)` 全面占优（codebase 46 / superhero 21 / student_club 25 /
      card_games 18 / california 29 …），`COUNT(DISTINCT)` 只在 **financial（23）和 thrombosis（29）** 常见，
      `COUNT(*)` 很少。⇒ **先看 `db/<库>.md` 末的“惯例卡片”，再决定**：
      - 本库以 `COUNT(列)` 为主 → `COUNT(T1.主键列)`（如 `COUNT(T1.member_id)`、`COUNT(T2.driverId)`）
      - 本库以 `COUNT(DISTINCT)` 为主 / evidence 明写 distinct → `COUNT(DISTINCT T1.主键列)`
      - 题干主语是**实体**且 JOIN 会扇出 → 也要去重（`codebase_community` 709：`COUNT(DISTINCT posts.Id)`=2，`COUNT(*)`=4 错）
- [ ] ⭐ **列的顺序 = 题干提到的顺序**（`set()` 判定 ⇒ **列序不同也是 0 分**）：
      实测 `california_schools` 81：列集合一模一样，我写 `School, City, Low Grade`、
      金标按题干顺序 `City, Low Grade, School` → ❌。
      ⇒ 写 `SELECT` 前先把题干里的概念**从左到右标个 1,2,3**，照序输出。

## ② 写 `FROM` / `JOIN` 时

- [ ] ⭐⭐ **主表先定，再写 JOIN**：`FROM` 第一张表按 `db/<库>.md` 的惯例卡片选。
      多表库里**主表决定行宇宙**：`thrombosis_prediction` 三表整体 ID 覆盖率 1238 / 302 / **70**
      ⇒ 选错表就是换了候选集，**形状再对值也必不同**（本轮 42 道错题里 20 道与此相关）。
- [ ] ⭐ **表集合最小化**：只 JOIN 题干真正用到的表。实测 `california_schools` 24：我多 JOIN 了一张
      `schools` → 999 行，金标只用 `satscores JOIN frpm` → 1068 行。
      （与下面“JOIN 隐式过滤”不矛盾：先用**最小表集**，行数偏少再加表）

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

- [ ] ⭐ **题干有 “if there are any / if any” 吗？** ⇒ 不是“结果可能为空”，而是**要你把该列为 NULL 的实体排除**：
      金标写 `AND 该列 IS NOT NULL`（实测 `california_schools` 33：「websites … **if there are any**」
      → 金标 `Website IS NOT NULL`，3 行 → 2 行）。

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
- [ ] ⭐ **题干的实体名词是复数（"how many students/schools…"、`school/s`）？**
      先算两种：`SUM` 一把 vs **每个实体一行**。实测 `california_schools` `53`（How many test takers
      at the school/s）金标是 **每校一行、32 行**，不是 `SUM`。
      （只有 1 个样本 ⇒ 这是**触发你去两种都算**的检查项，不是定论；攒到第 2 例再升级成规则。）
- [ ] **分母是"行数"还是"去重实体数"？** 先试行数（`COUNT(*)`）；evidence 写
      `DIVIDE(SUM(x), COUNT(all ...))` 就按它抄。
- [ ] **是不是要"先按实体/月份汇总再取极值"？** 触发词：「某年的最高月 X」、
      「消费最少的客户」、「每个学校的平均分」（`dev idx 1`、`13`）。
- [ ] **取极值时先查并列！** `superhero` 837（`MIN=5` 有 **10 个**并列）、
      `financial` 101（`1995-01-01` 有 **315 个** account）。
      ⇒ 行数不对时换 A2 的备用写法：`WHERE col = (SELECT MIN/MAX(col) ...)`。
- [ ] ⚠️ **NULL 在 `ORDER BY ASC` 时排最前** ⇒ 取“最小/最年轻/最早”**光 `LIMIT 1` 会选到 NULL 行**：
      两种写法金标都用过 —— 在 `ORDER BY … ASC LIMIT 1` 前面加 `WHERE 该列 IS NOT NULL`，
      或直接用 `WHERE col = (SELECT MIN(col) ...)`。
      实测 `california_schools` **40 / 43** 两道都栽在这（规则早就在，提交前没勾而已）。
- [ ] ⭐ **“which X has the most/most number of …” 但金标行数 >1？** ⇒ 是**并列第一**：
      金标用 `RANK()/DENSE_RANK() OVER (ORDER BY COUNT(...) DESC) … WHERE rank_num = 1`
      （实测 `california_schools` 68：金标 **3 行**，我 `LIMIT 1` → 1 行）。

- [ ] ⭐⭐ **百分比题的两个条件，哪个进 `WHERE`、哪个进 `CASE`？先想“范围”再想“分子”** ——
      本类题金标经常把**题面里作形容词的那个条件当范围（`WHERE`）**，把**题面主语当被数项（`CASE`）**，
      **与语义直觉相反**。实测 `card_games` **417**（“percentage of **Japanese** translated sets are **expansion** sets”）：
      金标 = `WHERE T1.type='expansion'` + `SUM(CASE WHEN T2.language='Japanese' THEN 1 END)*100/COUNT(T1.id)`
      = 61/610 = **10.0**；我按语义收窄成 `WHERE language='Japanese'` → 50.41（错）。
      同库 **433** 同理（分母是 `sets ⋈ set_translations` 的全体行数）。
      ⇒ 两个条件都在时，**默认把“被问的那个属性”放进 `CASE`、另一个进 `WHERE`**，不要自己把 `WHERE` 收窄成题面主体。
- [ ] ⭐ **“Is there / Did …” 类是否题：金标常用 `IIF(..., 'YES', 'NO')`（全大写）**
      （实测 `card_games` 465 / 469；EX 大小写敏感，写 'Yes' 或返回实体列都算错）。
      但同库 **410**（“Is there any card from …”）金标返回的是 `cards.id` ⇒ 用 evidence 里有没有 `EXISTS`/`IIF`/`YES` 字样判。
- [ ] ⭐ **“in set of <卡名>” 不一定是整张表的范围**：金标 `446` 直接用 `cards.name = '<卡名>'`
      限定**行本身**（分母 = 该卡自己的行数）；同族 `462` 用 `setCode IN (SELECT setCode FROM cards WHERE name=…） LIMIT 1` 只给 **1 行**。
- [ ] ⭐ **“How many …”开头 ≠ 计数**：`card_games` **408**（How many unknown power cards contain info about the
triggered ability）金标返回的是 **`rulings.text` 本身**（2059 行）。先看 evidence 写的是 `COUNT` 还是列名。
- [ ] ⭐⭐ **同义句式的百分比题，方向可能相反 ⇒ 不许复用分子/分母**（`toxicology` 实测：273
      “percentage of chlorine **in** carcinogenic molecules” 我算对；317 “percentage of carcinogenic molecules
      **which contain** chlorine” 我用了**同一个值**却错 ⇒ 分母换了边，很可能是「全体分子」）。
- [ ] ⭐ **“average number of X atoms in …” 多半要「先按实体计数、再平均」**，不是原子级 `AVG(标志位)`
      （`toxicology` 197：原子级 0.0846 ✗；每分子氧原子数再 `AVG` = 2.3597 才是“number”的读法）。
- [ ] ⭐ **“least / most common …” 可能要给全部并列**（`toxicology` 251 金标 **4 行**，不是 `LIMIT 1`）。
- [ ] ⭐ **“List down <属性> for <实体> from A to B” 常是行级 + 带实体 id**（`formula_1` 267 金标 **1153 行 2 列**，
      不是 `DISTINCT 属性` 的 3 行）。
- [ ] ⭐ **“is it carcinogenic?” 这类二值判断题，金标给的是原始标签字符 `+`/`-`**，不是 `'yes'/'no'`
      （`toxicology` 283/244 实测）。
- [ ] ⭐ ⭐ **“Rank … by X” 的金标往往就是 `RANK() OVER (ORDER BY X …)` 一个输出列**（而且聚合列排在前面）。
      ⇒ 碰到 **Rank / 排名 / popularity** 字样，先按 **3 列**写：`(实体名, X 的值, RANK() OVER (…))`。
      （`superhero` 726/728 都栽在这；简单集 763 是轻症。）
- [ ] ⭐ ⭐ **问“最…”分两种形态，先看主语是人还是值**：
      - **“Who/Which <人> is the <est>?”** ⇒ `ORDER BY 属性值 <方向>, T1.id LIMIT 1`（**取 1 行**，并列按 id 升序）
        （`superhero` 736/766/794 金标都是这个形状）
      - **“…the lowest/highest attribute value”**（问值） ⇒ `= (SELECT MIN/MAX(…))`（**全部并列**，837 金标 10 行）
- [ ] ⭐ ⭐ **分母优先用“JOIN 之后的行数”**，不要用独立子查询去数：`codebase_community` 557 金标
      `SUM(IIF(Age>65,1,0)) * 100 / COUNT(T1.Id)`（分母是同一次 JOIN 的行）；672 金标更是直接
      `COUNT(users.Id)` **不去重**（数论坛帖子行），而 716 又要求 `COUNT(DISTINCT users.Id)` ——
      **先写“不去重的 `COUNT(列)`”，形状/值对不上再换 DISTINCT**。
- [ ] ⭐ **日期列相减别自作主张用 `JULIANDAY`**：`codebase_community` 692 的金标就是 `T1.Date - T2.CreationDate`
      （SQLite 取字符串的数字前缀 ⇒ 得到**年份差**），用 JULIANDAY 反而 0 分。
- [ ] ⭐ **“average … per month” 的分母是 12**（不是“有数据的月份数”）：`codebase_community` 665 金标 `COUNT(T1.Id) / 12`。
      （同理：“per year” 想 12 个月 / “daily” 想 365。）
- [ ] ⭐ ⭐ **字面量照题干/evidence 的写法抄，不要“替金标纠正大小写”**：`codebase_community` 640 题干写
      `Mornington`、库里存的是 `mornington`，金标用大写 ⇒ 匹配不到任何行（= 0），答案是个负数。
      我改成库里真实大小写反而错。**金标常有这种“它自己也没匹配上”的字面量。**
- [ ] ⭐ **“comment” 要看上下文**：出现 **edit / edited / revision** 时，“comment” = `postHistory.Comment`（编辑备注），
      不是 `comments.Text`（`codebase_community` 584 实测：14254 行 vs 金标 8 行）。
- [ ] ⭐⭐ **evidence 里的公式不能照抄**，它只说明“用了哪些列”，不说明粒度：
      `student_club` 1454 按 evidence 的 `DIVIDE(SUM(cost), COUNT(event_id)) * 100` 算出 6686 ✗；
      正确读法是「这类成本 ÷ **全部**成本 × 100」。⚠️ 题面写了 percentage / percent 就**必须 ×100**
      （1458 evidence 没写 `*100`，不写就是 0 分）。
- [ ] ⭐ **“less than average <某类> cost” 返回**空集** ⇒ 一定是“平均”的算法不同**，
      不是条件写错：最该先换的是**另一套钱列**（`expense.cost` 报销 vs `budget.amount/spent` 预算）。
      （`student_club` 1453：金标回了 **3 行**，我 0 行。）
- [ ] ⭐ **分母别用 JOIN 后的 `COUNT(*)`**（JOIN 会掉掉外键为空的行）：`student_club` 1421 的分母是
      `member` **全表 33**，不是 JOIN 后的 32。
- [ ] ⭐ **答案可以是 0**：evidence 写「'X' is the major/… name」就照字面写 `= 'X'`，
      哪怕该取值在表里**根本不存在**（`student_club` 1441：`major_name='Education'` ⇒ 0，我改成
      `LIKE '%Education%'` 得 3 ✗）。

- [ ] ⭐⭐ **百分比/比例题的固定模板**（`thrombosis_prediction` 实测 1149/1150/1151/1160 四道全中）：

  ```sql
  SELECT CAST(SUM(CASE WHEN <条件> THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(*)
  FROM ... WHERE <实体级过滤（如 SEX='F'）>
  ```

  三个细节都是坑：① **`* 100` 紧跟 `CAST`，不要写在 `/COUNT(*)` 后面**
  ——`CAST(x AS REAL) * 100 / n` 与 `CAST(x AS REAL) / n * 100` **浮点结果不同**（最后一两位），而 EX 是精确集合比较；
  ② **实体级过滤放 `WHERE`，不要塞进 `CASE WHEN`**（它同时决定分子和分母，塞进 CASE 分母就不对了，实测 1160）；
  ③ 题干说“percentage”就 `* 100`，说“ratio”就不乘；
  ④ ⚠️ **不要信 evidence 里的乘数**：1279 的 evidence 写 `MULTIPLY(…, 1.0)`，金标却是 `* 100.0` ——
     题干说 percentage 就一律 `* 100`（写成 `* 100.0` 或 `* 100 /` 均可）。
- [ ] **两个日期相减 / “至少 N 天”用 `JULIANDAY`**：`JULIANDAY(a) - JULIANDAY(b) >= 365
  （实测 1170：金标是 `T1.Admission='+'`（“initial hospital visit”）+ `INNER JOIN` + **`COUNT(DISTINCT T1.ID)`**，
  而不是相关子查询取 `MIN(Examination Date)`）。跨度跨表计数一律 `COUNT(DISTINCT 实体id)`。

- [ ] ⭐⭐ **`STRFTIME`/`LIKE` 的结果是字符串，年份比较必须用字符串字面量**：
      `STRFTIME('%Y',x) >= 1990`（整数）在 SQLite 里**恒为真**（两个无 affinity 的操作数按存储类排序：数字 < 文本），
      必须写 `>= '1990'`。实测 1254：写成 `>= 1990` → 年份过滤完全失效 → 计数错（金标 `>= '1990'`）。
- [ ] ⭐ **“how many patients” 的计数单位是 `COUNT(T1.ID)`**（`Patient JOIN Laboratory` = **有记录的患者数**），
      不是 `COUNT(*)`（那是实验记录**行数**）。实测 1245 金标 `COUNT(T1.ID)`。
      evidence 写 `DIVIDE(COUNT(ID)…)` 或 “should compute the number of distinct ones” 时才用 `COUNT(DISTINCT …)`。
- [ ] **数值区间默认按“闭区间”写**：normal → `BETWEEN a AND b`（实测 1252 IGG 900~2000）；
      abnormal → `<= a OR >= b`（实测 1248 FG 150/450）；日期 → `BETWEEN`（实测 1187）。
      **例外**：1211 LDH 金标用 `> 600 AND < 800`。⇒ 别为端点反复试，默认闭区间。
- [ ] **题干的“反义词”优先于 evidence**：`inactivated partial prothrombin time` = APTT **异常**（`APTT >= 45`），
      而 evidence 给的是 normal 阈值 `< 45` —— 照抄方向就错（实测 1245）。
- [ ] **“latest / most recent（他们的最新一次）”是全局还是每人？** 两种金标都出现过：
      `thrombosis_prediction` 1219 金标是 **`Date = (SELECT MAX(Date) FROM Laboratory)`（全局最新）**，
      而旧 casebook 里“latest record of each patient”是 per-ID 子查询。⇒ 先按**全局**写，evidence 明写 “each patient” 再改。
- [ ] ⚠️ **evidence 会把输出形状说错，以“最直接读法”为准**：`thrombosis_prediction` 实测两条 ——
      1225 “List and group all patients by sex”的 evidence 写 `GROUP_CONCAT(DISTINCT ID)`，
      金标却是 **`SELECT T1.ID, T1.SEX … GROUP BY T1.SEX, T1.ID`**（行级两列）；
      1186 的 evidence 写 `YEAR(Description)`，金标用的是 **`Examination."Examination Date"`**。
      ⇒ **evidence 管“口径/阈值”，不管“输出形状”；形状看题干句式和 `db/<库>.md`**。

## ⑤ 提交前的最后一眼

→ 去 [`checklist.md`](checklist.md)，**逐条勾**（那里是从这里"毕业"出来的固定清单）。
“列序 = 题干顺序”属于**允许重交**的情形，判定口径见 `checklist.md` 末尾的「⛔ 重交白名单（唯一出处）」。
- [ ] ⭐ ⭐ **"给 id 还是给名字" —— 先看题干有没有 `name` 字样**：`superhero` 772 金标给的是
      **`eye_colour_id / hair_colour_id / skin_colour_id`（数字 id）**，不是 JOIN `colour` 翻译出来的 'Blue'；
      `student_club` 1437 给 `link_to_member, link_to_event`、1451 给 `member_id`。
      ⇒ **不要"自作聪明"去 JOIN 维表把 id 翻译成人话**；题干没要求名称时优先原样给外键/编码列。
- [ ] ⭐ ⭐ **"which X has more? Find the difference" 常常只输出差值一列**：
      `superhero` 744（Marvel−DC）、829（DC−Marvel）金标都是 **1 列**，没有出版社名字。
- [ ] ⭐ ⭐ **百分比的分子分母方向要照题干读，分母优先"没被 JOIN 缩小的那一侧"**：
      `superhero` 788 是「女性英雄里 Marvel 占多少」（分母 = 女性数），不是"Marvel 里女性占多少"；
      835 用 **`LEFT JOIN alignment`** 以便把 alignment 为 NULL 的算进分母；
      743 的分母是 **`(SELECT COUNT(*) FROM superhero)` 全表**。
- [ ] ⭐ ⭐ **"comprehensive profile / statistics / provide details" 这类题 = A11，列数就是属性清单**：
      `california_schools` 的 challenging 全是这种，金标 **9–18 列**，由「原始属性 + 派生比率 +
      `RANK() OVER` 排名 + `CASE` 文字列」拼成；我按 1 列写 ⇒ 那一批 65 道全 0。
      **见到 profile 字样，先一行一个属性数出列数。**
- [ ] ⭐ **"六个指标之比"这类题金标可能排成"每指标一行"**（`california_schools` 55 金标 **6 行 2 列**：
      `(指标名, 比值)`），不是 1 行 6 列。
- [ ] ⭐ **"percentage difference of A during Y1 and Y2" 的分母是 A 那个子集的行数**
      （`codebase_community` 598：`WHERE Name='Student'` 后 `COUNT(Id)` = Student 徽章数）。
