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
6. ⭐ **“不许思考”= 不许漫游，不是不许走流程**：流程必须一次走完（第 0 → 6 步），每一步的**产物**（惯例卡片、概念裁决、形状声明、勾选留痕）都得真写出来。
   被禁的是：同一题试第 2 种写法、穷举候选、“再试一种看看”、改完又改 —— **按流程执行是执行，漫游式试错才是思考**。
   同一题卡住 ~1 分钟 → 交手上最好的一条、记入挂起清单、做下一题；唯一允许的“试两次”是 skill **已写明**“先试 A 不行改 B”的情形（如 CDS naive→CAST、探针 2 轮内）。
   **重交只允许 `checklist.md` 末尾「⛔ 重交白名单（唯一出处）」里列的情形**（此处不重复）。

---

## 工作流（7 步）

### 第 0 步｜**换新库时先做结构体检**（换新库时一次性；已有档案就直接读）

📖 **读**：`db/<db_id>.md`（**只读当前库那一个文件**，不要翻别的库）
⚠️ **没有档案**（新库/Test 巨型库）⇒ 档案是缓存，跑 `traps.md` ⓪-1 冷启动五查；`conventions` 此时为空，别当「没惯例」。
📤 **产出**：表数/列数/主键重复度/**两两 JOIN 命中率**，补进该档案的 **`## 连接图与坑`**
（"体检单"不是另一个文件，就是这一节）

### 第 0.5 步｜⭐⭐ **惯例体检：把“猜惯例”换成“查惯例”**（换库时一次性，30 秒）

```bash
# bash 批量做（pi 会话里用同名工具：bird_brief / bird_conventions / bird_cols / bird_attrs）
python tools/bird.py --dataset dev2025 brief <db_id>            # ★ 本题库的知识 + 档案推到眼前
python tools/bird.py --dataset dev2025 conventions --db <db_id> --write-card   # ★ 写回惯例卡片
python tools/bird.py --dataset dev2025 cols <db_id> "type|option"   # 列名反查
```

⭐ **知识库不靠“我主动去读”**：`references/*.md` 里 `<!-- push step=N -->` 包住的片段会被 `brief` 按步骤推送
（文档是唯一数据源：改文件 = 改推送内容）；`db/<库>.md` 的「必查」与「惯例卡片」还会在 **`answer` 成功时自动回放**。

`conventions` **只统计已提交题**的金标（绝不碰未做的题），给的是**这个库自己**的写法分布：
计数形态、主表（`FROM` 第一张表是谁）、`SELECT DISTINCT` 比例、`*100`、JOIN 数。
**这里不抄数字**（必然过期）：跑 `bird_conventions` 或读卡片（两者同源）。
⭐ **卡片由工具写、不手改**（`write_card=true`）：同一份统计渲染 ⇒ 不会出现两套数。

📤 **产出**：本库“惯例卡片”，直接追加进 `db/<db_id>.md`（例：`db/thrombosis_prediction.md` 末尾）。

### 第 1 步｜**选题 + 读题**

选题（**同库连做**）：`bird_list <db> <difficulty>` 挑没做的题；`bird_info` 看进度，`bird.py answers | rg <库名>` 看本库已交。

`bird_question <idx>` → 题干 + **evidence**。
📤 **产出**：① 题型 ② evidence 给的口径/阈值/列名（**逐条划出来，后面要对着实现**）

### 第 2 步｜**认题型、套骨架**

📖 **读**：`shapes.md` 的 A 部分（**A1–A11**；`comprehensive profile / statistics` 那类看 **A11**）
📤 **产出**：这道题属于哪个骨架（A1 单属性 / A2 极值 / A4 计数 / A5 列表 / A6 比率 …）

### 第 3 步｜**查当前库的“交题前必查 3 条”**

📖 **读**：`db/<db_id>.md` 顶部的 **⚠️ 交题前必查**
📤 **产出**：这次写 SQL 要特别防的 3 条（例：`card_games` = ① DISTINCT ② 值首字母大写 ③ `=` vs `LIKE`）


### 第 3.5 步｜⭐ **两个概念先定位（列名靠猜是最贵的错）**

题干里的**概念名词**（办学类型、资助类型、区号、职务、地名…）必须**查出**它对应哪一列，不许用英文语感猜。
两个方向都查：概念是"值"还是"列名"？

| 概念形态 | 用什么查 | 例 |
|---|---|---|
| 以**值**存在库里（“continuation / locally funded”） | `find <db> <词>`（`bird_find` / `bird.py find`） | `find california_schools "option"` → `frpm."Educational Option Type"` |
| 是**列名**概念（“district code / funding type”） | **`bird.py cols <db> "code|type"`** ← ★ 新增的反查器 | `cols california_schools "type|option"` 一次列出所有命中列 + **非空/去重行数** |
| 是**库级写法**（该不该 DISTINCT、主表是谁） | `bird.py conventions --db <db>`（第 0.5 步） | 例：`thrombosis_prediction` 的主表是谁、计数该不该 DISTINCT，卡片里都写着 |

📤 **产出（写 SQL 前必须显式写出这两行，不许只在脑子里想）**：

```
概念 → 候选(表.列) → 裁决依据
“办学类型” → frpm."School Type" / frpm."Educational Option Type" → 行集合相同 ⇒ 任选
```

**命中 ≥2 列时的裁决顺序见 `traps.md` ⓪**（evidence 点名 → 只有一列命中 → 行集合相同则任选 → 否则选更专门的那列）。


### 第 4 步｜**写 SQL（对着陷阱表逐条过）**

📖 **读**：`traps.md` —— 它不是按主题、而是**按你正在写的部分**组织的：
写 `SELECT` 看 ①、写 `JOIN` 看 ②、写 `WHERE 值` 看 ③、写聚合看 ④。
⭐ **④ 开头是「值层六问」**（表 / 数实体还是行 / `DISTINCT` / `*100` 与分母 / 要值还是要整行 / NULL）
—— 落笔前按顺序问一遍（`traps.md` ④、`checklist.md` 8b）。
📤 **产出**：SQL

⭐ **写 `SELECT` 列之前的固定动作（治列序错）**：把题干里的概念**按出现的先后标号**，
SQL 里就照这个顺序写，并在 SQL 上留一行注释当自检：

```sql
-- 题干顺序: ① in which city ② lowest grade ③ indicate the school name
SELECT City, `Low Grade`, `School Name` FROM ...
```

（EX 是 `set(预测) == set(金标)` ⇒ **列序和列数同级重要**，`california_schools` 81 就是列集合全对、只因顺序反了得 0 分。）

⭐⭐ **表与计数形态的固定动作**（`audit` 里 `main`/`count` 差得多，就是这四个动作没做；实测案例见 `traps.md` ②/④）：

1. **主表**：按第 0.5 步的惯例卡片选 `FROM` 第一张表 —— 多表库里主表决定**行宇宙**，选错表等于换了候选集，**值必然不同**。
2. **表集合最小化**：只 JOIN 题干真正用到的表（多 JOIN 一张 = 行数变了）。
3. **计数形态三选一**（默认照惯例卡片）：`COUNT(主表.主键列)` 是默认 → `COUNT(DISTINCT 列)` 仅当本库以 DISTINCT 为主或 evidence 明写 → `COUNT(*)` 只在规范统计里明显时用。
4. **不要随手加 `DISTINCT`**（每个库的比例看卡片，不背数字）。

### 第 5 步｜**提交前自检**

📖 **读**：`checklist.md` —— **逐条勾**，不许跳。
📤 **产出**：提交 or 改（勾不过就改，一次改完直接交，不要反复）

### 第 6 步｜**提交（四道机器闸门，过不去交不上）**

```bash
# ① 探针留痕：run / find / cols / schema 带 --for <idx>（下面闸门 1 的凭据）
python tools/bird.py --dataset dev2025 run <db> "SELECT DISTINCT 列 FROM 表 LIMIT 5" --for <idx>
# ② 先看列数先验（闸门 4 的下界、同模板已提交题给了几列）
python tools/bird.py --dataset dev2025 attrs <idx>   # ai 工具名 bird_attrs
# ③ SQL 最前写形状声明；④ --checks 勾选；⑤ --attrs 属性清单（条数必须 == 列数）
python tools/bird.py --dataset dev2025 answer <idx> "/* shape: 3x1 */ SELECT ..." \
  --checks "0,1,1b,2,2b,4,5,5b,8,8b,10,12,13,13b" --attrs "属性1|属性2|属性3"
```

| 闸门 | 规则 | 不过会怎样 |
|---|---|---|
| **闸门 1 探针覆盖** | 该 idx 在 `work/probe_log.jsonl` 里必须有**真探针**记录（`tables/schema/desc/run/find/cols` 之一；**`checks` 与 `force` 不算** —— 硬交过一次不会让这题以后免探针），且**按数据集隔离**（minidev 的 344 ≠ dev2025 的 344） | `answer` 拒绝记录并告诉你该跑哪条 |
| **闸门 2 形状预演** | SQL 里必须有 `/* shape: 行数x列数 */`，且必须与实测一致（**拿完整结果比**，`--max-rows` 只管预览） | 拒绝记录（不符时告诉你实测几行几列） |
| **闸门 3 勾选留痕** | `--checks` 必须给出真实条目号（`checklist.md` 里带 `<!-- core -->` 的核心条目缺一不可） | 拒绝记录（缺条目时告诉你差哪一条） |
| **闸门 4 属性清单** | `--attrs "属性1\|属性2\|…"`：每条必须是题干/evidence 里的**原文片段**，**条数 == SELECT 列数**；且列数不得低于**列数下界** = max(同模板已提交题的金标列数, 本库×难度金标列数 P20) | 拒绝记录（少列时把“同模板给了几列”摆出来） |

⭐ 闸门 4 治「少给列」（怎么标定的、为什么不能更硬 → `traps.md` ⓪）。

📤 **产出**：`work/answers_dev2025.json` 的一条记录 + `work/probe_log.jsonl` 的探针/勾选/属性留痕。

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

⭐ **一个库做完后必做「挂起清单集中复盘」**（最高产的一步；逐条做法见 `diagnosis.md`）：
形状完全对、只有值不同那类挂起题**一次性**拉出来和金标 SQL 并排看（**只有复盘能看金标**，硬规则 1），
按**类**归因（列序 / 概念→列映射 / JOIN / NULL / 极值口径 / 并列 / 去重 / 值字面），
**同一类攒到 ≥2 道才毕业成规则**；只有 1 个样本时写成「先两种都算」的触发检查项。
⚠️ 扫金标前先按 `str(i) in answers` 过滤（否则会顺手把未做的题连同金标看进去，实测踩过）；
⚠️ **绝对不许把金标 SQL 拼回 `answers.json`** —— 复盘只产出规则，不产出答案。
⭐ **毕业必须当场验证**：写完立刻 `rg <这条规则的语义核心词> <目标文件>`，命中才算真的写进去了
（"声称写过"和"真的在那"是两件事，实测抽查 12 处声明逮到 1 处根本没写）。

---

## 出错之后

| 处境 | 读什么 |
|---|---|
| "`answer` 被闸门拒了" | 按它的提示**改一次**再交（探针 → 去跑一条；形状 → 对实测；勾选 → 补缺的条目；属性 → 补/删列）；**不许直接 `--force`** |
| "`bird_score` 说我错了，为什么？" | `diagnosis.md`（含"行列反推手册"） |
| "形状对但值不对，改了还是不对" | `diagnosis.md` 的止损规则 → 通常该去做**口径实验**（见下） |
| "金标返回的形状很奇怪" | `gold-style.md` |
| "SQLite 里这个函数怎么写 / 这列有脏数据吗" | `sqlite-and-data.md` |
| "该用哪张表的哪一列" | `naming-traps.md` |
| "形状对了但值算不对" | `calibration.md` |
| "这样算对了吗？列顺序、DISTINCT 有影响吗" | `scoring.md` |
| "这题之前错过吗" | `casebook.md` |

⚠️ **止损规则**：同一题试过 2 种写法、或 probe 过 2 轮还没定 → **挂起**（落盘形式见 `diagnosis.md`），继续下一题。
⚠️ **口径实验**（一批里 ≥30% 的错题是"形状对、值不同"时做 —— 一轮看清，别逐题猜）：做法见 `calibration.md`。

---

## 维护约定（改这个 skill 时）

📖 见 `references/maintaining.md`（维护原则 + 「下次又漏了规则」的自查 3 条；**做题时不用读**）。

📤 **产出**：规则写回 `traps.md` / `checklist.md` / `db/<库>.md`（`casebook.md` 只记账）+ 当场 `rg` 验证命中。
