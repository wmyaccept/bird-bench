# SUBMISSION.md — archive contents and requirement mapping

> This file is part of the archive. It lists what the archive contains and maps each official
> submission requirement to where it is satisfied. `README.md` has the commands to run.

## What is in this archive

```
README.md                    submission instructions with commands (required)
SUBMISSION.md                this file
requirements.txt             python dependencies
runner/                      the agentic runner (entry point: runner/run_bird.py)
tools/bird.py                schema / sampling / read-only execution / EX comparison (stdlib only)
tools/setup_data.py          official-URL downloader (no upload logic)
tools/official_eval/         the official evaluation scripts
prompt/                      exactly the files the runner reads: traps.md + shapes.md + db/<db_id>.md
dev_pred/dev2025_pred.json   our predicted SQL on the dev split (official pred format)
```

## Requirement-by-requirement mapping

| Official requirement | Where it is satisfied |
|---|---|
| *"detailed Readme file … relevant commands"* | `README.md` §2–§4 (install / configure / run / resume / smoke test) |
| *"compressed code"* | this archive |
| *"make sure your code is successful on your dev evaluation (Required)"* | `dev_pred/dev2025_pred.json` + `README.md` §9 (EX and empty-rate reported) |
| *"requirement.txt"* | `requirements.txt` |
| *"for special env, like java, jdk, please illustrate them in readme"* | none needed — pure Python, no GPU/Node/Java (README §2) |
| *"no private API package which can upload our database"* | only outbound calls go to the LLM endpoint; read-only DB access (README §7) |
| *"remove irrelevant files"* | no datasets, no `.sqlite`, no other splits' answers, no internal notes |
| *"logging or error-handling mechanism … restart from the example where errors occurred"* | `--log run_*.jsonl`, resumable by design (README §6) |
| *">5% abnormal (NULL/empty) outputs and/or runtime errors → we will contact the team"* | every SQL is executed read-only before being written; empty/error results are retried; dev empty-rate reported in README §9 |
| *"provide your own keys … you could reset the keys after the evaluation terminates"* | key is read from `BIRD_API_KEY` (README §3), never stored in the archive |
| *"inform us of the number of prompt tokens on your dev environment"* | README §9 |
| *"state whether you need column_meaning.json"* | not needed (README §8) |
| *"include your predicted SQLs on the development set"* | `dev_pred/dev2025_pred.json` |
| *"method should not rely on ground-truth SQLs"* | test input carries an empty `SQL` field; no gold file is read at inference (README §7) |

## Dev SQL file format

One JSON object, `idx → "<SQL>\t----- bird -----\t<db_id>"`, identical to what the official
`evaluation_utils.package_sqls(sql_path, ..., mode="pred")` expects. Keys are the 0-based question
indices in the same order as `test.json` / `dev.json`.

## Contact

`wmyaccept-SQL` (Independent Researcher) — 3053819143@qq.com
