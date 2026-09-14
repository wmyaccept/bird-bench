# 项目约定：BIRD-SQL 解题 Agent

这是一个用 pi 做 **BIRD-SQL / Mini-Dev** Text-to-SQL 题目的项目。
本项目自带一个 extension（工具层）和一个 skill（方法层），两者是一对，别拆开用。

## 目录

```
.pi/extensions/bird-sql/index.ts   工具层：7 个 bird_* 工具（TypeScript）
.pi/skills/bird-sql/
  SKILL.md                         入口：硬规则 + 7 步流程 + 索引表
  references/                      方法层：按需加载的 8 份手册（见 SKILL.md 的索引表）
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

## 两个数据集

| key | 题目数 | 难度分布 | 用途 |
|---|---|---|---|
| `minidev`（默认） | 500 | 148/250/102 | 快速迭代、调 skill |
| `dev` | 1534 | 925/464/145 | **和排行榜 Dev 列（人类 92.96 / GPT-4 46.35）可比** |

- 切换：`python tools/bird.py --dataset dev <cmd>`，或环境变量 `BIRD_DATASET=dev`。
- 准备数据：`python tools/setup_data.py --dataset dev`（330 MiB）。
- ⚠️ **Mini-Dev 是 Dev 的子集**（500 题里 494 题题干与 Dev 完全相同）。所以两边的
  `answers` 必须分开存，否则 idx 会串号。已做过的题用题干映射迁移。
- ⚠️ **两个文件的金标不完全一致**：可映射的 496 题里有 13 题金标 SQL 不同（2.6%）。
  因此同一道题可能在 Mini-Dev 对、在 Dev 错。**以 Dev 为准**（排行榜用的是 Dev）。

## 解一道题的标准动作

用 `bird_*` 工具，不要用 bash 直接敲 sqlite3，也不要用 read 去翻数据集文件：

1. `bird_list` 挑题 → 拿到 `idx`
2. `bird_question <idx>` 读题干 + **evidence**
3. `bird_schema <db_id>` 看库里有几张表
4. `bird_schema <db_id> table=<表>` 看列、样例值、人工标注的字段说明
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
