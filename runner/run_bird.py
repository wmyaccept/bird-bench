# -*- coding: utf-8 -*-
"""BIRD 评测 runner：在**任何机器上**把 test 集跑成官方要的预测文件。

官方要求（Submission Guidelines）：
  * "The Exp Team will run the codebase" → 交的是代码，不是预测文件
  * "make sure your code is successful on your dev evaluation" → 得真跑得起来

用法：
    export BIRD_API_KEY=...            # 或用 --api-key
    python runner/run_bird.py \
        --test-dir  <包含 <db_id>/<db_id>.sqlite 的目录> \
        --questions <test.json> \
        --out       pred_test.json \
        --log       run_test.jsonl \
        [--limit 50] [--max-retries 2] [--resume] [--mock mock.jsonl]

只读保证：`tools/bird.py` 的 guard_sql（单语句 + SELECT/WITH 白名单）+ 只读 URI 连接，
与 agent 用的是同一份闸门代码 —— 这里不另写一份，免得两处漂移。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import bird as birdmod                      # noqa: E402  （复用 guard_sql / 只读连接 / 原子写）
from runner import prompt as promptmod                 # noqa: E402
from runner.llm import LLMClient, LLMError             # noqa: E402

SEP = "\t----- bird -----\t"


def default_prompt_dir() -> Path:
    """包里的 `prompt/`（打包时生成）优先；仓库里跑就回退到 skill 的 references（唯一真源）。

    为什么要有回退：仓库里**没有** `prompt/` 这个目录（它是 make_submission 打包时才生成的），
    而开发时最该读的就是 `.pi/skills/bird-sql/references/` —— 改完规则立即生效，不用先打包。
    """
    for cand in (ROOT / "prompt", ROOT / ".pi" / "skills" / "bird-sql" / "references"):
        if (cand / "traps.md").exists():
            return cand
    return ROOT / "prompt"


DEFAULT_PROMPT_DIR = default_prompt_dir()


# ------------------------------------------------------------------ 数据层

def load_questions(path: Path) -> list[dict]:
    """读题目。**只取 question / evidence / db_id**——`SQL` 字段即使是空的也不碰。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("questions") or data.get("data") or []
    out = []
    for i, q in enumerate(data):
        out.append({
            "idx": i,
            "db_id": q.get("db_id") or q.get("db") or "",
            "question": q.get("question") or q.get("question_text") or "",
            "evidence": q.get("evidence") or "",
        })
    return out


def find_db(test_dir: Path, db_id: str) -> Path:
    for cand in (test_dir / db_id / f"{db_id}.sqlite",
                 test_dir / f"{db_id}.sqlite",
                 test_dir / db_id / f"{db_id}.db"):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"在 {test_dir} 下找不到库 {db_id}（期望 {db_id}/{db_id}.sqlite）")


def run_readonly(db_path: Path, sql: str, timeout: float = 30.0):
    """跑一条只读 SQL，返回 (列名, 行数)。抛异常表示这条 SQL 不可用。"""
    sql = birdmod.guard_sql(sql)                       # 单语句 + 只读白名单（违规抛 SystemExit）
    con = birdmod.connect_readonly(db_path, timeout=timeout)
    try:
        cur = con.execute(sql)
        if cur.description is None:
            return [], 0
        rows = cur.fetchall()
        return [d[0] for d in cur.description], len(rows)
    finally:
        con.close()


class MockResponses:
    """离线自测：mock.jsonl 每行 {"idx": 0, "responses": ["第一条回复", "重写后的回复"]}。"""

    def __init__(self, path: Path):
        self.by_idx: dict[int, list[str]] = {}
        self.used: dict[int, int] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                self.by_idx[int(rec["idx"])] = list(rec.get("responses") or [])

    def take(self, idx: int) -> str:
        n = self.used.get(idx, 0)
        self.used[idx] = n + 1
        pool = self.by_idx.get(idx) or []
        if not pool:
            return "```sql\nSELECT 1\n```"
        return pool[min(n, len(pool) - 1)]


# ------------------------------------------------------------------ 主流程

def answer_one(q: dict, db_path: Path, client: LLMClient, system: str, column_meaning,
               max_retries: int, samples: int, timeout: float, max_tokens: int,
               verbose: bool) -> dict:
    schema = promptmod.schema_block(db_path, samples=samples)
    descs = promptmod.descriptions_block(q["db_id"], db_path, column_meaning)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": promptmod.build_user(
            q["question"], q["evidence"], q["db_id"], schema, descs)},
    ]

    t0 = time.time()
    sql, exec_ok, n_rows, error, attempts = "", False, None, "", 0
    errors: list[str] = []                             # 每一次尝试的错误（供日志/复盘）
    tok_in = tok_out = 0

    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            text, usage = client.chat(messages, max_tokens=max_tokens)
        except LLMError as e:
            error = f"llm: {e}"
            errors.append(error)
            break
        tok_in += usage.get("prompt_tokens", 0)
        tok_out += usage.get("completion_tokens", 0)
        sql = promptmod.extract_sql(text)

        if not sql:
            feedback = "You did not return any SQL. Reply with a single ```sql fenced query."
        else:
            try:
                cols, n_rows = run_readonly(db_path, sql, timeout=timeout)
            except SystemExit:
                feedback = ("Your statement was rejected by the read-only guard: exactly one "
                            "SELECT/WITH statement is allowed.")
                error = "guard"
                errors.append(error)
            except sqlite3.Error as e:
                feedback = f"SQLite refused your query: {e}. Fix the schema/column names and rewrite."
                error = f"sqlite: {e}"
                errors.append(error)
            except Exception as e:                       # 超时等
                feedback = f"Execution failed ({type(e).__name__}: {e}). Simplify and rewrite."
                error = f"{type(e).__name__}: {e}"
                errors.append(error)
            else:
                error = ""
                if n_rows == 0 and attempt < max_retries:
                    feedback = ("Your query executed but returned 0 rows. That is almost always a "
                                "wrong filter/join or a wrong value spelling (check the sample "
                                "values and the evidence). Rewrite it.")
                else:
                    exec_ok = True
                    break

        if verbose:
            print(f"    [try {attempts}] {feedback[:110]}")
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": feedback})

    return {
        "sql": sql, "exec_ok": exec_ok, "n_rows": n_rows, "error": error,
        "errors": errors, "attempts": attempts, "latency_s": round(time.time() - t0, 1),
        "prompt_tokens": tok_in, "completion_tokens": tok_out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="BIRD runner：test 集 → 官方预测文件")
    ap.add_argument("--test-dir", required=True, help="含 <db_id>/<db_id>.sqlite 的目录")
    ap.add_argument("--questions", required=True, help="test.json（SQL 字段为空）")
    ap.add_argument("--out", required=True, help="输出预测文件（官方格式的 JSON）")
    ap.add_argument("--log", default="run_test.jsonl", help="逐题 JSONL 日志")
    ap.add_argument("--prompt-dir", default=str(DEFAULT_PROMPT_DIR), help="规则/档案目录")
    ap.add_argument("--column-meaning", default=None, help="官方 column_meaning.json（可选）")
    ap.add_argument("--api-key", default=None, help="默认取 BIRD_API_KEY")
    ap.add_argument("--base-url", default=None, help="默认取 BIRD_BASE_URL")
    ap.add_argument("--model", default=None, help="默认取 BIRD_MODEL")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--thinking", choices=["disabled", "enabled", "default"], default="disabled",
                    help="DeepSeek 思考模式：disabled=直出 SQL（默认，与 dev 成绩口径一致）/ enabled / default（服务端默认）")
    ap.add_argument("--max-retries", type=int, default=2, help="执行失败/空结果时回喂重写的次数")
    ap.add_argument("--samples", type=int, default=3, help="schema 里每列给几个样例值")
    ap.add_argument("--timeout", type=float, default=60.0, help="单条 SQL 的执行超时")
    ap.add_argument("--limit", type=int, default=0, help="只做前 N 题")
    ap.add_argument("--only-idx", default=None, help="只做这些 idx，逗号分隔")
    ap.add_argument("--no-resume", action="store_true", help="忽略已答，全部重跑")
    ap.add_argument("--mock", default=None, help="离线自测的假响应 jsonl（不联网、不花额度）")
    ap.add_argument("--dump-prompt", type=int, default=None, help="打印第 N 题的完整 prompt 后退出")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    test_dir = Path(args.test_dir).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    log_path = Path(args.log).expanduser().resolve()
    prompt_dir = Path(args.prompt_dir).expanduser().resolve()

    # 失败关闭：路径/文件不对就立刻 rc=2，不要"跑了但什么都没做"
    for label, p in (("test-dir", test_dir), ("questions", Path(args.questions)),
                     ("prompt-dir", prompt_dir)):
        if not p.exists():
            print(f"ERROR: {label} 不存在：{p}", file=sys.stderr)
            return 2

    questions = load_questions(args.questions)
    if args.only_idx:
        want = {int(x) for x in args.only_idx.replace(" ", "").split(",") if x}
        questions = [q for q in questions if q["idx"] in want]
    if args.limit:
        questions = questions[:args.limit]
    if not questions:
        print("ERROR: 没有题目可跑", file=sys.stderr)
        return 2

    column_meaning = promptmod.load_column_meaning(args.column_meaning)

    # --dump-prompt 不需要 key（不联网、不花钱）：官方可以直接看我们到底发了什么 prompt
    if args.dump_prompt is not None:
        q = next((x for x in questions if x["idx"] == args.dump_prompt), questions[0])
        db = find_db(test_dir, q["db_id"])
        system = promptmod.build_system(prompt_dir, q["db_id"])
        user = promptmod.build_user(q["question"], q["evidence"], q["db_id"],
                                    promptmod.schema_block(db, samples=args.samples),
                                    promptmod.descriptions_block(q["db_id"], db, column_meaning))
        print(f"prompt_dir = {prompt_dir}")
        print(f"\n===== system ({len(system)} chars) =====\n{system[:1500]}\n...\n")
        print(f"===== user ({len(user)} chars) =====\n{user}")
        return 0

    mock = MockResponses(args.mock) if args.mock else None
    try:
        client = LLMClient(model=args.model, api_key=args.api_key, base_url=args.base_url,
                           temperature=args.temperature, timeout=args.timeout,
                           thinking=args.thinking,
                           mock=(lambda msgs: mock.take(-1)) if mock else None,
                           verbose=args.verbose)
    except LLMError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    # mock 模式下 responder 需要知道当前 idx：主循环里逐题重建（见下面 client.mock = ...）
    done: dict[str, str] = {}
    if out_path.exists() and not args.no_resume:
        try:
            done = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            done = {}
    todo = [q for q in questions if not done.get(str(q["idx"]))]

    print(f"runner: {len(questions)} 题 / 已答 {len(questions) - len(todo)} / 待跑 {len(todo)}")
    print(f"  model={client.model} base_url={client.base_url} prompt_dir={prompt_dir}")
    print(f"  thinking={client.thinking}（DeepSeek 的 flash 默认开思考，长题会拖到十几分钟）")
    if mock:
        print("  ⚠️ mock 模式：不联网、不花额度，只验证流程（结果不可用于报分）")

    if args.dump_prompt is not None:
        pass

    system_cache: dict[str, str] = {}
    tok_in = tok_out = 0
    empty = errors = 0
    t0 = time.time()
    log_fh = log_path.open("a", encoding="utf-8")

    for n, q in enumerate(todo, 1):
        try:
            db_path = find_db(test_dir, q["db_id"])
        except FileNotFoundError as e:
            print(f"  [{n}/{len(todo)}] idx {q['idx']} 跳过：{e}")
            continue
        system = system_cache.setdefault(q["db_id"], promptmod.build_system(prompt_dir, q["db_id"]))
        if mock:                                   # mock 的 responder 绑定当前 idx
            client.mock = (lambda msgs, i=q["idx"]: mock.take(i))
        res = answer_one(q, db_path, client, system, column_meaning, args.max_retries,
                         args.samples, args.timeout, args.max_tokens, args.verbose)
        tok_in += res["prompt_tokens"]
        tok_out += res["completion_tokens"]

        if res["sql"]:
            done[str(q["idx"])] = res["sql"] + SEP + q["db_id"]
            birdmod.write_json_atomic(out_path, done)      # 每题落盘 → Ctrl+C 也能续跑
        if res["exec_ok"]:
            if res["n_rows"] == 0:
                empty += 1
        else:
            errors += 1

        rec = {"idx": q["idx"], "db_id": q["db_id"], **res, "question": q["question"][:200]}
        log_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log_fh.flush()

        flag = "ok" if res["exec_ok"] else "FAIL"
        print(f"  [{n}/{len(todo)}] idx {q['idx']:<5} {q['db_id']:<22} {flag:<4} "
              f"rows={res['n_rows']} tries={res['attempts']} {res['latency_s']}s "
              f"{('' if res['exec_ok'] else res['error'][:60])}")

    log_fh.close()
    elapsed = time.time() - t0
    answered = len(done)
    print(f"\n──── 汇总 ────")
    print(f"  预测文件：{out_path}  共 {answered} 条")
    print(f"  本轮执行失败 {errors} / 空结果 {empty} / 合计 {len(todo)} 题")
    if todo:
        rate = (errors + empty) / len(todo) * 100
        print(f"  异常率 {rate:.1f}%（官方阈值 5%：NULL/空输出或运行错误超了会被打回）"
              f"{'  ⚠️ 超标' if rate > 5 else ''}")
    print(f"  tokens：prompt {tok_in:,} / completion {tok_out:,}（官方要提前报 prompt token 数）")
    print(f"  用时 {elapsed / 60:.1f} 分钟；日志 {log_path}")
    if answered == 0:
        print("ERROR: 一条都没写成（库路径不对？）", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
