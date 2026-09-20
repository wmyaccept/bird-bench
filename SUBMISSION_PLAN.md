# BIRD 排行榜提交方案

> **状态：打包器已落地（2026-09-20），唯一硬缺口是 `runner/`。**
> 本文档 §0–§7 是决策分析（仍是有效的），**§8 是现在真正要执行的步骤**。
>
> - 本文档记录日期：**2026-09-14**（§8 增补于 2026-09-20）
> - 官方 Submission Guidelines 抓取日期：**2026-09-14**（原文全文见文末附录 A）
> - 官方页面：https://bird-bench.github.io/ → 右下角 "Submission Guidelines" 按钮
>   指向 Google Docs：`1Rs6d_pcs2vfqW4Ymub7Wb1XtBNlrc-WfH3T7U1ktuBo`
> - 提交邮箱：**bird.bench23@gmail.com**（官方承诺 10 天内返回结果）
> - 榜单现状（2026-09-20 复核）：leaderboard 已有 **New Dev** 列 = `dev_20251106` 口径，
>   所以提交时报的 Dev 数字必须是 dev2025 全量，不是旧 dev。

---

## 0. 结论先行

**官方不是只收预测文件，而是会在他们自己的环境里真的把你的代码跑一遍。**

所以"依赖库怎么处理"这个问题，真正的风险点只有一个：

> 我们的 agent 跑在 **pi（Node.js / npm 包）** 上，而官方的评测环境是 **Python + CUDA 12.2/12.3 的 GPU 机器**，
> 他们不会（也不应该）给你装 Node.js 和一个陌生的 agent 框架。

⇒ **提交前必须把 agent 从 pi 里剥离出来，做成一个纯 Python runner**，
依赖收敛到 `pip install -r requirements.txt` + 一个 LLM API key 即可。

好消息：`tools/bird.py` 和 `tools/setup_data.py` **本身零第三方依赖**（纯标准库），
剥离工作量主要在"prompt 组装 + LLM 调用 + 循环"这一层，不涉及重写数据层。

---

## 1. 官方对依赖的硬要求（原文摘录）

| # | 官方原话 | 对我们的含义 |
|---|---|---|
| 1 | *"Provide a requirement.txt for your environment package up. **For special env, like java, jdk, please illustrate them in readme.** Our cuda version is 12.2 or 12.3."* | 必须交 `requirements.txt`；任何非常规运行时（**Node.js 就属于这一类**）必须在 README 里交代清楚 |
| 2 | *"**Please make sure your code is successful on your dev evaluation. (Required)**"*<br>*"Exp Team run & revision loop: The Exp Team will run the codebase and inspect logs"* | 代码会被真的执行；**dev 集上必须先自己跑通** |
| 3 | *"please **not include any private API package which can upload our database**"*<br>*"please make your submission files concise only containing related files about your work, **please remove irrelevant files**"* | 合规审查（有内部 SFT agent 扫代码）；提交包必须精简 |
| 4 | *"if **more than 5% of SQL outputs are abnormal (e.g., NULL/empty outputs)** and/or runtime errors occur, we will contact the team for fixes. During non-peak traffic, up to **3 revisions** are typically allowed."* | 空结果/报错率必须 < 5%，否则被打回；修订机会最多 3 次 |

另外两条与依赖间接相关的：

- *"Please ensure your code includes **logging or an error-handling mechanism**. By this way, after debugging, we can restart the evaluation from the example where errors occurred, rather than starting over."*
  → runner 必须**可断点续跑**，不能一崩就从第 1 题重来。
- 若代码必须从头重跑，官方**不负责 token 费用**。

---

## 2. 我们项目的依赖，分四层看

| 层 | 位置 | 实际依赖 | 官方环境能否满足 |
|---|---|---|---|
| **数据/工具层** | `tools/bird.py`、`tools/setup_data.py` | Python 3.9+ **纯标准库**（sqlite3 / json / urllib / zipfile …） | ✅ 直接跑 |
| **官方评测脚本** | `tools/official_eval/` | `func_timeout`（VES 还要 `numpy`；可选 `psycopg2`/`pymysql`） | ✅ `pip install` 即可 |
| **Agent 运行时** | `.pi/extensions/bird-sql/index.ts`、`.pi/skills/bird-sql/` | **pi（`@earendil-works/pi-coding-agent`，Node.js 包）+ Pi-Harness** | ❌ **不会给装** ← 唯一真正的坑 |
| **LLM** | 当前是 DeepSeek 等 API | `openai` 兼容的 API key | ⚠️ 需提供 key，并提前报 prompt token 数 |

**关键区分**：`.pi/extensions/*.ts` 只是"让 pi 能调 bird.py 的适配层"，
`bird.py` 的能力（只读连接、超时、schema、试跑、评分）本身与 pi 无关 —— 所以可以整套搬到 Python 里。

---

## 3. 两条路线

### 路线 A：照实交，在 README 里说明特殊环境

依赖官方那句 *"for special env … illustrate them in readme"*，在 README 里写清：
需要 Node 18+、`npm i -g @earendil-works/pi-coding-agent`、配置 API key、以什么参数启动 pi。

- ✅ 工作量最小，代码不用改
- ❌ **风险很高**：官方 Exp Team 面对的是一个陌生 agent 框架 + Node 环境，
  大概率直接打回、或排在队尾（他们明说 "Expected Time: 1-20 days, highly depend on your env"）

### 路线 B：收敛成纯 Python runner（**推荐**）

把"agent 要做的事"从 pi 里搬出来，写一个 `runner/run_bird.py`：

```
读 test.json（官方给，不含 gold SQL）
  → 拼 prompt（skill 的规则文本当 system prompt + schema + evidence）
  → 调 LLM API（openai 兼容）
  → 用 tools/bird.py 的只读连接自检/试跑
  → 失败则带错误信息重试
  → 按官方格式输出 pred 文件（SQL \t----- bird -----\t db_id）
```

- ✅ `requirements.txt` 只剩 `openai` + `func_timeout`
- ✅ README 只需三行命令：装依赖 → 填 key → 跑
- ✅ 不存在"特殊环境"要解释，合规审查也简单（一眼能看完）
- ✅ 顺带满足官方另外两条要求：dev 上跑通、有 logging 可断点续跑
- ❌ 需要一次性投入：写 runner（约 200–300 行）并把 prompt 从"对话式"改成"函数式"

---

## 4. 路线 B 实施步骤（照此执行）

### 4.1 要新增/修改的文件

| 动作 | 文件 | 说明 |
|---|---|---|
| 新增 | `runner/run_bird.py` | 主流程（唯一入口） |
| 新增 | `runner/prompt.py` | prompt 组装：读 `skill` 的规则文本 + schema + evidence |
| 新增 | `runner/llm.py` | LLM 调用封装（openai 兼容 + 重试 + token 统计） |
| 修改 | `tools/bird.py` | `DATASETS`（第 55 行）加一项 `test`，指向官方给的 test 目录 |
| 修改 | `requirements.txt` | 加 `openai>=1.30` |
| 修改 | `README.md` | 新增"打榜提交"章节：安装、配置、运行命令、输出格式 |

### 4.2 runner 的职责

**输入**（官方在提交时提供，见附录 A 的 "Test Set Input"）：

- `test_databases/`（同 dev 的库 + 若干巨型库）
- `test_tables.json`、`column_meaning.json`
- `test.json`：`{db_id, question, evidence, SQL: ""}`（**SQL 是空字符串**，绝不依赖 gold）

**输出**：官方格式预测文件，每行一条
`<SQL>\t----- bird -----\t<db_id>`

**循环（逐题）**：

1. 组装 prompt：system = skill 精简版规则；user = question + evidence + schema 摘要
2. 调 LLM → 抽 SQL
3. `guard_sql()` 白名单校验 → `run_sql()` 在只读连接（`mode=ro` + `PRAGMA query_only`）上试跑
4. 报错或返回空集 → 把错误/空结果反馈回模型，重试（上限 N 次，写进日志）
5. 落盘（复用 `save_answers()` 的**原子写 + 文件锁**）

**断点续跑**：已作答的 idx 直接跳过（复用 `load_answers()`）

**日志**：每题一行 JSONL —— `idx / db_id / 耗时 / token / 重试次数 / 错误类型`

**收尾自检**：统计空结果比例与报错率，**超过 5% 就在本地先修，别带着提交**

### 4.3 复用 `tools/bird.py` 的哪些函数

`bird.py` 已经把这些函数拆好了（都在模块级，可直接 `import`）：

```
load_questions()      读题目（不含 gold）
load_answers()        读已作答（断点续跑用）
db_path(db_id)        定位 sqlite 文件
connect_readonly()    只读连接（mode=ro + query_only）
guard_sql(sql)        SELECT/WITH/EXPLAIN 白名单
run_sql()             试跑并返回结果
save_answers()        原子写 + 文件锁
compare_ex()          本地 EX 对比（在 dev 上验收 runner 用）
```

> 建议直接 `import`（`sys.path` 加 `tools/`），不要用 `subprocess` 调 CLI ——
> 每题省一次进程启动，几千题差别很明显。

### 4.4 验收标准（提交前必须全过）

- [ ] 在 **dev 集的一个子集（如 50 题）** 上跑完整流程，本地 EX 与"人工在 pi 里做的"接近
- [ ] 空结果 + 报错率 **< 5%**
- [ ] 中途 `Ctrl+C` 后重跑，不会重复消耗已完成的题
- [ ] 全新环境（只 `pip install -r requirements.txt` + 填 key）能从零跑通
- [ ] 代码里**没有任何**会把数据发出去的第三方包/逻辑（合规）
- [ ] 提交 zip 里没有 `data/`、`work/score/pred_*.json` 等无关文件

---

## 5. 提交物清单（对照官方 "Submission Required Material"）

| 官方要求 | 我们对应的东西 | 当前状态 |
|---|---|---|
| `Readme.md`：含详细命令 | `README.md` | ⚠️ 现在写的是 pi 工作流，**要重写成 runner 用法** |
| Code Zip（精简） | 打包 `tools/` + `runner/` + skill 文本 | ⚠️ 待整理，必须剔除 `data/`（4 GB） |
| `requirement.txt` | `requirements.txt` | ⚠️ 待补 `openai` |
| Models or Keys | 走 **API key** 路线（无本地模型） | ⚠️ 需提供 key，评测结束后可重置 |
| Column meaning file usage | 需明确回答是否用 `column_meaning.json` | ⚠️ 待决定（我们用 `bird_schema` 的字段说明，功能等价） |
| **Dev SQL File**（dev 集预测 SQL，便于复现） | `work/answers_dev.json` | ✅ 已有，需转成官方 pred 格式 |
| 评测类型选择 | Type 3（API Call）或 Type 4（Combined） | ⚠️ 待决定；Type 4 需"分开 GPU 代码与闭源 LLM 代码" |
| prompt token 数预估 | — | ⚠️ 待统计（`runner` 的日志可以直接算出来） |

---

## 6. 风险 / 待决策

### 6.1 待决策

| # | 问题 | 备注 |
|---|---|---|
| 1 | **用旧 dev 还是新 dev split？** | 官方 2025-11-13 发布了 `birdsql/bird_sql_dev_20251106`（*"a cleaner development split"*），用它提交需在邮件里声明。我们目前跑的 1534 题是**旧 dev**，榜上 Dev 列的分数口径可能已经变化 |
| 2 | 评测类型选 Type 3 还是 Type 4 | Type 3（纯 API）最省事；Type 4 适合"工具型 LLM"，我们要把工具代码与 LLM 代码分开摆放 |
| 3 | 是否公开 dev 预测 SQL | 官方允许不公开，但要主动说明 |
| 4 | 报告哪个数字 | 必须用**全量口径** `正确数 / 总题数`，不能报"已答部分的准确率" |

### 6.2 已知风险

- **5% 异常输出阈值**：我们现在有些题的答案是空集（金标却非空），runner 阶段要专门防守
  （试跑得空 → 回喂给模型重写，而不是直接落盘）
- **提交频率限制**：*"we allow each team to provide up to 2 checkpoints per submission and 1-2 submission within a 2-month period"* —— 别浪费机会
- **匿名双盲**：SQL 预测会去掉身份信息后交给独立的 Eval Team；两个团队不通信
- **数据许可**：官方 2024-04-27 起将数据许可改为 **CC BY-SA 4.0**，仅限研究与正当用途
- **合规**：`tools/setup_data.py` 只做"从官方 URL 下载"，不含任何外发逻辑 —— 这一点要在 README 里写明，避免审查误会

---

## 7. 触发条件（什么时候开始执行本文档）

同时满足以下条件再动手：

- [ ] Dev 集（或新 split）已跑到一个自己满意的 EX，且**全量口径**的数字算得出来
- [ ] skill 稳定：不再频繁新增 `references/` 规则，套路基本定型
- [ ] 决定确实要上 Test 榜（而不是只用 Dev 成绩交作业）
- [ ] 有 2–3 天完整时间做 runner + 本地验收（官方返还还要 1–10 天）

---

## 8. 现在怎么执行（2026-09-20 落地）

### 8.1 已就位的部分

| 产物 | 路径 | 作用 |
|---|---|---|
| 打包器 | `tools/make_submission.py` | 按清单打 zip + 硬自检（禁 `data/`、密钥扫描、体积、README 命令、占位符、dev 预测体检、可选空结果率实测） |
| 官方面 README | `submission/README.md` | 英文，含安装/配置/运行/断点续跑/合规声明/Dev 成绩表 |
| 包内清单 | `submission/CHECKLIST.md` | 逐条对账官方 13 项要求（进 zip 叫 `SUBMISSION.md`） |
| 提交邮件 | `submission/EMAIL.md` | 英文邮件模板 + 发送前勾选 + 提交后时间线 |

打包命令：

```bash
"D:/python/python" tools/make_submission.py              # 检查 + 打包（rc=0 才能发）
"D:/python/python" tools/make_submission.py --dry-run    # 只检查
"D:/python/python" tools/make_submission.py --check-run  # 额外真跑 dev 预测，实测空结果率
```

退出码：`0` 可提交 / `2` 有硬失败（不许提交）/ `3` 有警告（能打包但不该提交，典型就是缺 `runner/`）。

### 8.2 唯一硬缺口：`runner/`

官方 *"The Exp Team will run the codebase"* + *"make sure your code is successful on your dev
evaluation (Required)"* ⇒ 交的不是预测文件，是**能在他们机器上跑出预测的代码**。
我们现在的"方法"活在 pi（Node 包）里，官方不会装。所以要写一个纯 Python runner，接口定为：

```bash
python runner/run_bird.py --test-dir <dir> --questions <test.json> \
       --out pred_test.json --log run_test.jsonl [--limit N] [--max-retries 3]
```

职责（全部复用 `tools/bird.py` 里已拆好的函数，不要重写数据层）：

1. 读题（`test.json` 的 `SQL` 字段是空串，**绝不碰任何 gold**）
2. 组装 prompt：system = `prompt/` 下的规则文本；user = question + evidence + schema 摘要 + 样例值
3. 调 OpenAI 兼容 API（`BIRD_API_KEY` / `BIRD_BASE_URL` / `BIRD_MODEL`），抽 SQL
4. `guard_sql()` 白名单 → `connect_readonly()` 试跑；**报错或空集回喂模型重写**（上限 N 次）
5. `save_answers()` 原子写 + 每题 flush；已答 idx 跳过（断点续跑）
6. 每题一行 JSONL 日志（idx/db_id/attempts/exec_ok/n_rows/latency/tokens/error）

验收（提交前必须全过）：dev 子集 50 题跑通、异常率 < 5%、Ctrl+C 后续跑不重做、
全新环境只 `pip install -r requirements.txt` 能跑、代码里无任何外发逻辑。

### 8.3 发信前必须拿到的两个数字

1. **dev2025 全量 EX**（`correct / 1534`，不是已答部分准确率）
2. **dev 上的 prompt token 总数**（官方对 Type 3/4 明确要求提前报，用来估成本）

两个数字都从 `runner` 的日志里直接算出来；EX 也可以先用
`python tools/bird.py --dataset dev2025 score` 单独算（慢，十几分钟量级）。

---

## 附录 A：官方 Submission Guidelines 全文
来源：https://docs.google.com/document/d/1Rs6d_pcs2vfqW4Ymub7Wb1XtBNlrc-WfH3T7U1ktuBo/
（抓取于 2026-09-14，经代理下载；以下为原文，未改动）

```
﻿BIRD-Test Submission Guidelines:


Thank you for your interest in our work. Please send your request along with the essential files or descriptions to bird.bench23@gmail.com. Currently, we support four types of evaluations:
To protect our data, each code submission will be examined seriously, please not include any private API package which can upload our database. Therefore, please make your submission files concise only containing related files about your work, please remove irrelevant files. This could lead to faster and smoother evaluation. Thanks!


Evaluation Workflow
To ensure fairness and data security, we operate with two separate teams: the Experiment Team and the Evaluation Team. The Exp Team is responsible for environment initialization and running submissions, while the Eval Team handles ground-truth SQL pools, test cases, and human assessment. The two teams do not communicate about submissions, and the SQL predictions sent to the Eval Team are anonymized to remove submitter-identifying information (best-effort double-blind).
1. Code compliance check: We use an internal SFT agent to review submissions for compliance; please do not include any third-party API links/packages or other mechanisms that could upload/leak our databases.

2. Exp Team run & revision loop: The Exp Team will run the codebase and inspect logs; if more than 5% of SQL outputs are abnormal (e.g., NULL/empty outputs) and/or runtime errors occur, we will contact the team for fixes. During non-peak traffic, up to 3 revisions are typically allowed.

3. Anonymous third-party evaluation: The generated SQLs will be anonymized and sent to the independent Eval Team on a separate instance; each task uses multiple GT SQL pools, test cases, and new test values to ensure faithful evaluation, with human review to handle edge cases and ensure accuracy.


1. Single A100 80G GPU Inference (0~34B, suitable for smaller models):
Expected Time: 1-10 days (highly depend on your env and instruction file)
    • Provide a detailed Readme file and compressed code. Please make sure your code is    
      successful on your dev evaluation.(Required)
     • Provide a requirement.txt for your environment package up. For special env, like java,  
      jdk, please illustrate them in readme. Our cuda version is 12.2 or 12.3.
    • Push your model to huggingface with appropriate privacy. You can refer to these docs: 
      doc1, doc2. (Highly Suggested)


2. Multi-GPU Parallel Evaluation (> 34B, suitable for open-source LLMs):
Expected Time: 10 days (highly depend on your env and instruction file)
    • Provide a clear Readme file and compressed code. Please make sure your code is 
      successful on your dev evaluation. (Required)
    • Provide a requirement.txt for your environment package up. For special env, like java,  
      jdk, please illustrate them in readme. Our cuda version is 12.2 or 12.3.
    • Push your model to huggingface with appropriate privacy. You can refer to these docs: 
      doc1, doc2. (Highly Suggested)
    • Specify resources required for model inference on your dev evaluation (e.g., 4 A100 80G 
      cards, 3 hours) for our appropriate resource allocation. (Required)


3. Evaluation via API Call (Suitable for closed-source LLMs):
Expected Time: 1-5 days
    • Provide a clear Readme file and compressed code. Please make sure your code is 
      successful on your dev evaluation. (Required)
    • Please provide your own keys if your LLMs need APIs out of the above (Required)
      keys. And you could reset the keys after the evaluation terminates (Required)
    • Inform us of the number of prompt tokens on your dev environment in advance for us to 
      estimate costs on testing. (Required)


4. Combined Models (Suitable for Tool-based LLMs or Closed / Open LLMs Mixed):
Expected Time: 10-20 days (highly depend on your env and instruction file)
    • Provide a clear Readme file and compressed code. Please make sure your code is 
      successful on your dev evaluation. (Required)
    • Please provide your own keys if your LLMs need APIs out of the above 
      keys. And you could reset the keys after the evaluation terminates(Required)
    • Inform us of the number of prompt tokens on your dev environment in advance for us to 
      estimate costs on testing. (Required)
    • Provide a requirement.txt for your environment package up. For special env, like java,  
      jdk, please illustrate them in readme. Our cuda version is 12.2 or 12.3.
    • Push your models to the modelscope please if your models are large and want us to 
      return results soon.
    • Also, it would be very helpful if you could separate between GPU-based codes and 
      Closed LLM codes.
    • Push your model to huggingface with appropriate privacy. You can refer to these docs: 
      doc1, doc2. (Highly Suggested)
    • Specify resources required for model inference on your dev evaluation (e.g., 4 A100 80G 
      cards, 3 hours) for our appropriate resource allocation. (Required)


Test Set Input:
test_databases: The same with dev databases, but with some giant databases.
test_tables.json: The same with dev_tables.json
column_meaning.json: New, the summarized database description files, the same with https://github.com/quge2023/TA-SQL/blob/master/outputs/column_meaning.json.
test.json: The same with dev.json, but doesn’t contain “SQL”


Submission Required Material:
Readme.md: Please include detailed submission instructions with relevant commands to save significant time.
Code Zip: Provide your code in a compressed zip file.
Models or Keys: Upload your models to Hugging Face or ModelScope (recommended). Or OpenAI or other API keys. 
Columeaning File Usage: Please also state whether you need `column_meaning.json` in testing.
Dev SQL File: To facilitate following and reproducing your results, please include your predicted SQLs on the development set. However, if you have any concerns of not open-sourcing your dev results, please also let us know.


Submission Frequency: 
Please note that we allow each team to provide up to 2 checkpoints per submission and 1-2 submission within a 2-month period. Also you can only choose at most 2 preferred results to update at each submission.




NOTE:
1. Kindly be aware that in real-world scenarios, the ground truth SQL queries are NOT observed. Therefore, please ensure that your method should not rely on these ground truth SQLs. Otherwise, this may lead to failure of your code. Each test case in test.json is structured as follows (it’s just an example not the exact data from test, and SQL is an EMPTY string):
{
        "db_id": “nba_data”,
        "question": "how many players in NBA?",
        "evidence": "’how many’ refers to COUNT()",
        "SQL": ""
    }


2.Please ensure your code includes logging or an error-handling mechanism. By this way, after debugging, we can restart the evaluation from the example where errors occurred, rather than starting over. This will save both time and money. Logging files will make us better communicate when bugs happen. 
(If your codes require starting over if bugs happen, we will not be responsible for token costs. Thanks for your understanding!)


Disclaimer: We will only use your code for evaluation purposes and will not disseminate or disclose any details of your code. After the evaluation is completed and confirmed with the model author, we will immediately delete the server instance, including your code and Docker.
```
