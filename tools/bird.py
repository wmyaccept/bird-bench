#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BIRD Mini-Dev 解题后端 —— pi agent 与人类共用的一层命令行接口。

设计原则（也是这个 agent 和"随便让 LLM 生成 SQL"的区别）：

1. 防泄题：默认任何命令都不回传 gold SQL。只有 `score` 会读它。
2. 只读：所有 SQL 都在 `mode=ro` 的连接上执行，且语句白名单只允许
   SELECT / WITH / EXPLAIN，再加 `PRAGMA query_only` 和超时中断。
3. 输出截断：LLM 的上下文很贵，长结果只回传前 N 行 + 总行数。

数据目录结构由 tools/setup_data.py 生成，用 `--dataset` / `BIRD_DATASET` 切换：

  minidev（默认，500 题）
    data/MINIDEV/mini_dev_sqlite.json          # 题干 + evidence（含 gold SQL）
    data/MINIDEV/mini_dev_sqlite_gold.sql      # 金标，逐行 "SQL<TAB>db_id"
    data/MINIDEV/dev_databases/<db_id>/<db_id>.sqlite
    data/MINIDEV/dev_databases/<db_id>/database_description/*.csv

  dev（官方 Dev 集，1534 题；对齐排行榜 Dev 列）
    data/DEV/dev.json                          # 题干 + evidence（含 gold SQL）
    data/DEV/dev.sql                           # 金标，逐行 "SQL<TAB>db_id"
    data/DEV/dev_databases/<db_id>/<db_id>.sqlite

两个数据集共用一份作答记录 work/answers.json（idx 体系不同，所以**不要混用**）。
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- 路径与配置

ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


DATA_DIR = _env_path("BIRD_DATA_DIR", ROOT / "data")
WORK_DIR = _env_path("BIRD_WORK_DIR", ROOT / "work")

# 数据集登记表：加一个数据集就在这里加一行
DATASETS = {
    "minidev": {
        "name": "Mini-Dev 500 (SQLite)",
        "dir": "MINIDEV",
        "questions": "mini_dev_sqlite.json",
        "gold": "mini_dev_sqlite_gold.sql",
        "pred_stem": "pred_mini_dev_sqlite",
        "answers": "answers.json",  # 保留旧文件名，已作答的 172 题不能丢
    },
    "dev": {
        "name": "BIRD Dev 1534 (SQLite)",
        "dir": "DEV",
        "questions": "dev.json",
        "gold": "dev.sql",
        "pred_stem": "pred_dev",
        "answers": "answers_dev.json",
        "tied": "dev_tied_append.json",   # 42 道并列题的补充金标，命中任一即算对  # 与 minidev 分开存！idx 体系不同
    },
}


def _early_dataset_key() -> str:
    """在 argparse 之前定下数据集（路径是模块级变量）。"""
    argv = sys.argv[1:]
    key = None
    for i, arg in enumerate(argv):
        if arg == "--dataset" and i + 1 < len(argv):
            key = argv[i + 1]
        elif arg.startswith("--dataset="):
            key = arg.split("=", 1)[1]
    if key is None:
        key = os.environ.get("BIRD_DATASET")
    return (key or "minidev").strip().lower()


DATASET_KEY = _early_dataset_key() if _early_dataset_key() in DATASETS else "minidev"
DATASET = DATASETS[DATASET_KEY]
DATASET_NAME = DATASET["name"]

DS_DIR = DATA_DIR / DATASET["dir"]
DB_ROOT = DS_DIR / "dev_databases"
QUESTIONS_FILE = DS_DIR / DATASET["questions"]
GOLD_FILE = DS_DIR / DATASET["gold"]
PRED_FILE_NAME = DATASET["pred_stem"] + ".json"
ANSWERS_FILE = WORK_DIR / DATASET["answers"]
SCORE_DIR = WORK_DIR / "score"

READ_ONLY_RE = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE)
MAX_OUTPUT_CHARS = 12_000


# ---------------------------------------------------------------- 基础工具


def fail(message: str, code: int = 2):
    """统一的错误出口：把原因写给调用方（agent 也是调用方之一）。"""
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_questions() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        fail(
            f"找不到题目文件 {QUESTIONS_FILE}\n"
            f"先运行：python {ROOT / 'tools' / 'setup_data.py'}"
        )
    with QUESTIONS_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_gold() -> list[tuple[str, str]]:
    """返回 [(sql, db_id), ...]，顺序与 mini_dev_sqlite.json 一致。"""
    if not GOLD_FILE.exists():
        fail(f"找不到金标文件 {GOLD_FILE}")
    rows = []
    with GOLD_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            sql, _, db_id = line.rpartition("\t")
            rows.append((sql, db_id))
    return rows


def db_path(db_id: str) -> Path:
    path = DB_ROOT / db_id / f"{db_id}.sqlite"
    if not path.exists():
        available = sorted(p.name for p in DB_ROOT.iterdir()) if DB_ROOT.exists() else []
        fail(f"数据库 {db_id!r} 不存在。可用：{', '.join(available) or '(无，请先运行 setup_data.py)'}")
    return path


def connect_readonly(path: Path, timeout: float = 30.0):
    """只读连接 + 超时保护。URI 形式的 as_uri() 会自动转义路径里的空格。"""
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    deadline = time.monotonic() + timeout
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 20_000)
    return con


def guard_sql(sql: str) -> str:
    statements = [s for s in sql.split(";") if s.strip()]
    if len(statements) > 1:
        fail("只允许单条语句（检测到分号分隔的多条语句）")
    if not READ_ONLY_RE.match(sql):
        fail("只允许 SELECT / WITH / EXPLAIN 开头的只读查询")
    return sql.strip().rstrip(";").strip()


def run_sql(db_id: str, sql: str, max_rows: int = 50, timeout: float = 30.0):
    """执行只读 SQL，返回 (columns, rows, truncated, total_rows)。"""
    sql = guard_sql(sql)
    con = connect_readonly(db_path(db_id), timeout=timeout)
    try:
        cur = con.execute(sql)
        columns = [d[0] for d in (cur.description or [])]
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = [tuple(r) for r in rows[:max_rows]]
        if not truncated:
            total = len(rows)
        else:
            total = None  # 未知，除非再数一遍
        return columns, rows, truncated, total
    finally:
        con.close()


def fmt_rows(columns, rows, max_col: int = 40) -> str:
    def cell(value) -> str:
        text = "NULL" if value is None else str(value)
        text = text.replace("\n", "\\n")
        return text if len(text) <= max_col else text[: max_col - 1] + "…"

    header = [cell(c) for c in columns]
    body = [[cell(v) for v in row] for row in rows]
    widths = [max([len(header[i])] + [len(r[i]) for r in body]) if body else len(header[i]) for i in range(len(header))]
    lines = [" | ".join(h.ljust(w) for h, w in zip(header, widths))]
    lines.append("-+-".join("-" * w for w in widths))
    lines += [" | ".join(v.ljust(w) for v, w in zip(row, widths)) for row in body]
    return "\n".join(lines)


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [输出已截断，共 {len(text):,} 字符，仅显示前 {limit:,}]"


# ---------------------------------------------------------------- 子命令


def cmd_info(_args):
    print(f"数据集 : {DATASET_NAME}  [key={DATASET_KEY}]")
    print(f"数据目录: {DATA_DIR}")
    print(f"作答目录: {WORK_DIR}")
    ok = QUESTIONS_FILE.exists() and GOLD_FILE.exists() and DB_ROOT.exists()
    print(f"数据状态: {'就绪' if ok else '未就绪（先运行 tools/setup_data.py）'}")
    if not ok:
        ready = [k for k, v in DATASETS.items() if (DATA_DIR / v["dir"] / v["questions"]).exists()]
        print(f"已就绪的数据集: {', '.join(ready) if ready else '（无）'}")
        return
    questions = load_questions()
    dbs = sorted({q["db_id"] for q in questions})
    answers = load_answers()
    print(f"题目总数: {len(questions)}")
    print(f"数据库  : {len(dbs)} 个 -> {', '.join(dbs)}")
    print(f"已完成  : {len(answers)} 题")
    print()
    print("下一步：python tools/bird.py list --limit 10")


def cmd_list(args):
    questions = load_questions()
    rows = [
        (i, q)
        for i, q in enumerate(questions)
        if (not args.db or q["db_id"] == args.db)
        and (not args.difficulty or q.get("difficulty") == args.difficulty)
    ]
    total = len(rows)
    page = rows[args.offset : args.offset + args.limit]
    print(f"筛选后 {total} 题，显示第 {args.offset}–{args.offset + len(page) - 1} 条")
    print(f"{'idx':>5}  {'difficulty':<12} {'db_id':<24} question")
    for i, q in page:
        qtext = " ".join(str(q["question"]).split())
        print(f"{i:>5}  {q.get('difficulty', '?'):<12} {q['db_id']:<24} {qtext[:90]}")
    if args.offset + len(page) < total:
        print(f"\n继续：--offset {args.offset + len(page)}")


def cmd_question(args):
    questions = load_questions()
    if not 0 <= args.idx < len(questions):
        fail(f"idx 越界，合法范围 0–{len(questions) - 1}")
    q = dict(questions[args.idx])
    gold = q.pop("SQL", None)

    print(f"idx        : {args.idx}")
    print(f"question_id: {q.get('question_id')}")
    print(f"db_id      : {q['db_id']}")
    print(f"difficulty : {q.get('difficulty')}")
    print()
    print("question:")
    print(f"  {q['question']}")
    print()
    print("evidence (外部知识，必须结合使用):")
    print(f"  {q.get('evidence') or '(本题无 evidence)'}")
    print()
    print(f"库里没有 gold SQL。写好后用：python tools/bird.py answer {args.idx} \"<你的SQL>\"")
    if args.reveal and gold:
        print("\n--- gold SQL（--reveal 强制显示，仅用于事后复盘）---")
        print(f"  {gold}")


def cmd_schema(args):
    path = db_path(args.db_id)
    con = connect_readonly(path, timeout=args.timeout)
    try:
        objects = con.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table','view') AND substr(name, 1, 7) != 'sqlite_' ORDER BY name"
        ).fetchall()
        tables = [n for n, t in objects if t == "table"]
        views = [n for n, t in objects if t == "view"]
        print(f"数据库 {args.db_id}  ({path.stat().st_size / 1024 / 1024:.1f} MiB)")
        print(f"表 {len(tables)} 个，视图 {len(views)} 个")
        if views:
            print(f"视图: {', '.join(views)}")
        print()

        selected = [t for t in tables if not args.table or t == args.table]
        if args.table and not selected:
            fail(f"表 {args.table!r} 不存在。可用：{', '.join(tables)}")

        for name in selected:
            count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"### {name}  ({count:,} 行)")
            info = con.execute(f'PRAGMA table_info("{name}")').fetchall()
            print(f"{'column':<32} {'type':<12} {'pk':<3} samples")
            for _cid, col, ctype, notnull, _dflt, pk in info:
                samples = []
                if args.samples > 0 and not re.search(r"BLOB", ctype or "", re.I):
                    try:
                        got = con.execute(
                            f'SELECT DISTINCT "{col}" FROM "{name}" '
                            f'WHERE "{col}" IS NOT NULL LIMIT {args.samples}'
                        ).fetchall()
                        samples = [str(g[0]).replace("\n", " ")[:34] for g in got]
                    except sqlite3.Error:
                        samples = []
                mark = "PK" if pk else ("NN" if notnull else "")
                print(f"{col:<32} {(ctype or '?'):<12} {mark:<3} {', '.join(samples)}")
            print()
        print(f"字段含义（人工标注的 CSV，写 SQL 前必读）：")
        print(f"  python tools/bird.py desc {args.db_id}")
    finally:
        con.close()


def cmd_desc(args):
    base = db_path(args.db_id).parent / "database_description"
    if not base.exists():
        fail(f"没有找到 database_description 目录：{base}")
    files = sorted(base.glob("*.csv"))
    if args.table:
        files = [f for f in files if f.stem.lower() == args.table.lower()]
        if not files:
            fail(f"{args.db_id} 里没有描述 {args.table!r} 的 CSV")
    for path in files:
        print(f"### {path.stem}  ({path.name})")
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.reader(fh)
            for i, row in enumerate(reader):
                if i > 60:
                    print("  ... (CSV 较长，已截断)")
                    break
                print("  " + " | ".join(c.replace("\n", " ")[:60] for c in row))
        print()


def cmd_run(args):
    columns, rows, truncated, total = run_sql(
        args.db_id, args.sql, max_rows=args.max_rows, timeout=args.timeout
    )
    print(f"db_id: {args.db_id}")
    print(f"返回 {len(rows)}{'+' if truncated else ''} 行，{len(columns)} 列")
    print()
    print(fmt_rows(columns, rows) if columns else "(该语句无结果集)")
    if truncated:
        print(f"\n... 还有更多行，已按 --max-rows {args.max_rows} 截断")


def cmd_tables(args):
    """给 agent 一个便宜的第一步：只看表名和行数。"""
    path = db_path(args.db_id)
    con = connect_readonly(path)
    try:
        names = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND substr(name, 1, 7) != 'sqlite_' ORDER BY name"
            )
        ]
        print(f"{args.db_id}: {len(names)} 张表")
        for name in names:
            count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")')]
            print(f"  {name:<28} {count:>12,} 行  ({len(cols)} 列)")
    finally:
        con.close()


def load_tied_gold() -> dict[int, list[str]]:
    """并列题的补充金标：question_id -> [sql, ...]。只有 dev 数据集有。"""
    name = DATASET.get("tied")
    path = DS_DIR / name if name else None
    if not path or not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, list[str]] = {}
    for row in rows:
        out.setdefault(row["question_id"], []).append(row["SQL"])
    return out


def load_answers() -> dict:
    if not ANSWERS_FILE.exists():
        return {}
    text = ANSWERS_FILE.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 并行写入撞坏过的文件走这里。逐条抢救，不要直接把用户的工作丢掉。
        salvaged = salvage_answers(text)
        if not salvaged:
            fail(f"{ANSWERS_FILE} 已损坏且无法抢救，请备份后删除它重新作答")
        print(
            f"WARNING: {ANSWERS_FILE.name} 不是合法 JSON，已抢救出 {len(salvaged)} 条作答。",
            file=sys.stderr,
        )
        save_answers(salvaged)
        return salvaged


def salvage_answers(text: str) -> dict:
    """从被写坏的文件里尽量捞出 '"idx": "SQL..."' 形式的条目。"""
    pattern = re.compile(r'"(\d+)"\s*:\s*("(?:[^"\\]|\\.)*")')
    salvaged = {}
    for key, raw in pattern.findall(text):
        try:
            salvaged[key] = json.loads(raw)
        except json.JSONDecodeError:
            continue
    return salvaged


def write_json_atomic(path: Path, data) -> None:
    """原子写入：先写临时文件再 os.replace，避免并发时读到半个文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def save_answers(answers: dict):
    write_json_atomic(ANSWERS_FILE, answers)


@contextlib.contextmanager
def answers_lock(timeout: float = 60.0):
    """跨进程串行化「读 answers -> 改 -> 写回」。

    pi 会并发调用工具（一次 message 里发多个 bird_answer），如果没有这把锁，
    两个进程各自读到旧内容再各自写回，后写的会把先写的覆盖掉 —— 被撞成大文件的
    情况更糟，整个 answers.json 直接变成非法 JSON。这里用 O_EXCL 抢锁文件的方式，
    POSIX 和 Windows 都能用。
    """
    lock_path = ANSWERS_FILE.with_name(ANSWERS_FILE.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            # 持锁的进程崩了会留下陈旧锁文件，超过 30 秒就认为已失效
            try:
                if time.monotonic() - lock_path.stat().st_mtime > 30:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                fail(f"等待 {ANSWERS_FILE.name}.lock 超过 {timeout:.0f}s，可能有卡死的进程")
            time.sleep(0.05)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def cmd_answer(args):
    questions = load_questions()
    if not 0 <= args.idx < len(questions):
        fail(f"idx 越界，合法范围 0–{len(questions) - 1}")
    db_id = questions[args.idx]["db_id"]
    sql = guard_sql(args.sql)

    if not args.no_check:
        try:
            columns, rows, truncated, _ = run_sql(db_id, sql, max_rows=args.max_rows)
        except sqlite3.Error as exc:
            fail(f"SQL 在 {db_id} 上执行失败，未记录：{exc}")
        print(f"执行通过：{len(rows)}{'+' if truncated else ''} 行，{len(columns)} 列")
        print()
        print(fmt_rows(columns, rows))
        print()

    with answers_lock():
        answers = load_answers()
        answers[str(args.idx)] = f"{sql}\t----- bird -----\t{db_id}"
        save_answers(answers)
        total = len(answers)
    print(f"已记录第 {args.idx} 题（{db_id}），当前完成 {total} 题 -> {ANSWERS_FILE}")


def cmd_answers(args):
    answers = load_answers()
    if args.json:
        print(json.dumps(answers, indent=2, ensure_ascii=False))
        return
    questions = load_questions()
    print(f"已作答 {len(answers)} / {len(questions)} 题")
    for key, value in sorted(answers.items(), key=lambda kv: int(kv[0])):
        sql, _, db_id = value.partition("\t----- bird -----\t")
        sql = " ".join(sql.split())
        print(f"{key:>5}  {db_id:<24} {sql[:100]}")


def cmd_reset(args):
    if args.idx is None:
        if ANSWERS_FILE.exists():
            ANSWERS_FILE.unlink()
        print("已清空全部作答")
    else:
        answers = load_answers()
        if answers.pop(str(args.idx), None) is None:
            print(f"第 {args.idx} 题本来就没有作答")
        else:
            save_answers(answers)
            print(f"已删除第 {args.idx} 题的作答")


def cmd_score(args):
    """计算官方口径的 Execution Accuracy（结果集集合完全相同才算对）。"""
    questions = load_questions()
    gold = load_gold()
    if len(gold) != len(questions):
        fail(f"题目数 {len(questions)} 与金标行数 {len(gold)} 不一致，数据可能损坏")
    tied = load_tied_gold()
    if tied:
        print(f"注意：本数据集有 {len(tied)} 道并列题带补充金标，命中任一变体即算对")

    answers = load_answers()
    if not answers:
        fail("还没有任何作答，先用 answer 命令记录几题")

    results = []
    for idx_str, payload in sorted(answers.items(), key=lambda kv: int(kv[0])):
        idx = int(idx_str)
        if not 0 <= idx < len(questions):
            print(f"跳过越界的 idx {idx}")
            continue
        question = questions[idx]
        if args.db and question["db_id"] != args.db:
            continue
        if args.difficulty and question.get("difficulty") != args.difficulty:
            continue

        pred_sql = payload.split("\t----- bird -----\t")[0]
        gold_sql, db_id = gold[idx]
        path = db_path(db_id)
        outcome, detail = compare_ex(path, pred_sql, gold_sql, timeout=args.timeout)
        results.append(
            {
                "idx": idx,
                "db_id": db_id,
                "difficulty": question.get("difficulty", "unknown"),
                "correct": outcome,
                "detail": detail,
            }
        )

    if not results:
        fail("筛选后没有可评分的作答")

    n = len(results)
    correct = sum(r["correct"] for r in results)
    print("=" * 76)
    print(f"Execution Accuracy (EX) — {DATASET_NAME}")
    print("=" * 76)
    print(f"已作答   : {n} / {len(questions)} 题")
    print(f"正确     : {correct}")
    print(f"EX       : {correct / n * 100:.2f}%")
    print()

    print("按难度：")
    for level in ("simple", "moderate", "challenging"):
        subset = [r for r in results if r["difficulty"] == level]
        if subset:
            hit = sum(r["correct"] for r in subset)
            print(f"  {level:<12} {hit:>4} / {len(subset):<4} = {hit / len(subset) * 100:6.2f}%")

    print()
    print("按数据库：")
    for db_id in sorted({r["db_id"] for r in results}):
        subset = [r for r in results if r["db_id"] == db_id]
        hit = sum(r["correct"] for r in subset)
        print(f"  {db_id:<24} {hit:>4} / {len(subset):<4} = {hit / len(subset) * 100:6.2f}%")

    wrong = [r for r in results if not r["correct"]]
    if wrong and args.list_wrong:
        print()
        print(f"未通过的题（最多列 {args.list_wrong} 条，detail 是失败原因）：")
        for r in wrong[: args.list_wrong]:
            print(f"  idx {r['idx']:<5} {r['difficulty']:<12} {r['db_id']:<24} {r['detail']}")

    # 同时导出官方评测脚本需要的预测文件，方便老师复核。
    #
    # 注意两个必须遵守的约束，否则官方脚本会静默算错：
    #   1. `package_sqls(mode='pred')` 是按 **dict 的插入顺序** 取值的，而金标是按行读的，
    #      两边靠下标对齐 —— 所以这里必须按 idx 升序写出，不能直接用 answers 的原始顺序
    #      （那是作答先后顺序）。
    #   2. 条目数必须与题目数一致。只写已答的题会让预测列表比金标短，
    #      后面所有题都错位。未作答的题用占位 SQL 填上，并被计为错。
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    pred_file = SCORE_DIR / PRED_FILE_NAME
    ordered = {}
    for i, question in enumerate(questions):
        key = str(i)
        if key in answers:
            ordered[key] = answers[key]
        else:
            ordered[key] = f"SELECT 'UNANSWERED'\t----- bird -----\t{question['db_id']}"
    write_json_atomic(pred_file, ordered)

    unanswered = len(ordered) - len(answers)
    if unanswered:
        print()
        print(
            f"注：预测文件按 idx 升序写出了全部 {len(ordered)} 条，其中 {unanswered} 题未作答、"
            f"用占位 SQL 填充。"
        )
        print(
            f"    若要跑官方脚本，请按 {len(ordered)} 题口径看待结果（全量 EX = "
            f"{correct}/{len(ordered)} = {correct / len(ordered) * 100:.2f}%）；"
        )
        print(
            f"    上面 {correct / n * 100:.2f}% 是「已作答部分的准确率」，两个数不要混。\n"
        )

    report_file = SCORE_DIR / "score_report.json"
    write_json_atomic(
        report_file,
        {
            "dataset": DATASET_NAME,
            "dataset_key": DATASET_KEY,
            "answered": n,
            "unanswered": unanswered,
            "total_questions": len(questions),
            "correct": correct,
            "ex_percent": round(correct / n * 100, 2),
            "ex_percent_full_set": round(correct / len(ordered) * 100, 2),
            "results": results,
        },
    )
    print()
    print(f"官方格式预测文件 -> {pred_file}")
    print(f"逐题明细         -> {report_file}")


def compare_ex(path: Path, pred_sql: str, gold_sqls, timeout: float = 30.0):
    """与官方 evaluation_utils.execute_sql 相同的判定：set(pred) == set(gold)。

    `gold_sqls` 可以是单条 SQL，也可以是列表 —— Dev 集有 42 道**并列题**的补充金标
    （`dev_tied_append.json`），官方口径是命中任一条就算对。
    诊断信息用**主金标**（列表里的第一条）生成，以便和 Mini-Dev 的经验一致。
    """
    if isinstance(gold_sqls, str):
        gold_sqls = [gold_sqls]
    try:
        con = connect_readonly(path, timeout=timeout)
    except sqlite3.Error as exc:
        return False, f"无法连接数据库: {exc}"
    try:
        try:
            pred_rows = con.execute(pred_sql).fetchall()
        except Exception as exc:  # 语法错、超时、除零……
            return False, f"预测 SQL 执行失败: {type(exc).__name__}: {exc}"

        gold_rows = None
        for k, gold_sql in enumerate(gold_sqls):
            try:
                rows = con.execute(gold_sql).fetchall()
            except Exception as exc:
                if k == 0:
                    return False, f"金标 SQL 执行失败（题目本身可能有问题）: {exc}"
                continue
            if gold_rows is None:
                gold_rows = rows
            if set(pred_rows) == set(rows):
                return True, "ok" if k == 0 else f"ok（命中并列变体 #{k}）"

        # 诊断信息要说清楚是「行数不对」还是「列数不对」还是「值不对」。
        # 官方判定是 set(元组) 相等，元组是按位置比的 —— 所以列顺序和列数一样重要。
        pred_cols = len(pred_rows[0]) if pred_rows else 0
        gold_cols = len(gold_rows[0]) if gold_rows else 0
        shape = f"预测 {len(pred_rows)} 行 {pred_cols} 列 / 金标 {len(gold_rows)} 行 {gold_cols} 列"
        if len(gold_sqls) > 1:
            shape += f"（并列变体 {len(gold_sqls) - 1} 条均未命中）"
        if pred_cols != gold_cols:
            return False, f"列数不同（{shape}）"
        if len(pred_rows) != len(gold_rows):
            return False, f"行数不同（{shape}）"
        if {r[:1] for r in pred_rows} - {r[:1] for r in gold_rows}:
            return False, f"行数相同但取值不同（{shape}）"
        extra = set(pred_rows) - set(gold_rows)
        missing = set(gold_rows) - set(pred_rows)
        return False, (
            f"行数相同、首列也对得上，但整行元组不同（{shape}，"
            f"多出 {len(extra)} 组 / 少 {len(missing)} 组）—— 大概率是列顺序或多选了列"
        )
    finally:
        con.close()


# ---------------------------------------------------------------- 入口


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bird.py",
        description="BIRD 解题后端（只读、不回传 gold SQL；支持 minidev / dev 两个数据集）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "典型流程：\n"
            "  bird.py info\n"
            "  bird.py list --difficulty simple --limit 5\n"
            "  bird.py question 0            # 读题 + evidence\n"
            "  bird.py tables debit_card_specializing\n"
            "  bird.py schema debit_card_specializing --table customers\n"
            "  bird.py desc debit_card_specializing\n"
            "  bird.py run debit_card_specializing \"SELECT ... LIMIT 5\"\n"
            "  bird.py answer 0 \"SELECT ...\"\n"
            "  bird.py score\n"
        ),
    )
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASETS),
        help="数据集（默认 minidev；也可用环境变量 BIRD_DATASET）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="数据集状态与进度").set_defaults(func=cmd_info)

    p = sub.add_parser("list", help="列出题目（含 idx）")
    p.add_argument("--db", help="只列某个数据库")
    p.add_argument("--difficulty", choices=["simple", "moderate", "challenging"])
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("question", help="读第 idx 题（不回传 gold SQL）")
    p.add_argument("idx", type=int)
    p.add_argument("--reveal", action="store_true", help="复盘用：强制显示 gold SQL")
    p.set_defaults(func=cmd_question)

    p = sub.add_parser("tables", help="只列表名与行数（最便宜的第一步）")
    p.add_argument("db_id")
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("schema", help="表结构 + 行数 + 样例值")
    p.add_argument("db_id")
    p.add_argument("--table", help="只看某一张表")
    p.add_argument("--samples", type=int, default=3, help="每列显示几个去重样例值（0 关闭）")
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("desc", help="读人工标注的 database_description CSV")
    p.add_argument("db_id")
    p.add_argument("--table", help="只看某张表")
    p.set_defaults(func=cmd_desc)

    p = sub.add_parser("run", help="在指定库上试跑只读 SQL")
    p.add_argument("db_id")
    p.add_argument("sql")
    p.add_argument("--max-rows", type=int, default=50)
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("answer", help="记录第 idx 题的最终 SQL")
    p.add_argument("idx", type=int)
    p.add_argument("sql")
    p.add_argument("--no-check", action="store_true", help="跳过执行前检查")
    p.add_argument("--max-rows", type=int, default=20)
    p.set_defaults(func=cmd_answer)

    p = sub.add_parser("answers", help="查看已作答")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_answers)

    p = sub.add_parser("reset", help="删除作答（全部或某一题）")
    p.add_argument("--idx", type=int)
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("score", help="算官方口径的 EX")
    p.add_argument("--db")
    p.add_argument("--difficulty", choices=["simple", "moderate", "challenging"])
    p.add_argument("--list-wrong", type=int, default=10, help="列出前 N 道错题及原因")
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(func=cmd_score)

    return parser


def main():
    # Windows 控制台默认可能是 GBK，题目/字段描述里有非 ASCII 字符会炸
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
