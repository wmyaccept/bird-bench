# BIRD-SQL 解题 Agent（pi skill + tool）

用 [pi](https://github.com/earendil-works/pi-mono) 的 **skill + custom tool** 机制，
给 [BIRD-SQL](https://bird-bench.github.io/) 这个 Text-to-SQL 基准做一套解题 Agent。

BIRD 的评测指标是 **EX（Execution Accuracy）**：预测 SQL 的结果集与金标 SQL 的结果集
完全相同才算对。榜单上人工（数据工程师 + 数据库学生）在 Dev 集上是 **92.96**，
GPT-4 baseline 是 46.35 —— 这条线就是本项目要追的目标。

---

## 1. 设计：为什么要分成 skill 和 tool 两层

pi 里这两层解决的是不同问题，混在一起会写成一个难维护的大杂烩：

| 层 | 位置 | 回答的问题 | 内容 |
|---|---|---|---|
| **tool** | `.pi/extensions/bird-sql/index.ts` | agent **能做什么** | 7 个 `bird_*` 工具：列题、读题、看 schema、只读试跑、提交、算分 |
| **skill** | `.pi/skills/bird-sql/SKILL.md` | agent **怎么做得好** | 解题工作流、BIRD 的三个难点、SQLite 方言表、定稿前自检清单、反模式 |

关键点是 **skill 的内容是按需加载的**（平时只占 system prompt 里一行 description），
所以方法论可以写得很详细而不浪费上下文。

### 三个刻意的设计决定

**① 工具层做薄，后端用 Python**

`index.ts` 不含任何 SQL 逻辑，所有命令都转发给 `tools/bird.py`。好处：
同一套逻辑在终端里直接敲就能复现 —— 老师复核时不需要装 pi，也不需要相信 agent 的自述。

**② 防作弊写在工具层，而不是靠提示词求模型自觉**

- `bird_question` 把 `SQL` 字段从返回结果里 pop 掉，agent 拿不到金标；
- `bird_schema` 不带 `table` 时只返回列名，**不返回样例值** —— 这是为了逼 agent
  收敛关注范围，而不是把几十张表全读进上下文；
- `bird_query` 的连接是 `mode=ro` + `PRAGMA query_only`，语句再用白名单卡一遍
  （只放 `SELECT / WITH / EXPLAIN`），并加超时中断。

**③ 错误当错误报**

`bird_answer` 会先真的把 SQL 跑一遍，跑不通就**拒绝记录**并回报 `sqlite3` 的错误。
这样 agent 拿到的是"你的 SQL 在第几行崩了"，而不是"已保存"，避免它一路瞎猜到最后。

---

## 2. 快速开始

### 2.1 准备数据（约 764 MiB 下载，1.5 GB 落盘）

```bash
python tools/setup_data.py
```

它做了三件事，都不是"下载 + 全解压"那么简单：

1. **选择性解压**：压缩包里除了 SQLite 版，还塞了 MySQL 和 PostgreSQL 各自的 1 GB
   建库脚本。我们只做 SQLite，默认跳过这两个目录，省下约 2 GB。
2. **格式规范化**：包里的题目文件是 `mini_dev_sqlite.json`（JSON **数组**），而官方
   评测脚本的 `--diff_json_path` 只吃 **JSONL**（`load_jsonl` 逐行 `json.loads`）。
   脚本会补生成 `.jsonl`，否则官方脚本一跑就崩。
3. **断点续传**：中断后重跑不会从头下载。

### 2.2 让 pi 信任本项目

project-local 的 `.pi/extensions` 和 `.pi/skills` **只在项目被信任后才会加载**。
在 pi 里执行 `/trust`（或启动时的信任提示里选同意），然后重启 pi。

验证是否加载成功：问 pi "BIRD 数据集状态如何"，它应该去调 `bird_info`。
也可以用 `/skill:bird-sql` 强制加载方法层。

### 2.3 不用 pi 也能跑（给复核用）

```bash
python tools/bird.py info
python tools/bird.py list --difficulty simple --limit 5
python tools/bird.py question 0
python tools/bird.py schema debit_card_specializing
python tools/bird.py desc debit_card_specializing
python tools/bird.py run debit_card_specializing "SELECT * FROM customers LIMIT 3"
python tools/bird.py answer 0 "SELECT ..."
python tools/bird.py score --list-wrong 10
```

---

## 3. 工具清单

| 工具 | 作用 | 对应命令 |
|---|---|---|
| `bird_info` | 数据状态与作答进度 | `bird.py info` |
| `bird_list` | 按难度/数据库筛题，拿到 `idx` | `bird.py list` |
| `bird_question` | 题干 + evidence（**不含** gold SQL） | `bird.py question` |
| `bird_schema` | 表概览 / 单表详情 / 字段描述 | `bird.py tables` / `schema` / `desc` |
| `bird_query` | 只读试跑 SQL | `bird.py run` |
| `bird_answer` | 提交某题（失败会拒绝记录） | `bird.py answer` |
| `bird_score` | 按官方 EX 口径打分 + 错因 | `bird.py score` |

---

## 4. 评测：两套口径，互相验证

### `bird.py score`（默认，零依赖）

在 `tools/bird.py` 里重实现了官方判定：**`set(预测行) == set(金标行)`**，
与 `evaluation_utils.execute_sql` + `calculate_ex` 完全一致。
输出总分、分难度、分数据库的 EX，以及每道错题的失败原因
（SQL 执行报错 / 结果集不同 / 行数差异）。

### `tools/official_eval/run_ex.py`（官方脚本）

直接跑 BIRD 官方仓库的 `evaluation_ex.py`：

```bash
pip install func-timeout
python tools/official_eval/run_ex.py
```

两个本地补丁，都在代码里标注了 `[本地补丁]`：

- `evaluation_utils.py` 原本在顶部**无条件** `import psycopg2, pymysql`，
  导致只跑 SQLite 也必须装两个数据库驱动（Python 3.14 上 `psycopg2-binary` 还没有 wheel）。
  改成在真正需要对应方言时才 import，行为不变。
- 原 `run_evaluation.sh` 写死了相对路径和 `python3`，Windows + Git Bash 下不能直接用，
  所以有了 `run_ex.py` 包装（它顺带保证 `.jsonl` 存在）。

---

## 5. 数据来源与版本

- 数据集：`https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip`
  （Mini-Dev **V1，500 题**，包的 Last-Modified 是 2024-06-20）
- 题目构成：500 题 / 11 个数据库 / simple 148、moderate 250、challenging 102
- 官方脚本来源：`https://github.com/bird-bench/mini_dev` 的 `evaluation/`

> 补充说明：`mini_dev` 仓库 README 指出 HuggingFace 上的 `birdsql/bird_mini_dev`
> 才是 canonical 版本（现已更新到 Mini-Dev V2，780 题，含 CRUD 与 JSON 操作）。
> 本项目用 OSS 包是为了让整个流程可一键复现。若改用 V2，
> 需要同步调整 `tools/setup_data.py` 里的路径与题量常量。

## 6. 协议

BIRD 数据集遵循 **CC BY-SA 4.0**（见其官网 Notes），
`tools/official_eval/` 下的脚本版权归 BIRD 团队所有，此处仅作评测复现用途。
