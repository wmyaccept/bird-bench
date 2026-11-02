# 交接文档（pi-harness → Codex）

- 写于：**2026-10-19**
- 项目根：`D:\school source\数据库学习`
- 远端：`https://github.com/wmyaccept/bird-bench.git`，分支 `main`，HEAD = `7201c35`（已推送）
- 用途：**给接手的 Codex 一份自包含的状态说明**。读完这一份，不需要回读任何聊天历史。

> ⚠️ `D:/tmp/bird/HANDOFF.md` 是 **2026-10-03 的旧快照**，其中 "N-version 期望收益是 0"、
> "下一步走 γ" 等结论已被后续实验修正（见 §4）。**以本文件为准**。

---

## 0. 三十秒速览

这个项目做的是 **BIRD-SQL Text-to-SQL**，两条线同时存在：

1. **解题 agent（pi 扩展 + skill）** —— 用于在本机 500/1534 道 dev 题上迭代方法论。
2. **提交 runner（纯 Python、零第三方依赖）** —— 把同一套方法论打到**隐藏 test 集**，提交官方排行榜。

**已经发生的事**：v1 已提交并上榜（官方 test **EX 69.59**，PR #241 待 merge）；
之后发现 v1 的 dev 分数里含 **11 份手写库档案**（dev 专属先验，隐藏 test 的 15 个库上不存在），
于是做了 v2（删档案 → 改成运行时侦察）；再用**配对消融**量化了两者各自的贡献；
随后跟进了 DeepEye-SQL 论文的 4 个方向（β/P0/P1.5/γ），结论都记在 `casebook.md`。

**现在的状态**：代码干净、回归全绿（**325 通过 / 0 失败**）、没有在跑的批处理、**等用户指令**。

---

## 1. 接手后先做这 5 件事（10 分钟）

```bash
cd "D:/school source/数据库学习"

# ① 确认代码与远端一致（应当输出同一个 hash）
git rev-parse HEAD origin/main

# ② 跑全量回归（唯一权威的"没退化"判据；零 API 成本）
PYTHONIOENCODING=utf-8 "D:/python/python" tools/tests/run_all.py
#   期望最后一行：════ 合计 通过 325 / 失败 0 ════

# ③ 确认数据集在位（data/ 被 gitignore，不进仓库；不存在就跑 tools/setup_data.py）
du -sh data/DEV data/MINIDEV

# ④ 确认 runner 能离线起（不花钱）：只打印 prompt，不联网
PYTHONIOENCODING=utf-8 "D:/python/python" runner/run_bird.py \
  --test-dir data/DEV/dev_databases \
  --questions data/DEV/dev_20251106.json \
  --out /dev/null --dump-prompt 0 | head -20

# ⑤ 读规则入口（Codex 不会自动加载，必须手动读）
#    .pi/skills/bird-sql/SKILL.md      ← 工作流 + 硬规则
#    .pi/skills/bird-sql/references/traps.md   ← 写 SQL 时按动作顺序过
```

**不要**一上手就跑批处理。任何**花钱**的动作都要先问用户（见 §7）。

---

## 2. ⭐ 从 pi 换到 Codex：哪些东西会消失

这是本次交接**最关键**的一节。项目里有一层是 **pi 专属**的，Codex 用不了：

| 东西 | 在 pi 下 | 在 Codex 下 | 怎么办 |
|---|---|---|---|
| `bird_*` 工具（`bird_question` / `bird_schema` / `bird_query` / `bird_answer` …） | 由 `.pi/extensions/bird-sql/index.ts` 提供 | **没有** | 改用 CLI：`python tools/bird.py <子命令>`（**同一套后端、同一套闸门**） |
| `SKILL.md` / `references/*.md` | pi 按 description 自动加载 | **不自动加载** | 手动 `read`；或把要点贴进任务描述 |
| `AGENTS.md` | pi 读 | **Codex 原生读 `AGENTS.md`** ✅ | 不用动，保持现状 |
| 会话 JSONL / 上下文压缩 | `C:\Users\30538\.pi\agent\sessions\...` | 无关 | 不用管 |
| 四道提交闸门 | 在扩展里调用后端 | **仍在 `tools/bird.py::cmd_answer` 里** ✅ | CLI 一样会被拦，不会因为换工具就绕过 |

**结论**：Codex 下**一切走 CLI**，功能不缺。工具名 → 命令的对应关系：

| pi 工具 | CLI 等价 |
|---|---|
| `bird_info` | `bird.py info` |
| `bird_list` | `bird.py list --difficulty … --db …` |
| `bird_question` | `bird.py question <idx>` |
| `bird_schema` | `bird.py tables <db>` / `schema <db> [table]` / `desc <db>` |
| `bird_find` | `bird.py find <db> "<概念词>"` |
| `bird_cols` | `bird.py cols <db> "<列名正则>"` |
| `bird_query` | `bird.py run <db> "<SQL>" --for <idx>` |
| `bird_answer` | `bird.py answer <idx> "<SQL>" --checks "…" --attrs "…"` |
| `bird_attrs` | `bird.py attrs <idx>` |
| `bird_score` | `bird.py score [--pred <file>]` |
| `bird_audit` | `bird.py audit` |
| `bird_brief` | `bird.py brief [--step N]` |

⭐ 两个容易忘的点：
- `--for <idx>` 是**探针留痕**，`answer` 的闸门 1 靠它。用 CLI 时**必须显式带**（pi 里是 `for_idx` 参数）。
- 数据集要显式指定：`--dataset dev2025`（**默认是 minidev**，别搞错）。

---

## 3. 项目地图

```
.pi/
  extensions/bird-sql/index.ts    pi 工具层（Codex 用不到，但改工具行为时仍要同步）
  skills/bird-sql/
    SKILL.md                      入口：硬规则 + 7 步工作流（≤14500 字节，回归强校验）
    references/
      traps.md                    ★ 写 SQL 时逐条过（SELECT/JOIN/WHERE值/聚合）
      checklist.md                ★ 提交前必勾（四道闸门的 checks 条目号来源）
      shapes.md                   题型骨架 A1–A10
      calibration.md              标定/泛化实测
      diagnosis.md / gold-style.md / scoring.md
      sqlite-and-data.md / naming-traps.md
      casebook.md                 ★ 复盘账本（append-only，第 59/60 轮在末尾）
      maintaining.md              改 skill 的原则（做题不用读）
runner/                           提交用 runner（**只用标准库**）
  run_bird.py                     主程序：批处理 / 续跑 / 重试 / 崩溃隔离
  prompt.py                       system+user prompt 构造、schema 渲染、运行时侦察、D&C 变体
  llm.py                          DeepSeek 客户端（重试、截断重试、thinking 开关）
  run_subset.py                   （可选）子集跑批辅助
tools/
  bird.py                         ★ 唯一直接操作 SQLite 的地方（15 个子命令 + 四道闸门）
  setup_data.py                   下载 / 选择性解压数据集
  make_submission.py              打官方 zip + 硬自检（纯英文、禁 data/、扫密钥、体积…）
  schema_audit.py                 γ 实验：authorizer 记录金标真实列（离线，零 API）
  official_eval/                  BIRD 官方评测脚本（只允许 `[本地补丁]` 标注的改动）
tools/tests/                      全量回归（check_* + extension_smoke.cjs + make_fixture.py）
work/                             答案、预测、日志、评分、实验产物（**已 tracked**）
submission/                       给官方的三份文档（README.md / CHECKLIST.md / EMAIL.md）
data/                             数据集（gitignore，约 4 GB，可再生）
PAPER_DEEPEYE_SQL.md              论文精读笔记（不进提交包）
SUBMISSION_PLAN.md                打榜方案 + 官方 guideline 全文 + 上榜单记录
HANDOFF.md                        本文件
```

---

## 4. 状态账本（**务必分清"已测量"与"外推"**）

### 4.1 官方 / 提交

| 项 | 值 |
|---|---|
| 已提交产物 | `work/submission/bird_submission_20260921.zip`（28 文件 / 0.20 MB，**含 11 份库档案**，**勿覆盖**） |
| 官方 test（v1） | **EX 69.59**（simple 76.61 / moderate 66.67 / challenging 51.93，1789 题） |
| 其他指标 | Soft F1 **70.81**、R-VES **67.73** |
| 排行榜 | PR **#241**（branch `add-wmyaccept-sql-leaderboard`，commit `c4dca74`），**仍待 merge** |
| 规则 | 官方回信原话：**"一个榜上同一种方法最多留两条"** ⇒ v2 可以作为**第二行**，不必覆盖 69.59 |
| PR 仓库 | clone 在 `D:/tmp/bird/site`（临时产物，**不在本仓库**） |

### 4.2 本地分数（口径必须写清楚）

| 口径 | EX | 说明 |
|---|---|---|
| runner v1（含库档案）× dev2025 | **72.43%**（1111/1534） | simple 79.07 / moderate 75.40 / challenging 42.42 |
| runner v2（运行时侦察，无档案）× dev2025 | **68.97%**（1058/1534） | 空结果 0.33%，prompt ≈30.6M |
| agent 产出 × dev2025 | **70.47%**（1081/1534） | ⚠️ pi + **grok-4.6**，**换过模型**，不可与 runner 直接比 |
| 官方 test（v1，等价"无档案"） | **69.59** | 隐藏 test 上档案值为 0（没有文件） |

### 4.3 配对消融（384 题 stride-4：209 simple / 118 moderate / 57 challenging）

| 臂 | 配置 | 正确 | EX |
|---|---|---|---|
| A | 通用 prompt，`--no-recon` | 265 | **69.01%** |
| B = v2 | 通用 + 运行时侦察 | 272 | **70.83%**（+1.82 vs A） |
| C = v1 | 通用 + 库档案 | 286 | **74.48%**（+5.47 vs A） |
| D | 通用 + 侦察 + D&C 生成（`--variant dnc`） | 263 | **68.49%** |

- **结论 1**：dev→test 的落差**全部来自库档案**（test 上没有档案文件）；**侦察是可迁移的 +1.82**。
- **结论 2**：D 单臂更弱，但 **B ∪ D = 286 = 74.48%**（D 独救 14 题，同时弄丢 23 题）⇒ **换"方法论"能产多样性，换"知识注入"不能**。
- **结论 3（P0/UB-EX）**：四臂并集 **307/384 = 79.95%**，比最强单臂高 **+5.47** ⇒ **候选池有空间，瓶颈在"选"**。
- ⚠️ 外推：test ≈ 69.59 + 1.82（侦察）≈ **71.4**。**这是外推，不是官方成绩**。

### 4.4 论文跟进（DeepEye-SQL, arXiv 2510.17586）

| 方向 | 做了什么 | 结论 |
|---|---|---|
| **α** 复现整条流水线 | 只做了勘察 | **阻塞**：值检索要 embedding 端点（Qwen3-Embedding-0.6B + Chroma），DeepSeek 不提供 |
| **β** D&C 生成 | 已实现 `--variant dnc` 并跑了 384 题 | 单臂 −2.34，但边际覆盖 +3.65 ⇒ 多样性真实存在 |
| **P0** 候选覆盖 | 免费离线 | 四臂并集 79.95% vs 单臂 74.48% |
| **P1.5** 离线选择器 | 免费离线 | **零净增益**（θ 全试过）。⚠️ 但全程 **T=0 单次采样**，论文的 `Conf` 机制（T=0.7 × 8 次）**根本没被启动** ⇒ 只能结论"这个朴素选择器在本设定下无净收益"，**不能**推广成"N-version 无用" |
| **γ** schema 剪枝审计 | 免费离线，`tools/schema_audit.py` | schema 只占总 prompt **≈12%**；砍样本最多省 **−7.8%**；漏列不可逆 ⇒ **决定不接入**、不为此花钱 |

详见 `casebook.md` **第 59 轮**（2026-10-13）与 **第 60 轮**（2026-10-19）。

---

## 5. 常用命令（全部实测过）

### 5.1 解题（dev 集）

```bash
B="D:/python/python"; export PYTHONIOENCODING=utf-8

# 读题（含 evidence，**不给 gold SQL**）
$B tools/bird.py --dataset dev2025 question 344

# 看库 / 表 / 字段说明
$B tools/bird.py --dataset dev2025 tables california_schools
$B tools/bird.py --dataset dev2025 schema california_schools schools
$B tools/bird.py --dataset dev2025 desc california_schools

# 概念反查（写 SQL 前必做；列名靠猜是本项目最大失分源）
$B tools/bird.py --dataset dev2025 find california_schools "locally funded"
$B tools/bird.py --dataset dev2025 cols california_schools "type|code"

# 只读试跑（--for 留探针痕迹）
$B tools/bird.py --dataset dev2025 run california_schools "SELECT DISTINCT ..." --for 344

# 列数先验（防"少给列"）
$B tools/bird.py --dataset dev2025 attrs 344

# 提交（四道闸门；缺一会被拒）
$B tools/bird.py --dataset dev2025 answer 344 \
  "/* shape: 1x2 */ SELECT ..." \
  --checks "0,1,1b,2,2b,4,5,8,10,12,13" \
  --attrs "the name|the count"

# 评分
$B tools/bird.py --dataset dev2025 score --list-wrong 10
$B tools/bird.py --dataset dev2025 score --pred work/runner_pred_dev2025_v2.json
```

### 5.2 runner（提交口径）

```bash
# 全量 dev2025（1534 题，约 3 小时，≈30M prompt tokens）
$B runner/run_bird.py \
  --test-dir data/DEV/dev_databases \
  --questions data/DEV/dev_20251106.json \
  --out work/runner_pred_dev2025_v2.json \
  --log work/runner_log_dev2025_v2.jsonl

# 384 题子集（stride-4，约 21 分钟）
$B runner/run_bird.py \
  --test-dir data/DEV/dev_databases \
  --questions data/DEV/dev_20251106.json \
  --out work/runner_pred_dnc.json \
  --log work/runner_log_dnc.jsonl \
  --only-idx "$(cat D:/tmp/bird/stride4.txt)" \
  --variant dnc

# 离线自测（不花钱）：打印完整 prompt
$B runner/run_bird.py --test-dir data/DEV/dev_databases \
  --questions data/DEV/dev_20251106.json --out /dev/null --dump-prompt 0
```

关键参数：`--variant {direct,dnc}`、`--no-recon`、`--thinking disabled`（默认，与 dev 成绩口径一致）、
`--temperature 0.0`、`--low-card-max 12`、`--recon-terms 8`、`--recon-budget 25`、
`--max-retries 2`、`--no-resume`、`--limit N`、`--only-idx "1,2,3"`、`--mock <jsonl>`。

### 5.3 打包 / 回归

```bash
$B tools/tests/run_all.py                              # 325 pass / 0 fail
$B tools/make_submission.py --out D:/tmp/bird/v2.zip    # 硬自检 + 打 zip
$B tools/make_submission.py --dry-run                   # 只检查不写
```

---

## 6. 硬约束（违反了会直接弄坏项目）

### 6.1 数据与答案

- **禁止**读 `data/MINIDEV/mini_dev_sqlite.json` / `mini_dev_sqlite_gold.sql` 抄答案；
  **禁止** `bird_question --reveal`。抄答案就失去做题的意义。
- **禁止**修改 `data/` 下任何内容（数据集只读）。
- **禁止**手写 `work/answers*.json`（格式是 `SQL<TAB>----- bird -----<TAB>db_id`，只能由 `bird.py answer` 写）。
- `work/answers.json`（minidev）、`answers_dev.json`（旧 dev）、`answers_dev2025.json`（新 dev）
  **三套互不相通**，idx 体系不同，别混。

### 6.2 提交包

- 进 zip 的 `submission/README.md` 与 `submission/CHECKLIST.md` 必须**纯英文**（含中文标点都算违规，
  回归里有 CJK 守卫）。`.pi/skills/**` 里的中文是**给模型读的规则**，允许，且已在 README §7 声明。
- `submission/EMAIL.local.md` 含**明文 API key**，已 gitignore。**不得读取打印、不得提交、不得外发**。
  同理 Desktop 上的 `BIRD_email_body.txt` / `bird_pr.md` 也可能含 key，用完应删。
- `work/submission/bird_submission_20260921.zip` 是**历史凭据**（官方收到的就是它），**不要覆盖**。

### 6.3 方法论（第 57 轮的类级不变式）

- **禁止恢复任何预写库知识**：`references/db/` 不许存在，`build_system()` 不许接受 `db_id`，
  `brief` 不许接受库参数，工具链不许往 `references/` 写。
  这不是洁癖：11 个 dev 库 ≠ 15 个隐藏 test 库，预写知识在 test 上**直接失效**（已被消融证实）。
- 复盘得到的新规则要**毕业**到 `traps.md` / `checklist.md` / `shapes.md` 之一，
  不能只留在 `casebook.md`。
- `casebook.md` 是 **append-only** 账本，不要改历史轮次（第 59 轮的那次措辞修正是用户明确批准的）。

### 6.4 工具链

- `runner/` **只允许标准库**（`requirements.txt`）。不要引入 `sqlglot` / `sqlparse` / `sklearn` 等。
- `tools/official_eval/` 是官方口径凭据，只允许带 `[本地补丁]` 标注的改动。
- `.pi/skills/bird-sql/SKILL.md` **≤14500 字节**（LF 归一后计数，回归强校验）。
- 改完任何东西**必须**跑 `tools/tests/run_all.py`。

---

## 7. 成本与授权（**这条最容易被违反**）

- **任何花钱的动作都必须先得到用户明确同意**。历史累计花费约 **$5–15**。
- 定价锚点（deepseek-flash，2026-10）：cache hit 输入 $0.003/M（off-peak）/ $0.006/M（peak）；
  cache miss 输入 $0.15 / $0.30；输出 $0.60 / $1.20。
- 实测：全量 1534 题 ≈ **30M prompt tokens**、≈ **3 小时**；384 题 ≈ **7.3M**、≈ **21 分钟**。
- 结论：**钱不是瓶颈，时间和上下文才是。**
- 用户明确说过 **"不要着急"** —— 系统是初稿不是冻结设计，给方案时要列选项 + 成本闸门。

---

## 8. 未决事项（等用户拍板，不要自作主张）

1. **要不要用 v2 重投官方 test？**
   - 预期 ≈71.4（外推，非实测），vs 已提交 69.59。
   - 官方允许**同一方法最多两条** ⇒ 可作为第二行，不必覆盖旧行；也可以更新同一 PR 分支。
   - 需要：活着的临时 API key、约 3 小时、约 $10。
2. **要不要做温度/多样性探针？**（唯一能证伪我们 P1.5 零结果的最小实验）
   - 先跑 **128 题 × 3 样本 @ T=0.7**（≈$0.3–1，20 分钟）看簇多样性是否出现；
   - 有 → 再跑 384 × 3 算真实多数投票；没有 → 写"本模型/本数据下 NVP 不值得"并停止。
   - **动手前先与用户预注册判定规则**。
3. **α（复现 DeepEye-SQL 全流程）仍被 embedding 端点阻塞**：
   - 可选：本地 CPU 跑 Qwen3-Embedding-0.6B / 用户提供 API / 用精确匹配侦察替代（不忠实）。
4. **PR #241 状态未知**（之前被 GitHub API 403 限流挡住）。恢复后要查；merge 后清理
   Desktop 上含 key 的临时文件，并吊销临时 key。

---

## 9. 已知坑（都踩过，别再踩）

| 坑 | 表现 | 正确做法 |
|---|---|---|
| **git 代理会来回变** | 有时代理通、直连不通，有时反过来 | 推之前先探：`curl -x http://127.0.0.1:7890 -m 6 -o /dev/null -w "%{http_code}" https://github.com`；200 就用 `-c http.proxy=http://127.0.0.1:7890`，否则用 `-c http.proxy=` |
| **管道吞退出码** | `cmd \| tail` 的 `$?` 是 tail 的 | 用 `out=$(cmd 2>&1); rc=$?` 再判断 |
| **Windows 编码** | `UnicodeEncodeError: 'gbk' codec` | 一律 `PYTHONIOENCODING=utf-8` |
| **Ctrl-Z / 后台缓冲** | `nohup` 的 `.log` 长时间空着 | **轮询 JSONL / 预测文件的条数**，不要看 log |
| **CRLF vs LF** | 同一文件在不同机器字节数不同 | 比较 **git blob sha**，不要比 `st_size`；SKILL 预算按 LF 归一计 |
| **HTTP 响应截断** | `http.client.IncompleteRead` 曾在第 886 题弄死整轮 | 已修：`llm.py` 把 `HTTPException` 纳入重试；`run_bird.py` 单题隔离 + 连续 5 次异常才非零退出 |
| **fixture 缺字段** | 新克隆跑回归必红 2 条 | 已修：`make_fixture.py` 现在会生成 `database_description/*.csv` |
| **idx ≠ question_id** | 新 dev 恰好全部 `question_id == idx`，但别依赖 | 一律用 `bird.py list` 拿到的 **idx** |
| **老/新 dev 不可比** | 新版 65 道旧 simple 被升级成多属性题 | 报分必须写清 `dev2025`；榜单上要带 `new-dev-badge` |

---

## 10. 建议的下一步（按性价比排序）

1. **零成本**：确认 PR #241 状态；读一遍 `casebook.md` 第 59/60 轮。
2. **零成本**：如果还想压缩 prompt，**别再动 schema**（上限只有 7.8%），
   去看 30,490 字符的**共享规则块**（`prompt.py::PREAMBLE`），但要另做对照。
3. **低成本（需授权）**：温度/多样性探针，先 128 题 × 3 样本。
4. **中成本（需授权）**：v2 重投官方 test（约 $10 / 3 小时）。
5. **不建议**：继续做 schema 剪枝；为了省 token 删规则；在 T=0 下再跑一遍选择器。

---

## 11. 一句话交接

**方法论已定型：库无关的通用 prompt + 运行时侦察；四道闸门保证不漏列、不瞎猜；
消融证明"库档案"是 dev 专属幻觉、侦察是可迁移增益、候选池有空间但廉价选择器兑现不了。
剩下的都是"要不要花钱把外推变成实测"的决策，不是技术问题。**
