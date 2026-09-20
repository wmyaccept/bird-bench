# 提交邮件模板（发给 bird.bench23@gmail.com）

> 官方原话：*"Please send your request along with the essential files or descriptions to
> bird.bench23@gmail.com."*
> 附件：① 代码 zip（`tools/make_submission.py` 产出）② dev 预测 SQL 文件（已在 zip 里，
> 也可单独附一份，方便他们不复现就核对）。
> 发送前把 `<...>` 全部填掉 —— 打包器会检查 README 里的占位符，但邮件里的要自己确认。
>
> ⚠️ **不要把真 key 写进这份文件**（它是 git 跟踪的）。发信时把本文件复制成
> `submission/EMAIL.local.md`（已 gitignore）再填 key，从那份底稿发。

---

**To:** bird.bench23@gmail.com
**Subject:** BIRD Test Set Submission — <团队/项目名> — Evaluation Type 3 (API Call)

Dear BIRD team,

We would like to submit to the BIRD test leaderboard. Our submission is an **API-only agentic
Text-to-SQL system** (no GPU required; closed-source LLM accessed via an OpenAI-compatible API).

**Evaluation type:** Type 3 — Evaluation via API Call.

**Attachments**
1. `bird_submission_<date>.zip` — code (concise: no datasets, no DB files, no unrelated files)
2. `dev2025_pred.json` — our predicted SQL on the development split (also included in the zip)

**Summary**
- Dev split used: `bird_sql_dev_20251106` (the 2025-11-06 development split), 1534 questions
- Dev EX (full set, correct / 1534): **72.43% (1111 / 1534)**
- Empty/error rate on dev: **0.78%** (12 empty, 0 runtime errors; below the 5% threshold)
- Prompt tokens on dev: **34,251,163** (prompt + completion: **34,373,488**)
- LLM call mode: non-thinking (`--thinking disabled`); one pass plus up to 2 rewrites when the SQL
  fails to execute or returns no rows
- `column_meaning.json`: **not needed** — we derive column semantics from the databases
  (types, distinct sample values, join probing) plus the per-question `evidence`
- Runtime: Python 3.9+, `pip install -r requirements.txt`; no Java/JDK/Node/CUDA
- Code has JSONL logging and resumes from the last unanswered question; every SQL is executed on a
  read-only connection before being written out

**API key** (please use for this evaluation only; we will reset it after the evaluation terminates)
- `BIRD_API_KEY`: `<FILL: temporary key>`
- `BIRD_BASE_URL`: `https://api.deepseek.com`
- `BIRD_MODEL`: `deepseek-flash`

Please let us know if anything in the archive is unclear or if you need a different format.

Best regards,
<FILL: name / affiliation>
<FILL: contact email>

---

## 发送前自检（逐条勾）

- [ ] `python tools/make_submission.py` 退出码 **0**（不是 3：3 = 有警告，多半是缺 runner）
- [ ] `submission/README.md` 里 `<FILL: ...>` 全部填完（打包器会硬拦，但要人工复核数字）
- [ ] dev EX 是**全量口径** `correct / 1534`，不是"已答部分准确率"
- [ ] 空结果率 < 5%（`--check-run` 实测过）
- [ ] key 是**临时**的、可撤销的；不要用主账号长期 key
- [ ] 确认 `<BIRD_BASE_URL>` 官方环境**能访问**（第三方聚合域名可能不通，见 `SUBMISSION_PLAN.md` §6）
- [ ] 附件里没有 `data/`、没有 `*.sqlite`、没有别的数据集的作答文件
- [ ] 记下提交日期与附件哈希（官方 2 个月内只允许 1–2 次提交、最多 3 次修订，机会要记账）

## 提交后

| 环节 | 官方承诺 | 我们的动作 |
|---|---|---|
| 合规审查（内部 SFT agent 扫代码） | — | 只等结果；有问题按官方反馈删包里的无关件 |
| Exp Team 跑代码 + 看日志 | 1–5 天（Type 3） | 准备好接"异常率 > 5%"的打回，按日志定位是哪几题 |
| 匿名第三方评测 | — | 结果回来后在 `references/casebook.md` 记一轮 |
