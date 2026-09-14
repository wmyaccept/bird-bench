---
name: bird-sql
description: 解 BIRD-SQL / Mini-Dev 的 Text-to-SQL 题目。当用户提到 BIRD、bird-bench、text-to-sql 数据集、mini_dev、或要求"做第 N 道 SQL 题/按官方口径打分"时使用。包含读题、探 schema、只读试跑、提交、算 EX 的完整工作流，以及用 bird_score 的失败明细反推错因的诊断手册、金标写法与同名列等实测坑。
license: CC BY-SA 4.0（BIRD 数据集遵循此协议）
---

# 解 BIRD 题目的工作流

BIRD 的评测指标是 **EX**：预测 SQL 的结果集与金标 SQL 的结果集**完全相同**才算对。
本 skill 是入口和索引，**细节都在 `references/` 下按需加载**。

## 硬规则（每次都要遵守）

1. **不许偷看金标。** 不读 `data/MINIDEV/mini_dev_sqlite_gold.sql`、不读题目 JSON 的 `SQL` 字段、
   不用 `bird_question --reveal`。**唯一例外**：一批题做完后的复盘，见
   [`references/casebook.md`](references/casebook.md)。
2. **只写只读 SQL。** `bird_query` / `bird_answer` 只接受 `SELECT / WITH / EXPLAIN`，这是工具层的强制约束。
3. **用 `idx` 当题号，不要用 `question_id`。** 500 题里没有一个 `question_id` 等于它的下标。
4. **`bird_answer` 和 `bird_score` 不要放在同一批并发调用里** —— 会读到写入前的旧答案，
   让你看到过期的失败结果。（本项目真踩过。）
5. **改答案只能通过 `bird_answer`**，不要手写 `work/answers.json`。

## 一条题目的标准流程

按顺序走，不要跳步：

1. **`bird_list`** —— 挑题，拿到 `idx`（是题号，不是 `question_id`）。新手先做 `difficulty: "simple"`。
2. **`bird_question <idx>`** —— 读题干 + **evidence**（evidence 常直接给出口径）。
3. **认题型、套骨架** —— 先看 [`references/playbooks.md`](references/playbooks.md) 的 A 部分；
   **进入一个新库时，先读 B 部分的"该库连接图"**，后面几十题都能复用。
4. **`bird_schema <db_id> table=<关键表>`** —— 列类型、主键、去重样例值 + 人工标注的字段含义。
5. **`bird_query <db_id> "SELECT ..."`** —— 只读试跑，反复用到确信。
6. **`bird_answer <idx> "<最终SQL>"`** —— 提交；跑不通会被拒绝并回报错误。
7. **`bird_score`** —— 看 EX 和错题 detail（解读方法见 `diagnosis.md`）。

> 效率要点：**同库连做**，一批 10–20 题一次提交、一次评分；只在 `bird_score` 报错时才回头推理。
> 不要一题一探、一题一评。

## 索引：什么时候读哪个文件

| 你的处境 | 读这个 |
|---|---|
| **准备做一批题** ← 开始前先看这个 | [`playbooks.md`](references/playbooks.md)（题型骨架 + 各库连接图） |
| "这样算对了吗？列顺序、DISTINCT 到底有没有影响？" | [`scoring.md`](references/scoring.md) |
| "准备提交了，查一遍" | [`checklist.md`](references/checklist.md) |
| **"`bird_score` 说我错了，为什么？"** | [`diagnosis.md`](references/diagnosis.md) |
| "我知道行数/列数对不上，但不知道改成什么" | [`diagnosis.md`](references/diagnosis.md) 的"行列反推手册" |
| "金标返回的形状很奇怪，不合常理" | [`gold-style.md`](references/gold-style.md) |
| "该用哪张表的哪一列？" | [`naming-traps.md`](references/naming-traps.md) |
| "形状对了但值算不对" | [`calibration.md`](references/calibration.md) |
| "SQLite 里这个函数怎么写？这列有脏数据吗？" | [`sqlite-and-data.md`](references/sqlite-and-data.md) |
| "这题之前错过吗？复盘记录在哪？" | [`casebook.md`](references/casebook.md) |

## 维护约定（改这个 skill 时）

- **新增经验先判断"什么时候会用到它"**，按上面的索引归到对应文件，不要都往 SKILL.md 塞
  （SKILL.md 会常驻上下文，其他文件按需加载）。
- 每条经验都要带**实测题号 + 具体数字**（如 "`idx 347`：金标 67 行 = 37+30"），否则以后没法验证。
- 归纳规则前过一遍收录标准：**这条规则能让我写出更接近金标的 SQL 吗？**
  只能教你复现一个 bug 的规则不收（例：`idx 222`）。
- 规则是要改的：`NULL` 排序那条就被 `idx 211` 推翻过一次，现在的写法是"准备两套写法都试"。
  **发现了反例就立刻改，不要留着自相矛盾的条款。**
- 改完用 `bird_score` 在**没做过的题**上验证，别只在错题上验证（错题已经"见过答案"了）。
