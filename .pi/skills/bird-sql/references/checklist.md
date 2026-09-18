# 提交前必勾（按顺序从头到尾过一遍）

> 用法：`bird_answer` 之前**从头到尾扫一遍**。每条都对应实测踩过的坑，不是理论清单。
> 勾不过 → 改一次 → 直接交（**不要反复试**，那是违反 SKILL.md 硬规则 6）。
>
> ⭐ **留痕要求（P10）**：`bird_answer` 现在有**闸门 3** —— 必须带 `--checks "0,1,1b,…"` 列出这次**真正走过**的条目号。
> 标了 `<!-- core -->` 的是**无条件适用**的核心条目（`1` / `1b` / `2` / `2b` / `8` / `12` / `13`），
> 少一个就交不上（确实不适用才用 `--force`，会留痕）；其余条目按题意取舍。
> 留痕写进 `work/probe_log.jsonl`，`bird.py audit` 会统计勾选率、平均条数、**最常被漏掉的条目**。

## A. 形状（先看这个，形状错 = 100% 错）

- [ ] **0. 这个库的惯例卡片读了吗？**（**换库第一题之前**必须跑过一次）
      `python tools/bird.py --dataset dev2025 conventions --db <db_id>` → 看计数形态分布、
      主表分布、`SELECT DISTINCT` 比例、`*100`。结论在 `db/<库>.md` 末尾的“惯例卡片”。
      ⇒ 实测：不看惯例、靠语感猜库级写法，是本项目 68% EX 的主要来源。
- [ ] **1. 列数 = 「属性清单」的行数？**（**落笔前先写清单**：题干每出现一个属性词就写一行 `属性 → 表.列`；  <!-- core -->
      词袋型维度（statistics / profile / activity）当场展开成 3–5 列。**清单行数 = 列数**，不足就回去补列）
      三种偏差都实测过：
      金标少给（`card_games` 435「How many X? **List out the id**」→ 只要 id）、
      金标多给（`toxicology` 264「labels for A, B and C」→ **2 列**，多一个实体 id）、
      金标拼接（`financial` 1000「full location」→ 1 列）。
      ⇒ **拿不准时，题干里每个名词都给一列。**
- [ ] **1b. 列顺序 = 题干提到的顺序？**（**光列数对还不够，`set()` 判定会因列序不同判 0**）  <!-- core -->
      实测 `california_schools` 81：列集合完全一样，只因我按 `School, City, Low Grade` 排、
      金标按题干顺序 `City, Low Grade, School` 排，就成了 ❌。
      ⇒ **写 `SELECT` 时按题干从左到右出现的顺序列字段**（“In which city… what is its lowest grade… Indicate the school name”
      → City, Low Grade, School）。
- [ ] **2b. 主表和表集合对了吗？** ① `FROM` 第一张表按惯例卡片选（主表决定**行宇宙**：  <!-- core -->
      `thrombosis_prediction` 三表 ID 覆盖率 1238/302/70，选错 = 换了候选集）；
      ② **表集合最小化** —— 只 JOIN 题干真用到的表（实测 24：多 JOIN `schools` → 999 vs 金标 1068）。
- [ ] **2. 行数量级对吗？** 心里估一下：问"哪个/谁"→ 通常 1 行；"列出 X"→ 几十行；  <!-- core -->
      "多少 X"→ 1 行 1 列。**对不上量级就是口径或 JOIN 错了**，别硬交。
- [ ] **3. 要不要 `DISTINCT`？** ← 看 `db/<当前库>.md` 的"必查"。
      `card_games` 要（387: 187→10）；`formula_1` 混合（956 金标是**行级 224 行**）；
      `european_football_2` 的属性题**既不去重也不 `LIMIT 1`**。

## B. 空集与值（最常见的"形状对但不该是空"）

- [ ] **4. 结果是空的吗？** 空 = JOIN 条件错 / 值匹配失败 / 大小写不对 / 格式不对。
      **先 `SELECT DISTINCT 该列` 看真值**（`card_games` 小写 `'restricted'` = **0 行**，真值 636 行）。
- [ ] **4b. 题干有 “if there are any / if any” 吗？** ⇒ 那是让你**排除该列为 NULL 的实体**：
      金标会写 `AND 该列 IS NOT NULL`（实测 `california_schools` 33：「websites … **if there are any**」
      → 金标 `Website IS NOT NULL`，3 行 → 2 行）。
- [ ] **5. `WHERE` 里的每个值都核对过库内真写法吗？** 每个库风格都不同：
      `card_games`/`thrombosis_prediction` **首字母大写**；`california_schools` **小写 f**。
      **evidence 给的值不一定是库里的写法。**
- [ ] **5b. 题干里的每个「概念名词」都定位过了吗？**（**不是值，是概念** —— “办学类型/资助类型/区号/职务/地名”）
      → `bird.py cols <db> "type|code|option"`（概念是**列名**，一次列出表.列 + 非空/去重行数）
      或 `find <db> <词>`（概念以**值**存在）。**猜列名是失分最大头**
      （`california_schools` 12 道挂起题里 6 道如此；本轮 42 道错题里 `main` 差 20 道）。
      命中多列时：evidence 点名 > 只有一列命中 > 行集合相同则任选 > 选更专门那列（写回库档案）。
- [ ] **6. 日期是哪种格式？** `'YYYY-MM-DD'` / `'YYYYMM'` / `'YYYY-MM-DD HH:MM:SS.0'` 都出现过。
      **动手前 `SELECT 该列 FROM 表 LIMIT 1`。**（⛔ **已作废**：`financial` 的旧笔记是 Mini-Dev 的 `'930101'`，Dev 已改）
- [ ] **7. 多值串列用 `=` 还是 `LIKE`？** 先试精确匹配：
      `card_games` 376 `keywords='Flying'`=**3088**（金标）vs `LIKE '%flying%'`=5039。

## C. 口径（形状对、值不对的元凶）

- [ ] **8. evidence 的每一个口径都实现了吗？** 逐条对着看到第 1 步划出来的口径：  <!-- core -->
      阈值、`DISTINCT`、分母、列名、单位。（evidence 写 `COUNT(full_name)` 就别用 `COUNT(*)`）
- [ ] **9. 聚合函数旁边还有非聚合列吗？** 有 → **必须 `GROUP BY`**
      （`student_club` 1467：忘了 → 1 行 vs 金标 7 行）。
- [ ] **10. 计数形态对不对？默认 `COUNT(主表.主键列)`**（实测 11 库 1057 道金标：`COUNT(列)` 占绝对多数，
      `COUNT(*)` 很少；`COUNT(DISTINCT)` 只在 **financial / thrombosis** 常见）。
      分母是“行数”还是“去重实体数”→ 先看惯例卡片；题干主语是**实体**且 JOIN 会扇出时用
      `COUNT(DISTINCT 实体id)`（`codebase_community` 709：2 vs 4）。
- [ ] **11. 取极值时查并列了吗？** `superhero` 837（`MIN=5` 有 **10 个**并列）、
      `financial` 101（**315 个** account 并列）。
      行数不对 → 换 `WHERE col = (SELECT MIN/MAX(col) ...)`。
      ⚠️ **NULL 在 `ORDER BY ASC` 排最前** ⇒ 取“最小/最早”**光 `LIMIT 1` 会选到 NULL 行**：
      加 `WHERE 该列 IS NOT NULL`（实测 `california_schools` **40 / 43** 两道都是这个原因，规则本来就在，没勾就是白写）。
- [ ] **11b. 题干问 “which X has the most …” 但金标行数 >1？** ⇒ 是**并列第一**，
      金标用 `RANK()/DENSE_RANK() ... WHERE rank_num = 1`（实测 `california_schools` 68：金标 **3 行**、我 `LIMIT 1` 1 行）。

## D. 最后一眼

- [ ] **12. 当前库档案的"⚠️ 交题前必查 3 条"过了吗？** 回到 `db/<db_id>.md` 顶部逐条对。  <!-- core -->
- [ ] **13. 三道机器闸门过了吗？**（不过会被 `answer` 直接拒绝）  <!-- core -->
      ① **探针**：这题有没有用 `--for <idx>` 跑过真实探针？（`run`/`cols`/`find`/`schema`）
      ② **形状**：SQL 最前面写了 `/* shape: 行数x列数 */` 吗？与实测一致吗？（**比对用的是完整结果**，
      默认 `--max-rows 20` 只影响预览，不会再把 21 行的题说成「实测 20 行」——P13）
      ③ **勾选**：`--checks` 写了吗？核心条目（本文件里带 `<!-- core -->` 的 7 条）齐吗？
      用 `--force` 跳过会在 `audit` 的合规行里现形（**它是唯一的绕过出口**，`--no-check` 那个静默后门已在 P11 里删掉）—— 强制率是要盯的指标。
- [ ] **14. 本步该推的知识库片段看了吗？** `bird.py brief <db_id> --step <当前步骤>`
      （step 1 形状 / 2 骨架 / 3.5 概念 / 4 方言+口径 / 5 判定 / 7 复盘）。

---

## 反模式（不要做）

- ❌ 读 `data/**/mini_dev_sqlite.json` 或 `*_gold.sql` 抄答案，或用 `--reveal`（第 7 步复盘除外）。
- ❌ 把复盘时看到的金标 SQL 拼回 `answers.json` —— 那是对答案的拟合，不是解题。
- ❌ **复盘扫金标时不按已提交题过滤** —— 会把**未做的题连同金标**一起看进去变成抄答案。
  本轮踩过：扫本库“题干含 within normal”的题学输出约定，结果把 5 道未做的题（1205/1207/1212/1213/1217）连带金标看了。
  ⇒ **扫描前先 `if str(i) in answers` 过滤**（只看已提交/已评分的题）。
- ❌ 一次读完整个库的所有列（`bird_schema` 不带 `table` 就是这个原因）。
- ❌ 一题失败就在同一思路上微调十次（先按 `diagnosis.md` 分类错因）。
- ❌ 把 `question_id` 当题号。

## 效率与并发纪律

- ⚠️ **`bird_answer` 与 `bird_score` 不在同一批并发调用**（会读到写入前的旧答案）。
- ⚠️ **同一题不试第 3 种写法**：skill 写明"先试 A 不行改 B"的照做；B 也不行就**交 B**、
  记入挂起清单、做下一题。正确的修法是把根因写回 `db/<库>.md`，下次同类题一次做对。
- **同库连做**（schema 认知跨题复用）；一批 10–20 题一起提交，再跑一次 `bird_score`。
- 每批按**错因分类**记录（用 `bird.py audit` 自动出分布）：是"值差一个"还是"行数差一截"？
  前者是口径/惯例问题，后者是条件/表集合问题。

---

<!-- canon:resubmit  唯一出处。别处只许指路，不许抄一遍（tools/tests/check_docs.py 会查）-->
## ⛔ 提交之后：什么情况下允许重交（**唯一出处**）

**允许重交**（都属于“有明确依据”，不是猜）：

1. **列名 / 表名硬错**：执行时报 `no such column` / `no such table` ⇒ 按真列名改，**重交**（不算 EX 错）。
2. **取值大小写 / 字面错**：探到真值是 `'Restricted'` 而你写了 `'restricted'`（0 行 vs 636 行）⇒ 重交。
3. **形状声明被闸门 2 拒**（与实测不符）⇒ 改对**重交**。
4. **执行失败**（金标自身超时那类除外）⇒ 修好**重交**。
5. **返回空集**（硬触发器：多半是条件写错表 / 值错）⇒ 查明依据后重交。
6. **skill 已写明的修法**（`traps.md` 的“列序 = 题干顺序”、CDS 的 naive→CAST、`diagnosis.md` 的四类 detail 对策）⇒ 重交。

**不允许重交**：

- 纯“再猜一种口径”（没有任何新依据）⇒ 记进挂起清单，做下一题。
- **复盘时已经看过金标的题** ⇒ 那是看着答案改，不是做题（见硬规则 1）。

> 别处（`SKILL.md` 硬规则 6、`AGENTS.md`、`traps.md`、`diagnosis.md`、`casebook.md`）**只许指路，不许再抄一遍**：
> 抄第二份就必然和这里漂移。`tools/tests/check_docs.py` 会检查“白名单正文只出现在一处”。
