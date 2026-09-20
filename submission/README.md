# BIRD Test Set Submission — Agentic API-only Text-to-SQL

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

`tools/bird.py` and `runner/` use only the Python standard library (the HTTP call is plain
`urllib.request`). The only third-party dependency in `requirements.txt` is `func-timeout`, and
that is needed **only** by the official evaluation script under `tools/official_eval/`, not by the
runner.

## 3. Configuration

```bash
export BIRD_API_KEY="<your key>"          # key you provide for this evaluation
export BIRD_BASE_URL="<openai-compatible endpoint>"
export BIRD_MODEL="<model name>"
```

Defaults if unset: `BIRD_BASE_URL=https://api.deepseek.com`, `BIRD_MODEL=deepseek-flash`. They can
also be passed as `--api-key/--base-url/--model`. The runner talks to `POST {base_url}/chat/completions`
with `Authorization: Bearer <key>` — i.e. any OpenAI-compatible endpoint works.

## 4. Running on the test set

```bash
python runner/run_bird.py \
    --test-dir  /path/to/test_databases_parent \
    --questions /path/to/test.json \
    --out       pred_test.json \
    --log       run_test.jsonl
```

`--test-dir` must contain `<db_id>/<db_id>.sqlite` per database. Optional flags:
`--column-meaning column_meaning.json` (see §8), `--max-retries N` (default 2),
`--samples N` (sample values per column, default 3), `--only-idx 1,2,3`, `--timeout SECONDS`.

Resume after a crash / interruption — the same command continues where it stopped
(already-answered indices are skipped; resume is on by default, `--no-resume` redoes everything):

```bash
python runner/run_bird.py --test-dir ... --questions ... --out pred_test.json --log run_test.jsonl
```

Smoke test on a few questions before a full run (also useful to eyeball the exact prompt we send,
without spending any API call):

```bash
python runner/run_bird.py --test-dir ... --questions ... --out pred_smoke.json --limit 5
python runner/run_bird.py --test-dir ... --questions ... --out x.json --dump-prompt 0
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
  `idx, db_id, attempts, sql, exec_ok, n_rows, latency_s, prompt_tokens, completion_tokens,
  error, errors` (`errors` is the per-attempt error list, `error` the last one)
- every SQL is executed on a **read-only** connection (`file:...?mode=ro` + `PRAGMA query_only`)
  **and** passes a single-statement/`SELECT|WITH` whitelist before execution; execution errors and
  empty results are fed back to the model for a bounded number of retries (`--max-retries`,
  default 2)
- the output file is written atomically and flushed after every question, so an interruption never
  loses more than the question in flight
- the runner exits with code 2 (not 0) if nothing could be written — a broken path can never look
  like a successful run

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
  with `prompt/` reduced to the two generic rule files only (`traps.md`, `shapes.md`).
  Note on what is **not** in the prompt: our internal agent workflow (tool names, submission gates)
  is deliberately excluded — the runner's system prompt contains SQL-writing rules and per-database
  notes only.

## 8. `column_meaning.json`

**Yes — we use it if you provide it.** The runner accepts `--column-meaning column_meaning.json` and
renders the human-annotated column meanings for the database of the current question. It falls back
to the per-table description files that ship with the public dev databases
(`<db>/database_description/*.csv`, the dev counterpart of `column_meaning.json`), which is what our
dev numbers were produced with. Without either source the runner still works (declared types +
distinct sample values + the per-question `evidence` field), but fidelity to our dev setting is best
when the descriptions are available.

## 9. Dev results (reproducible)

| Item | Value |
|---|---|
| Dev split used | `bird_sql_dev_20251106` (the cleaner 2025-11-06 development split, 1534 questions) |
| Model / mode | `deepseek-flash` via `https://api.deepseek.com`, thinking disabled (`--thinking disabled`) |
| EX (full-set, `correct / 1534`) | **72.43% (1111 / 1534)** |
| Dev SQL file | `dev_pred/dev2025_pred.json` (1534 entries, official pred format) |
| Empty / error rate on dev | **0.78%** (12 empty of 1534, 0 runtime errors; guideline threshold is 5%) |
| Prompt tokens on dev | **34,251,163** (total = prompt + completion: **34,373,488**) |
| Wall time on dev | ~43 minutes, single process, no GPU |

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
