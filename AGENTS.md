# 项目约定：BIRD-SQL 解题 Agent

这是一个用 pi 做 **BIRD-SQL / Mini-Dev** Text-to-SQL 题目的项目。
本项目自带一个 extension（工具层）和一个 skill（方法层），两者是一对，别拆开用。

## 目录

```
.pi/extensions/bird-sql/index.ts   工具层：8 个 bird_* 工具（TypeScript）
.pi/skills/bird-sql/
  SKILL.md                         入口：硬规则 + 7 步工作流（每步绑定"读哪个文件"）
  references/
    traps.md                       ★ 写 SQL 时按动作顺序逐条过（SELECT/JOIN/WHERE值/聚合）
    checklist.md                   ★ 提交前固定 12 条必勾
    shapes.md                      题型骨架 A1–A10
    db/<db_id>.md                  ★ 11 个库各一个短档案（顶部"交题前必查 3 条"+ 连接图）
    diagnosis.md / gold-style.md / scoring.md  出错反推 / 金标写法 / EX 判定
    sqlite-and-data.md / naming-traps.md / calibration.md  细节展开（卡住再看）
    casebook.md                    复盘账本（只记账，不放规则）
tools/bird.py                      后端：唯一直接操作 SQLite 的地方
tools/setup_data.py                数据准备：下载 + 选择性解压 + 嵌套 zip
 tools/official_eval/              BIRD 官方评测脚本（已打本地补丁）
data/MINIDEV/                      Mini-Dev 500（开发用轻量集）
data/DEV/                          官方 Dev 集 1534 题（对齐排行榜 Dev 列）
work/answers.json                  minidev 的作答
work/answers_dev.json              dev 的作答（**与 minidev 分开**，idx 体系不同）
work/score/                        评测产物（pred 文件 + 逐题明细）
SUBMISSION_PLAN.md                 打榜提交方案（待执行；含官方 guideline 全文）
```

> **skill 的组织原则**（改的时候别破坏它）：
> 按**做题的时间轴**组织，而不是按主题分类 —— 每题只读**当前库的 1 个短文件**（`db/<库>.md`），
> 写 SQL 时对着 `traps.md` 的动作小节查，提交前逐条勾 `checklist.md`。
> 复盘得到的新规则必须**毕业**到这三个地方之一，不能只留在 `casebook.md`。

## 两个数据集

| key | 题目数 | 难度分布 | 用途 |
|---|---|---|---|
| `minidev`（默认） | 500 | 148/250/102 | 快速迭代、调 skill |
| `dev` | 1534 | 925/464/145 | **旧版 Dev（2024-06）**，已全量做完 simple |
| `dev2025` | 1534 | **860/443/231** | **新版 Dev（2025-11-06 官方修订）← 后续以此为准** |

- `dev` 与 `dev2025` **共用同一批数据库**，`question_id` 一一对应、**idx 顺序完全一致**。
- 新版差异：question 变 11.9%、evidence 变 24.6%、**金标 SQL 变 29.4%**，并有
  **65 道旧 simple 被改写升级为 challenging**（单属性问答 → 多维度分析）。
- 切换：`python tools/bird.py --dataset dev2025 <cmd>`，或环境变量 `BIRD_DATASET=dev2025`。
- 对标基准（官方 README，dev2025 全量 1534）：gemini-3-pro-preview **68.97**、claude-sonnet-4.5 66.56、GPT-5.1 64.02。

### 旧版 Dev 的成绩（已完成）

```
simple 925/925 全部完成，EX 744/925 = 80.43%
```

### 新版 Dev 的复核成绩（用旧答案对新金标）

```
simple 860/860 已答，EX 675/860 = 78.49%
全量：已答 949/1534，正确 697 → 全量 EX 45.44%
```

> ⚠️ 两个 dev 的答案文件**分开存**：`work/answers_dev.json` vs `work/answers_dev2025.json`。

## 解一道题的标准动作

用 `bird_*` 工具，不要用 bash 直接敲 sqlite3，也不要用 read 去翻数据集文件：

1. `bird_list` 挑题 → 拿到 `idx`
2. `bird_question <idx>` 读题干 + **evidence**
3. `bird_schema <db_id>` 看库里有几张表
4. `bird_schema <db_id> table=<表>` 看列、样例值、人工标注的字段说明
4.5 `bird_find <db_id> <概念词>` ⭐ **概念词反查**：题干里的“办学类型/资助类型/区号”这类词
   究竟在哪张表哪一列 —— **列名靠猜是失分最大头，别用英文语感猜**
5. `bird_query <db_id> "SELECT ..."` 只读试跑，反复验证
6. `bird_answer <idx> "<最终SQL>"` 提交
7. 每 10–20 题 `bird_score` 一次，按错因分类

> 工具层目前固定用 `minidev`（extension 里写死了）。要在 `dev` 上做题，
> 直接用 `python tools/bird.py --dataset dev <cmd>`，或给 pi 进程设 `BIRD_DATASET=dev`。

### 在 dev 上批量做题（推荐用法）

extension 只绑了 minidev，所以 dev 的题用 bash 直接调 `bird.py` 并**批量操作**，比一题一次工具调用快得多：

```bash
# 一次读一批题（含 evidence）
for i in 0 2 3 5 6; do "D:/python/python" tools/bird.py --dataset dev question $i; done

# 一次试跑多条候选 SQL
for q in "SELECT ..." "SELECT ..."; do "D:/python/python" tools/bird.py --dataset dev run <db> "$q"; done

# 一次提交多题，然后单独评分（**不要把 answer 和 score 放同一批**）
"D:/python/python" tools/bird.py --dataset dev answer 0 "SELECT ..."
"D:/python/python" tools/bird.py --dataset dev score --list-wrong 12
```

## 硬性规则

- **⭐ 做题时不许思考，思考只在复盘时。** 以 skill 为准，一次定稿就提交；
  **不要左右为难、不要穷举候选、不要“再试一种看看”**。错了就错了，错了再总结
  （错误的价值是写回 skill，不是当场救回来）。同一题想到第 2 种写法或卡住 ~1 分钟 →
  立刻提交手上最好的一条，记进挂起清单，做下一题。详见 `.pi/skills/bird-sql/SKILL.md` 硬规则第 6 条。
- **禁止**读 `data/MINIDEV/mini_dev_sqlite.json` 或 `mini_dev_sqlite_gold.sql` 去抄答案，
  **禁止**用 `bird_question --reveal`。抄答案就失去做题意义了。
- 只写只读 SQL。`bird_query` 和 `bird_answer` 都只接受 `SELECT / WITH / EXPLAIN`，
  这是工具层的强制约束，不是建议。
- 只能通过 `bird.py` 改 `work/answers.json`，不要手写这个文件（格式是官方的
  `SQL<TAB>----- bird -----<TAB>db_id`，很容易写错）。
- **要推送时：固定先问一句，得到同意立刻推。** 流程定死：**改动完成 → 一句话问“要推吗”
  → 用户同意 → 立即 `git push`**。不要先推演“该不该推”，也不要绕一圈最后还是问一句。
- 不要修改 `data/` 下的任何内容。数据集是只读的。
- 不要"顺手优化"`tools/official_eval/` 里的官方脚本——它是官方口径的凭据，
  只在必要处打了标注了 `[本地补丁]` 的改动。

## 环境

- 需要 Python 3.9+（本机实测 3.14.7，`sqlite3` ≥ 3.41 即可）。
- extension 会自动找 `python`；找不到时用环境变量 `BIRD_PYTHON` 指定绝对路径。
- 项目位置不固定也没关系：extension 从 cwd 向上找 `tools/bird.py`，
  也可以用 `BIRD_HOME` 直接指定项目根目录。
- 数据目录可用 `BIRD_DATA_DIR` / `BIRD_WORK_DIR` 覆盖（方便拿小数据集做测试）。

## 改动的边界

- 改工具行为 → 改 `tools/bird.py`（终端里能直接复现），不要改 extension 里的逻辑。
- 改解题策略/提示 → 改 `.pi/skills/bird-sql/` 下的文件。
  **新经验先判断"什么时候会用到"**，归到 `references/` 里对应的那一份；
  `SKILL.md` 只放"每次都走的流程 + 索引表"，不要往上塞细节（它会常驻上下文）。
- 只有"给工具加参数、加工具、改工具描述"才动 `index.ts`。
- extension 和 skill 的 `description` 决定 pi 什么时候加载它们，改的时候要一起想清楚。
