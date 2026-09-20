# BIRD Test Set Submission — Agentic API-only Text-to-SQL

<!-- 状态：README 模板已就位；**runner 未落地**，命令以 runner 的 CLI 规格为准。
     打包器 tools/make_submission.py 会在缺 runner 时给出警告，并在 README 里留有
     未填占位符（<...>）时直接硬失败 —— 所以这份文件不可能被"忘了填"就发出去。 -->

## 1. What this is

An **API-only** agentic Text-to-SQL pipeline. There is **no GPU requirement and no special
environment**: the whole system is a Python entry point (`runner/run_bird.py`) plus an
OpenAI-compatible LLM call. The intelligence lives in a prompt (`prompt/`), the rest is
deterministic tooling:

| Layer | Files | What it does |
|---|---|---|
| Prompt (the method) | `prompt/*.md` | rules distilled from our dev-set error analysis, plus one short card per database |
| Runner | `runner/run_bird.py` | loop: build prompt → call LLM → validate → execute read-only → retry → log |
| Data layer | `tools/bird.py` | schema introspection, sample values, read-only execution, EX comparison |
| Local evaluator | `tools/official_eval/` | the official evaluation scripts (unmodified except a marked local patch) |

## 2. Environment

```bash
# Python 3.9+ (developed and tested on 3.14). No Java/JDK, no Node.js, no CUDA needed.
pip install -r requirements.txt
```

`tools/bird.py` uses only the Python standard library. The only third-party dependency is the
OpenAI client used by the runner.

## 3. Configuration

```bash
export BIRD_API_KEY="<your key>"          # key you provide for this evaluation
export BIRD_BASE_URL="<openai-compatible endpoint>"
export BIRD_MODEL="<model name>"
```

## 4. Running on the test set

```bash
python runner/run_bird.py \
    --test-dir  /path/to/test_databases_parent \
    --questions /path/to/test.json \
    --out       pred_test.json \
    --log       run_test.jsonl
```

Resume after a crash / interruption — the same command continues where it stopped
(already-answered indices are skipped, see `--resume`, on by default):

```bash
python runner/run_bird.py --test-dir ... --questions ... --out pred_test.json --log run_test.jsonl
```

Smoke test on a few questions before a full run:

```bash
python runner/run_bird.py --test-dir ... --questions ... --out pred_smoke.json --limit 5
```

## 5. Output format

A single JSON file, one entry per question, in the exact format consumed by the official
`evaluation_utils.package_sqls(..., mode="pred")`:

```json
{"0": "SELECT COUNT(*) FROM players\t----- bird -----\tnba_data", "1": "..."}
```

## 6. Logging and error handling

Required by the guidelines so that a failed run can be restarted instead of starting over:

- `--log run_test.jsonl`: one JSON object per question —
  `idx, db_id, attempts, sql, exec_ok, n_rows, latency_s, prompt_tokens, completion_tokens, error`
- every SQL is executed on a **read-only** connection (`file:...?mode=ro` + `PRAGMA query_only`)
  before being written out; execution errors and empty results are fed back to the model for a
  bounded number of retries (`--max-retries`, default 3)
- the output file is written atomically and flushed after every question, so an interruption never
  loses more than the question in flight

## 7. Compliance statement

- No third-party API, package, or link in this submission can upload or leak the databases.
  The **only** outbound network calls are to the LLM endpoint configured in §3.
- `tools/setup_data.py` only downloads datasets from the official BIRD URLs; it contains no
  upload logic of any kind.
- All database access is read-only.
- No ground-truth SQL is used anywhere at inference time: `test.json` carries an empty `SQL` field
  and the runner never reads any `*_gold.sql` / `dev.json` content.
- **Disclosure:** the prompt text in `prompt/` was distilled from our own error analysis on the
  public dev split (i.e. from *our wrong predictions* and the public dev questions/evidence), not
  from the test set. No dev gold SQL is embedded in the prompt: it contains prose rules and
  per-database notes (column meanings, join paths, value conventions), not example gold queries.
  If you prefer a prompt that does not use dev-derived notes at all, we can ship the same runner
  with `prompt/` reduced to the generic rules only (`SKILL.md`, `traps.md`, `checklist.md`).

## 8. `column_meaning.json`

**We do not need `column_meaning.json` for testing.** Column semantics are derived from the
databases themselves (declared types, distinct sample values, join-path probing) together with the
per-question `evidence` field. (If you prefer us to use it, it is a one-line prompt change.)

## 9. Dev results (reproducible)

| Item | Value |
|---|---|
| Dev split used | `bird_sql_dev_20251106` (the cleaner 2025-11-06 development split, 1534 questions) |
| EX (full-set, `correct / 1534`) | **<FILL: dev EX>** |
| Dev SQL file | `dev_pred/dev2025_pred.json` (1534 lines, official pred format) |
| Empty / error rate on dev | **<FILL: %>** (guideline threshold is 5%) |
| Prompt tokens on dev | **<FILL: total prompt tokens>** (total = prompt + completion: **<FILL>**) |

Reproduce locally (requires the dev databases, which are public):

```bash
python tools/bird.py --dataset dev2025 score --pred dev_pred/dev2025_pred.json
```

## 10. Evaluation type

**Type 3 — Evaluation via API Call** (closed-source LLM, no GPU). If a combined/type-4 evaluation
is preferred, the GPU-free part and the LLM-call part are already separated in this codebase.

## 11. Layout of this archive

```
README.md                  this file
SUBMISSION.md              what is inside the archive + requirement-by-requirement mapping
requirements.txt           dependencies (see §2)
runner/                    the runner (entry point: run_bird.py)
tools/                     data layer + the official evaluation scripts
prompt/                    the prompt text = our method (rules + per-database cards)
dev_pred/dev2025_pred.json our predicted SQL on the dev split
```
