# 提交前必勾（固定 12 条，按顺序过）

> 用法：`bird_answer` 之前**从头到尾扫一遍**。每条都对应实测踩过的坑，不是理论清单。
> 勾不过 → 改一次 → 直接交（**不要反复试**，那是违反 SKILL.md 硬规则 6）。

## A. 形状（先看这个，形状错 = 100% 错）

- [ ] **1. 列数 = 题干提到的概念数？** 三种偏差都实测过：
      金标少给（`card_games` 435「How many X? **List out the id**」→ 只要 id）、
      金标多给（`toxicology` 264「labels for A, B and C」→ **2 列**，多一个实体 id）、
      金标拼接（`financial` 1000「full location」→ 1 列）。
      ⇒ **拿不准时，题干里每个名词都给一列。**
- [ ] **2. 行数量级对吗？** 心里估一下：问"哪个/谁"→ 通常 1 行；"列出 X"→ 几十行；
      "多少 X"→ 1 行 1 列。**对不上量级就是口径或 JOIN 错了**，别硬交。
- [ ] **3. 要不要 `DISTINCT`？** ← 看 `db/<当前库>.md` 的"必查"。
      `card_games` 要（387: 187→10）；`formula_1` 混合（956 金标是**行级 224 行**）；
      `european_football_2` 的属性题**既不去重也不 `LIMIT 1`**。

## B. 空集与值（最常见的"形状对但不该是空"）

- [ ] **4. 结果是空的吗？** 空 = JOIN 条件错 / 值匹配失败 / 大小写不对 / 格式不对。
      **先 `SELECT DISTINCT 该列` 看真值**（`card_games` 小写 `'restricted'` = **0 行**，真值 636 行）。
- [ ] **5. `WHERE` 里的每个值都核对过库内真写法吗？** 每个库风格都不同：
      `card_games`/`thrombosis_prediction` **首字母大写**；`california_schools` **小写 f**。
      **evidence 给的值不一定是库里的写法。**
- [ ] **6. 日期是哪种格式？** `'YYYY-MM-DD'` / `'YYYYMM'` / `'YYYY-MM-DD HH:MM:SS.0'` 都出现过。
      **动手前 `SELECT 该列 FROM 表 LIMIT 1`。**（`financial` 的旧笔记是 Mini-Dev 的 `'930101'`，Dev 已改）
- [ ] **7. 多值串列用 `=` 还是 `LIKE`？** 先试精确匹配：
      `card_games` 376 `keywords='Flying'`=**3088**（金标）vs `LIKE '%flying%'`=5039。

## C. 口径（形状对、值不对的元凶）

- [ ] **8. evidence 的每一个口径都实现了吗？** 逐条对着看到第 1 步划出来的口径：
      阈值、`DISTINCT`、分母、列名、单位。（evidence 写 `COUNT(full_name)` 就别用 `COUNT(*)`）
- [ ] **9. 聚合函数旁边还有非聚合列吗？** 有 → **必须 `GROUP BY`**
      （`student_club` 1467：忘了 → 1 行 vs 金标 7 行）。
- [ ] **10. 分母是"行数"还是"去重实体数"？** 先试行数；题干主语是**实体**且 JOIN 会扇出时
      用 `COUNT(DISTINCT 实体id)`（`codebase_community` 709：2 vs 4）。
- [ ] **11. 取极值时查并列了吗？** `superhero` 837（`MIN=5` 有 **10 个**并列）、
      `financial` 101（**315 个** account 并列）。
      行数不对 → 换 `WHERE col = (SELECT MIN/MAX(col) ...)`。
      ⚠️ **NULL 在 `ORDER BY ASC` 排最前**，取"最小/最早"别用 `LIMIT 1`（`codebase_community` 663）。

## D. 最后一眼

- [ ] **12. 当前库档案的"⚠️ 交题前必查 3 条"过了吗？** 回到 `db/<db_id>.md` 顶部逐条对。

---

## 反模式（不要做）

- ❌ 读 `data/**/mini_dev_sqlite.json` 或 `*_gold.sql` 抄答案，或用 `--reveal`（第 7 步复盘除外）。
- ❌ 把复盘时看到的金标 SQL 拼回 `answers.json` —— 那是对答案的拟合，不是解题。
- ❌ 一次读完整个库的所有列（`bird_schema` 不带 `table` 就是这个原因）。
- ❌ 一题失败就在同一思路上微调十次（先按 `diagnosis.md` 分类错因）。
- ❌ 把 `question_id` 当题号。

## 效率与并发纪律

- ⚠️ **`bird_answer` 与 `bird_score` 不在同一批并发调用**（会读到写入前的旧答案）。
- ⚠️ **同一题不试第 3 种写法**：skill 写明"先试 A 不行改 B"的照做；B 也不行就**交 B**、
  记入挂起清单、做下一题。正确的修法是把根因写回 `db/<库>.md`，下次同类题一次做对。
- **同库连做**（schema 认知跨题复用）；一批 10–20 题一起提交，再跑一次 `bird_score`。
- 每批按**错因分类**记录：是"值差一个"还是"行数差一截"？前者是口径问题，后者是条件问题。
