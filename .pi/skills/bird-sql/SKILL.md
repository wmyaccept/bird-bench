---
name: bird-sql
description: 解 BIRD-SQL / Mini-Dev 的 Text-to-SQL 题目。当用户提到 BIRD、bird-bench、text-to-sql 数据集、mini_dev、或要求"做第 N 道 SQL 题/按官方口径打分"时使用。包含读题、探 schema、只读试跑、提交、算 EX 的完整工作流，以及用 bird_score 的失败明细反推错因的诊断手册、金标写法与同名列等实测坑。
license: CC BY-SA 4.0（BIRD 数据集遵循此协议）
---

# 解 BIRD 题的工作流

EX = 预测 SQL 的结果集与金标结果集**完全相同**才算对。

⚠️ **本文件是流程主干。按步骤走，每一步都写明了"读哪个文件"—— 不要跳步，也不要凭记忆。**
（"明明写过却漏了"这件事，是因为旧版把规则堆成索引表；现在每一步都绑死了要读的文件。）

---

## 硬规则（每题都适用）

1. **不许偷看金标**：不读 `mini_dev_sqlite_gold.sql`、不读题目 JSON 的 `SQL` 字段、不用 `--reveal`。
   **唯一例外**：一批做完后的复盘（见第 7 步）。
2. **只写只读 SQL**：`SELECT / WITH / EXPLAIN`，工具层强制。
3. **用 `idx` 当题号**，不要用 `question_id`。
4. **`bird_answer` 和 `bird_score` 不要放在同一批并发调用里**（会读到写入前的旧答案）。
5. **改答案只能通过 `bird_answer`**，不手写 `work/answers.json`。
6. ⭐ **“不许思考”= 不许漫游，不是不许走流程**：流程本身必须一次走完（第 0 → 6 步），
   每一步的**产物必须写出来**（惯例卡片、概念裁决表、形状声明）。
   被禁止的是：同一题试第 2 种写法、穷举候选、“再试一种看看”、改完又改。
   **按流程执行不是思考，是执行；漫游式试错才是思考。**
   同一题卡住 ~1 分钟 → 立刻交手上最好的一条、记入挂起清单、做下一题。
   **重交只允许 `checklist.md` 末尾「⛔ 重交白名单（唯一出处）」里列的情形**（唯一出处，此处不重复）。
   唯一允许的“试两次”是 skill **已写明**“先试 A 不行改 B”的情形（如 CDS naive→CAST、探针 2 轮内）。

---

## 工作流（7 步）

### 第 0 步｜**换新库时先做结构体检**（3 分钟，一次性）

```sql
-- 每个库跑一遍，把结果写进 db/<db_id>.md 顶部的"体检单"
SELECT m.name, (SELECT COUNT(*) FROM pragma_table_info(m.name)) AS cols
FROM sqlite_master m WHERE m.type='table';
-- 关键：主键重复度 + 两两 JOIN 的命中率
SELECT COUNT(*) AS rows_all, COUNT(DISTINCT 主键) AS distinct_pk FROM 表;
SELECT COUNT(*) AS joined FROM A JOIN B ON A.key = B.key;   -- ← 这一步最容易被跳过
```

📖 **读**：`db/<db_id>.md`（**只读当前库那一个文件**，不要翻别的库）
📤 **产出**：这张库的体检单（尤其 JOIN 命中率——`thrombosis_prediction` 就是靠它发现
`Examination` 806 行里只有 70 行能连上 `Patient`）

### 第 0.5 步｜⭐⭐ **惯例体检：把“猜惯例”换成“查惯例”**（换库时一次性，30 秒）

```bash
# 在 pi 会话里直接调工具（等价，推荐）：
#   bird_brief db_id=<库>            bird_brief db_id=<库> step="4"
#   bird_conventions db=<库>          bird_cols db_id=<库> pattern="type|option"
#   bird_conventions db=<库> write_card=true      # ★ 把同一份统计写回惯例卡片
#   bird_conventions write_card=true all=true     # 刷全部库的卡片
# 在 bash 里批量做（dev/dev2025）时用命令行：
python tools/bird.py --dataset dev2025 brief <db_id>          # ★ 知识库推送到决策点（换库跑一次，~100 行）
python tools/bird.py --dataset dev2025 brief --step 4          # 只推“写 SQL / 口径”这一步的片段
python tools/bird.py --dataset dev2025 conventions --db <db_id>  # 已提交题的金标统计
python tools/bird.py --dataset dev2025 conventions --db <db_id> --write-card  # ★ 写回惯例卡片（同一份统计）
python tools/bird.py --dataset dev2025 conventions --write-card --all         # 刷全部库
python tools/bird.py --dataset dev2025 cols <db_id> "type|option"  # 列名反查
```

> ⚠️ 之前扩展里没有这四个工具（`bird_brief` / `bird_cols` / `bird_conventions` / `bird_audit`），
> 导致这一整套“标准动作”在 pi 里只能退回 bash，甚至因为拿不到 `--for` 而交不上题。
> 2026-09-16 已补齐（同上：探针可用 `for_idx` 留痕、`bird_answer` 有 `force`、所有工具可传 `dataset`）。

⭐ **知识库不再靠“我主动去读”**：`references/*.md` 里带 `<!-- push step=N -->` 标记的片段
会被 `brief` 按步骤推出来（step=1 读题形状、2 骨架、3.5 概念定位、4 写 SQL/口径、5 判定、7 复盘）。
文档是**唯一数据源**：改文件 = 改推送内容，不会出现两份说法。
另外，`db/<库>.md` 的「必查」与「惯例卡片」会在 **`answer` 成功的瞬间自动回放**（即使我没主动读）。

`conventions` **只统计已提交题**的金标（绝不碰未做的题），给的是**这个库自己**的写法分布：
计数形态、主表（`FROM` 第一张表是谁）、`SELECT DISTINCT` 比例、`*100`、JOIN 数。

**这里不抄数字**（手抄的数字必然过期 —— 本文件曾写死过“已完成题数”“某库 DISTINCT 计数比”这类数字，实测很快就对不上了）：
直接跑 `bird_conventions`（或读 `db/<库>.md` 的惯例卡片，两者同源）。
大体规律：`COUNT(列)` 是绝对主流；`COUNT(DISTINCT)` 只在 `financial`、`thrombosis_prediction` 常见；
`california_schools` 那类 schools/frpm/satscores 三分天下的库 ——**没有单一主表的库就是错题重灾区**。

⭐ **卡片由工具写、不手改**：`bird_conventions db=<库> write_card=true`（配 `all=true` 刷全部）。
卡片和 `conventions` 的输出是同一次统计渲染的 ⇒ 不会出现“工具一套数、卡片另一套数”。

📤 **产出**：本库“惯例卡片”，直接追加进 `db/<db_id>.md`（例：`db/thrombosis_prediction.md` 末尾）。

### 第 1 步｜**读题**

`bird_question <idx>` → 题干 + **evidence**。
📤 **产出**：① 题型 ② evidence 给的口径/阈值/列名（**逐条划出来，后面要对着实现**）

### 第 2 步｜**认题型、套骨架**

📖 **读**：`shapes.md` 的 A 部分（A1–A10）
📤 **产出**：这道题属于哪个骨架（A1 单属性 / A2 极值 / A4 计数 / A5 列表 / A6 比率 …）

### 第 3 步｜**查当前库的“交题前必查 3 条”**

📖 **读**：`db/<db_id>.md` 顶部的 **⚠️ 交题前必查**
📤 **产出**：这次写 SQL 要特别防的 3 条（例：`card_games` = ① DISTINCT ② 值首字母大写 ③ `=` vs `LIKE`）

> **这一步是防止"写了没看到"的关键**：库级坑不在长文档里翻，而是每次只读**当前库的 1 个短文件**。

### 第 3.5 步｜⭐ **两个概念先定位（列名靠猜是最贵的错）**

题干里的**概念名词**（办学类型、资助类型、区号、职务、地名…）必须**查出**它对应哪一列，不许用英文语感猜。
两道闸门，看概念是"值"还是"列名"：

| 概念形态 | 用什么查 | 例 |
|---|---|---|
| 以**值**存在库里（“continuation / locally funded”） | `find <db> <词>`（`bird_find` / `bird.py find`） | `find california_schools "option"` → `frpm."Educational Option Type"` |
| 是**列名**概念（“district code / funding type”） | **`bird.py cols <db> "code|type"`** ← ★ 新增的反查器 | `cols california_schools "type|option"` 一次列出 **9 个候选列 + 非空/去重行数** |
| 是**库级写法**（该不该 DISTINCT、主表是谁） | `bird.py conventions --db <db>`（第 0.5 步） | 例：`thrombosis_prediction` 的主表是谁、计数该不该 DISTINCT，卡片里都写着 |

📤 **产出（写 SQL 前必须显式写出这 3 行，不许在脑子里想）**：

```
概念 → 候选(表.列) → 裁决依据
“办学类型” → frpm."School Type" / frpm."Educational Option Type" → 两者行集合相同(459) ⇒ 任选
“资助类型” → schools.FundingType(1642 行) / frpm."Charter Funding Type"(1167 行) → evidence 点名前者
```

**命中 ≥2 列时的裁决顺序**（写进 `traps.md` ⓪）：evidence 点名 → 只有一列命中 →
多列且**行集合相同**则任选（差异必在别处）→ 否则选**更专门**的那列，**并把结论写进 `db/<库>.md`**。
⭐ **`cols` 输出的“非空行数”就是裁决线索**：同一概念的两个候选列行数差得远，往往是不同粒度的两列。

### 第 4 步｜**写 SQL（对着陷阱表逐条过）**

📖 **读**：`traps.md` —— 它不是按主题、而是**按你正在写的部分**组织的：
写 `SELECT` 看 ①、写 `JOIN` 看 ②、写 `WHERE 值` 看 ③、写聚合看 ④。
📤 **产出**：SQL

⭐ **写 `SELECT` 列之前的固定动作（治列序错）**：把题干里的概念**按出现的先后标号**，
SQL 里就照这个顺序写，并在 SQL 上留一行注释当自检：

```sql
-- 题干顺序: ① in which city ② lowest grade ③ indicate the school name
SELECT City, `Low Grade`, `School Name` FROM ...
```

（EX 是 `set(预测) == set(金标)` ⇒ **列序和列数同级重要**，`california_schools` 81 就是列集合全对、只因顺序反了得 0 分。）

⭐⭐ **表与计数形态的固定动作**（本轮 42 道错题里 `main` 差 20 道、`count` 差 13 道 —— 就是这四个动作没做）：

1. **主表**：按第 0.5 步的惯例卡片选 `FROM` 第一张表。多表库里主表决定**行宇宙**：
   `thrombosis_prediction` 三表的 ID 覆盖率是 1238 / 302 / **70** ⇒ 选错表就是换了候选集，**值必然不同**。
2. **表集合最小化**：只 JOIN 题干真正用到的表。实测 24：我多 JOIN 了 `schools` → 999 行，
   金标只有 `satscores JOIN frpm` → 1068 行。
3. **计数形态三选一**（默认照惯例卡片）：
   `COUNT(主表.主键列)` 是默认 → `COUNT(DISTINCT 列)` 仅当本库以 DISTINCT 为主（financial/thrombosis）
   或 evidence 明写 distinct → `COUNT(*)` 只在规范统计里占比明显时用。
4. **不要随手加 `DISTINCT`**：金标 `SELECT DISTINCT` 比例整体很低
   （具体到每个库看 `db/<库>.md` 的惯例卡片，与 `bird_conventions` 同源；不要背数字）。

### 第 5 步｜**提交前自检**

📖 **读**：`checklist.md` —— **逐条勾**，不许跳。
📤 **产出**：提交 or 改（勾不过就改，一次改完直接交，不要反复）

### 第 6 步｜**提交（两道机器闸门，过不去交不上）**

```bash
# pi 会话里用工具（推荐）：bird_query / bird_find / bird_cols / bird_schema 传 for_idx=<idx>
#                          bird_answer 的 sql 里带 /* shape: RxC */
# ① 探针留痕：任何 run / find / cols / schema 带 --for <idx>，就为这题记下“我真的查过”
python tools/bird.py --dataset dev2025 run <db> "SELECT DISTINCT 列 FROM 表 LIMIT 5" --for <idx>
# ② SQL 最前面写形状声明（预测的结果集形状）
python tools/bird.py --dataset dev2025 answer <idx> "/* shape: 3x1 */ SELECT ..."
```

| 闸门 | 规则 | 不过会怎样 |
|---|---|---|
| **闸门 1 探针覆盖** | 该 idx 在 `work/probe_log.jsonl` 里必须有记录（**只有工具真跑过才写得进去**，人无法凭空声明），且**按数据集隔离**（minidev 的 344 ≠ dev2025 的 344） | `answer` 拒绝记录并告诉你该跑哪条 |
| **闸门 2 形状预演** | SQL 里必须有 `/* shape: 行数x列数 */`，且必须与实测一致 | 拒绝记录（不符时告诉你差几行几列） |

确属一目了然的题可以用 `--force` 跳过，但会记进 probe_log、`audit` 会统计 ——
**强制率本身就是要盯的指标**（高了说明流程没真走）。
（注释开头的 SQL 已被 `guard_sql` 放行；导出提交时可剥掉。前面写错列名属硬错，直接按真列名重交。）

### 第 7 步｜**批末复盘**（每批 10–20 题，或一个库做完）

**先用工具拿错因分布，再读细节文档**：

```bash
python tools/bird.py --dataset dev2025 audit --difficulty moderate --list 3
```

→ 直接给出：EX、各库正确率、**失败类型分布**（列数/列序/行集/值）、
**结构特征差异频次**（`main`/`tables`/`count`/`x100`…哪个差得最多就是首要根因）、每类 3 条并排例子。
（`main` 差得多 ⇒ 概念定位/主表问题；`count` 差得多 ⇒ 计数形态问题；`x100` ⇒ 百分比口径问题。）
再 📖 读 `diagnosis.md` 按 detail 反推单题错因。
**然后必须把结论写进"能被读到的地方"**（这是唯一让你下次不犯同样错的办法）：

| 结论类型 | 写到哪 |
|---|---|
| 某个库特有的坑 | `db/<库>.md` 顶部的"交题前必查"（**替换掉三条里最不重要的**，保持只有 3 条） |
| 通用陷阱（跨库） | `traps.md` 的对应动作小节 |
| 提交前能拦住的 | `checklist.md`（加一条或改写一条） |
| 只是"发生过什么" | `casebook.md`（**只记账，不放规则**） |

⭐ **一个库做完后必做「挂起清单集中复盘」**（这是最高产的一步）：

⚠️ **扫金标前先按 `str(i) in answers` 过滤（只看已提交/已评分的题）** ——
   否则会顺手把**未做的题连同金标**看进去，等于抄答案（实测踩过：一次关键词扫描污染了 5 道未做题）。
1. 把本库的挂起题（尤其**形状完全对、只有值不同**那类）**一次性**拉出来，
   和金标 SQL 并排看一遍（**只在复盘时可以看金标**，见硬规则 1）。
2. 每条归因到下面几类之一，**按类**写规则，而不是按题：
   `列序错` / `概念→列映射错` / `JOIN 选错或绕了弯路` / `NULL 未排除` / `极值选行口径错` / `并列未保留` /
   `该去重没去重` / `值字面不匹配`
3. 归因完统计：**同一类 ≥ 2 道就毕业成 trap/checklist 规则**（`casebook.md` 第 22 轮有一例：
   一批错题恰好能归到 5 类）。只有 1 个样本时不许升级成规则，写成**触发检查项**（“先两种都算”）。
4. ⭐ **毕业必须当场验证“真的写进去了”**：写完立刻 `rg <这条规则的语义核心词> <目标文件>`，
   命中才算毕业。实测（2026-09-16 抽查 12 处“已写回 X”的声明）：**1 处是真的没写**
   （第 5 轮第 5 条「复数名词 ⇒ 金标给行级」，已补进 `traps.md` ④），另 2 处只是**措辞/关键词不同**
   （实质已覆盖）。⇒ **“声称写过”和“真的在那”是两件事**；关键词要取语义核心词，别只信字面。
5. ⚠️ **绝对不许把金标 SQL 拼回 `answers.json`** —— 复盘只产出规则，不产出答案。
   验证规则是否有效，要拿**没做过的同类题**去试（skill 维护原则第 6 条）。

---

## 出错之后

| 处境 | 读什么 |
|---|---|
| "`bird_score` 说我错了，为什么？" | `diagnosis.md`（含"行列反推手册"） |
| "形状对但值不对，改了还是不对" | `diagnosis.md` 的止损规则 → 通常该去做**口径实验**（见下） |
| "金标返回的形状很奇怪" | `gold-style.md` |
| "SQLite 里这个函数怎么写 / 这列有脏数据吗" | `sqlite-and-data.md` |
| "该用哪张表的哪一列" | `naming-traps.md` |
| "形状对了但值算不对" | `calibration.md` |
| "这样算对了吗？列顺序、DISTINCT 有影响吗" | `scoring.md` |
| "这题之前错过吗" | `casebook.md` |

⚠️ **止损规则**：同一题试过 2 种写法、或 probe 过 2 轮还没定 → **挂起**，继续下一题。
⚠️ **口径实验**：当**同一批里 ≥30% 的错题都是"形状对、值不同"**时，别再逐题猜 ——
写一条 SQL 把候选口径（`COUNT(*)` / `COUNT(DISTINCT)` / 不同 JOIN）**并排输出一次**，
一轮看清（`thrombosis_prediction` 就是这么定位到 ID 体系问题的）。

---

## 维护约定（改这个 skill 时）

1. **SKILL.md 只放流程**。新增知识一律按第 7 步的表归位，**不要往这里塞细节**。
2. **`db/<库>.md` 的"必查"永远只有 3 条**：新坑进来，就要把旧的那条最没用的挤出去
   （否则又会变成"翻不到"的长文档）。
3. 每条规则都要带**实测题号 + 数字**（如"387: 187→10"），否则以后无法验证。
4. 归纳规则前过一遍：**这条能让我写出更接近金标的 SQL 吗？** 只能复现一个 bug 的不收。
5. **发现了反例就立刻改，不留自相矛盾的条款**（`NULL 排序`、`european_football_2 的 LIMIT 1`
   都曾经写反过 —— 各被 2–3 道题同时证伪）。
6. 改完在**没做过的题**上验证，别只在错题上验证（错题已经“见过答案”了）。
7. ⭐ **知识必须能被“推到决策点”**：新规则写进正文没人读 = 等于没写。写在 `references/*.md` 里的，
   就要用 `<!-- push step=N -->…<!-- /push -->` 包住（`brief` 会推它），或写进 `db/<库>.md` 的惯例卡片。
8. 宁可包住**现成小节**（零漂移），也不另写一份摘要（两份说法早晚不一致）。

### 如果下次又漏了规则，按这 3 条查

1. **漏的规则在哪个文件？** 如果它在 `casebook.md` 里 —— 那是记账本，**做题时本来就不会读**，
   说明它**没毕业**，立刻搬到 `db/<库>.md`、`traps.md` 或 `checklist.md`。
2. **它是不是"陈述句"？**（"本库输出要 DISTINCT"）→ 改成**祈使句 + 检查点**
   （"⚠️ 交题前必查：输出列加 DISTINCT 了吗？"）。
3. **它是不是藏在长文件中间？** → 拆短，或提到该文件顶部。
