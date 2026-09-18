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
    # 2025-11-06 官方修订版：题目/evidence/金标都改过（question 变 11.9%、evidence 24.6%、SQL 29.4%），
    # 且难度重分类（simple 925→860）。数据库文件与 dev **共用**，idx 顺序也与 dev 完全一致。
    "dev2025": {
        "name": "BIRD Dev 2025-11-06 修订版（1534，SQLite）",
        "dir": "DEV",
        "questions": "dev_20251106.json",
        "gold": None,                   # 金标直接在题目 json 的 SQL 字段里
        "pred_stem": "pred_dev2025",
        "answers": "answers_dev2025.json",
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
GOLD_FILE = (DS_DIR / DATASET["gold"]) if DATASET.get("gold") else None
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
    """返回 [(sql, db_id), ...]，顺序与题目文件一致。"""
    if GOLD_FILE is None:  # 2025-11-06 版：金标就在题目 json 的 SQL 字段里
        return [(q["SQL"], q["db_id"]) for q in load_questions()]
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


def _strip_lead_comments(sql: str) -> str:
    """去掉开头的空白与注释（让我可以在 SQL 最前面写 `/* shape: 3x1 */` 形状声明）。"""
    s = sql.lstrip()
    while True:
        if s.startswith("/*"):
            end = s.find("*/", 2)
            if end < 0:
                break
            s = s[end + 2 :].lstrip()
        elif s.startswith("--"):
            nl = s.find("\n")
            if nl < 0:
                break
            s = s[nl + 1 :].lstrip()
        else:
            break
    return s


def guard_sql(sql: str) -> str:
    statements = [s for s in sql.split(";") if s.strip()]
    if len(statements) > 1:
        fail("只允许单条语句（检测到分号分隔的多条语句）")
    if not READ_ONLY_RE.match(_strip_lead_comments(sql)):
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


def _exact_rows(db_id: str, sql: str, fallback=None):
    """⭐ P13：把真实行数**数准**（包一层 COUNT(*)）。包不上就返回 fallback。

    用途：结果比一次取回的上限还大时，形状校验不能拿被截断的数字去比。
    """
    inner = sql.rstrip().rstrip(";").strip()
    wrapped = f"SELECT COUNT(*) FROM (\n{inner}\n) AS _shape_count"
    try:
        _cols, r, _tr, _n = run_sql(db_id, wrapped, max_rows=1)
    except (sqlite3.Error, SystemExit):
        return fallback
    if r and r[0] and r[0][0] is not None:
        return int(r[0][0])
    return fallback


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
    ok = QUESTIONS_FILE.exists() and (GOLD_FILE is None or GOLD_FILE.exists()) and DB_ROOT.exists()
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


def cmd_find(args):
    """概念词反查：题干里的一个词，究竟躺在哪张表哪一列里？

    用途：题干出现 “locally funded / high schools / option / Riverside” 这类概念词时，
    **不要用英文语感猜列名**，直接搜库内真值。用 EXISTS 短路，没命中的列只扫一遍、很快。
    """
    path = db_path(args.db_id)
    con = connect_readonly(path, timeout=args.timeout)
    try:
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND substr(name, 1, 7) != 'sqlite_' ORDER BY name"
            )
        ]
        pattern = f"%{args.word}%"
        print(f"db: {args.db_id}   反查词: {args.word!r}   (列取值全文匹配，不区分大小写)")
        print()
        found = 0
        for table in tables:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
            for col in cols:
                probe = f'SELECT 1 FROM "{table}" WHERE CAST("{col}" AS TEXT) LIKE ? LIMIT 1'
                try:
                    if not con.execute(probe, (pattern,)).fetchone():
                        continue
                except sqlite3.Error:
                    continue
                found += 1
                cnt = con.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE CAST("{col}" AS TEXT) LIKE ?', (pattern,)
                ).fetchone()[0]
                vals = [
                    r[0]
                    for r in con.execute(
                        f'SELECT DISTINCT "{col}" FROM "{table}" WHERE CAST("{col}" AS TEXT) '
                        f"LIKE ? LIMIT ?",
                        (pattern, args.samples),
                    )
                ]
                shown = " | ".join(repr(v) for v in vals)
                print(f'  {table}."{col}"   命中 {cnt} 行   真值: {shown}')
        print()
        if not found:
            print("没有任何列含有该词 → 换同义词再试，或这个词其实是**列名**概念")
            print("(列名概念用 `schema <db> --table <表>` 通读列名，别只 grep 关键词)")
        else:
            print(f"共 {found} 列命中。命中 ≥2 列时：挑与题干措辞最一致的，把结论写进 db/<库>.md")
    finally:
        con.close()


def _list_tables(con) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND substr(name, 1, 7) != 'sqlite_' ORDER BY name"
        )
    ]


def cmd_cols(args):
    """列名反查（与 find 互补：find 按**取值**，本命令按**列名**）。

    用途：题干出现 “district code / school type / 办学类型 / 资助类型” 这类**列名概念**时，
    grep 关键词不算读过列名 —— 用本命令把所有匹配的 `表.列` 列出来，并给出
    **非空行数 / 去重数**：这两个数常直接决定该选哪一列（覆盖面量级不同）。
    """
    con = connect_readonly(db_path(args.db_id), timeout=args.timeout)
    try:
        rx = re.compile(args.pattern, re.I)
        print(f"db: {args.db_id}   列名正则: {args.pattern!r}")
        print()
        hit = 0
        for table in _list_tables(con):
            for col in [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]:
                if not rx.search(col):
                    continue
                hit += 1
                try:
                    n, nd = con.execute(
                        f'SELECT COUNT("{col}"), COUNT(DISTINCT "{col}") FROM "{table}"'
                    ).fetchone()
                    vals = [
                        r[0]
                        for r in con.execute(
                            f'SELECT DISTINCT "{col}" FROM "{table}" '
                            f'WHERE "{col}" IS NOT NULL LIMIT ?',
                            (args.samples,),
                        )
                    ]
                    info = f"非空 {n} 行 / 去重 {nd}"
                except sqlite3.Error as exc:
                    vals, info = [], f"读取失败: {exc}"
                shown = " | ".join(repr(v) for v in vals)
                print(f'  {table}."{col}"   {info}   样例: {shown}')
        print()
        if not hit:
            print("没有列名匹配 → 概念可能藏在**取值**里，改用 `find <db> <词>`；或换同义说法再试。")
        elif hit > 1:
            print("命中多列 → 裁决顺序：evidence 点名 > 行集合相同则任选 > 更专门的那列（结论写回 db/<库>.md）。")
    finally:
        con.close()


def _top_split(text: str) -> list[str]:
    items, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur)
    return items


def _select_items(sql: str) -> list[str]:
    flat = " ".join(sql.split())
    up = flat.upper()
    start = up.find("SELECT")
    if start < 0:
        return []
    rest = flat[start + 6 :]
    depth, idx = 0, 0
    while idx < len(rest):
        ch = rest[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and rest[idx : idx + 4].upper() == "FROM":
            break
        idx += 1
    return [x.strip() for x in _top_split(rest[:idx])]


def _sql_profile(sql: str) -> dict:
    """一条 SQL 的结构指纹：用 SQL 文本能看出来的形状/口径特征。"""
    flat = " ".join(sql.split())
    up = flat.upper()
    tables = re.findall(r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", flat)
    if re.search(r"COUNT\s*\(\s*DISTINCT", up):
        count_form = "COUNT(DISTINCT)"
    elif re.search(r"COUNT\s*\(\s*\*", up):
        count_form = "COUNT(*)"
    elif "COUNT(" in up:
        count_form = "COUNT(列)"
    else:
        count_form = "无"
    items = _select_items(flat)
    return {
        "ncol": len(items),
        "distinct": "SELECT DISTINCT" in up,
        "count": count_form,
        "main": tables[0] if tables else "-",
        "tables": tuple(sorted(set(tables))),
        "njoin": max(0, len(tables) - 1),
        "x100": bool(re.search(r"\*\s*100", flat)),
        "between": "BETWEEN" in up,
        "like": "LIKE" in up,
        "cast": "CAST" in up,
        "strftime": "STRFTIME" in up,
        "groupby": "GROUP BY" in up,
        "limit": "LIMIT" in up,
    }


def _answered_gold(only_db: str | None = None) -> list[tuple[int, dict, str]]:
    """只取**已提交题**的金标 —— 绝不能把未做的题的金标带进来。"""
    questions = load_questions()
    answers = load_answers()
    gold = load_gold()
    rows = []
    for i, q in enumerate(questions):
        if str(i) not in answers:
            continue
        if only_db and q["db_id"] != only_db:
            continue
        rows.append((i, q, gold[i][0]))
    return rows


def _convention_stats(only_db: str | None = None) -> dict[str, dict]:
    """按库统计已提交题金标的写法惯例。

    ⭐ 单一数据源：控制台输出（cmd_conventions）与写回 db/<库>.md 的惯例卡片
    （write_card）都由这一份统计渲染 —— 不再出现“工具一套数、卡片另一套数”。
    """
    from collections import Counter

    groups: dict[str, list[str]] = {}
    for _, q, gold_sql in _answered_gold(only_db):
        groups.setdefault(q["db_id"], []).append(gold_sql)
    stats: dict[str, dict] = {}
    for db, sqls in groups.items():
        profs = [_sql_profile(s) for s in sqls]
        stats[db] = {
            "n": len(sqls),
            "sqls": sqls,
            "profs": profs,
            "ncol": Counter(p["ncol"] for p in profs),
            "count": Counter(p["count"] for p in profs),
            "distinct": sum(p["distinct"] for p in profs),
            "x100": sum(p["x100"] for p in profs),
            "between": sum(p["between"] for p in profs),
            "main": Counter(p["main"] for p in profs),
            "njoin": Counter(p["njoin"] for p in profs),
        }
    return stats


def _count_advice(st: dict) -> str:
    forms = {k: st["count"].get(k, 0) for k in ("COUNT(列)", "COUNT(DISTINCT)", "COUNT(*)")}
    total = sum(forms.values())
    if total == 0:
        return "已提交题里几乎没有计数题"
    best = max(forms, key=lambda k: forms[k])
    if best == "COUNT(DISTINCT)":
        return f"本库偏去重（{forms[best]}/{total} 计数题）⇒ 计数先试 `COUNT(DISTINCT 实体id)`"
    if best == "COUNT(*)":
        return f"本库偏 `COUNT(*)`（{forms[best]}/{total} 计数题）⇒ 计数写 `COUNT(*)`"
    return f"本库以 `COUNT(列)` 为主（{forms[best]}/{total} 计数题）⇒ 计数写 `COUNT(主表.主键列)`"


def _main_advice(st: dict) -> str:
    n = st["n"]
    top, top_n = st["main"].most_common(1)[0]
    share = top_n / n if n else 0
    if share >= 0.6:
        return f"主表几乎总是 **{top}**（{top_n}/{n}）"
    if share >= 0.35:
        return f"主表以 **{top}** 为主但**不固定**（{top_n}/{n}）⇒ 按题干主语选"
    return f"主表**不固定**（最大是 {top} 也只占 {top_n}/{n}）⇒ 按题干主语选，此处是错题重灾区"


def render_conventions(db: str, st: dict, examples: int = 0) -> str:
    out = [f"### {db}   (n={st['n']} 道已提交题的金标)"]
    out.append(f"  输出列数: {dict(st['ncol'].most_common())}")
    out.append(
        f"  计数形态: {dict(st['count'].most_common())}"
        f"   |  SELECT DISTINCT: {st['distinct']}/{st['n']}"
        f"   |  *100: {st['x100']}   |  BETWEEN: {st['between']}"
    )
    out.append(f"  主表(FROM 第一张): {dict(st['main'].most_common())}")
    out.append(f"  JOIN 数: {dict(sorted(st['njoin'].items()))}")
    if examples:
        shown = set()
        for sql, prof in zip(st["sqls"], st["profs"]):
            if prof["count"] == "无":
                continue
            shape = (prof["count"], prof["main"], prof["ncol"], prof["distinct"])
            if shape in shown:
                continue
            shown.add(shape)
            out.append(f"    计数例 {shape} -> {sql[:160]}")
            if len(shown) >= examples:
                break
    return "\n".join(out)


def render_card(db: str, st: dict) -> str:
    """惯例卡片：写回 db/<库>.md 的那一段（与 render_conventions 同一份统计）。"""
    n = st["n"]
    ncol = " / ".join(f"{k}列×{v}" for k, v in sorted(st["ncol"].items()))
    njoin = ", ".join(f"{k}:{v}" for k, v in sorted(st["njoin"].items()))
    cnt = {k: v for k, v in st["count"].most_common()}
    forms = " / ".join(f"{k} {v}" for k, v in cnt.items() if k != "无")
    return "\n".join(
        [
            f"{CARD_MARK}（实测统计，n={n} 道已提交题的金标；数据集 {DATASET_KEY}）",
            "",
            f"- 计数形态：{forms} / 无 {cnt.get('无', 0)}　⇒ {_count_advice(st)}",
            f"- 主表（FROM 第一张）：{' / '.join(f'{k} {v}' for k, v in st['main'].most_common())}"
            f"　⇒ {_main_advice(st)}",
            f"- `SELECT DISTINCT`：{st['distinct']}/{n}　|　`*100`：{st['x100']}"
            f"　|　`BETWEEN`：{st['between']}",
            f"- 输出列数分布：{ncol}",
            f"- JOIN 数分布：{njoin}",
            "",
            f"> 由 `bird_conventions db={db} write_card=true` 生成（与工具输出同源），重跑即刷新；"
            f"数字不要手改。",
        ]
    )


def write_card(db: str, st: dict) -> Path:
    """把惯例卡片写回 db/<库>.md：替换从 `## 惯例卡片` 到下一个二级标题之间的内容。"""
    path = REFS / "db" / f"{db}.md"
    if not path.exists():
        fail(
            f"没有库档案 {path}（惯例卡片写在档案末尾）—— 先用 bird_schema 摸清库结构，"
            f"按 references/db/ 里其它库的样子建一份，再刷新卡片"
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    card = render_card(db, st)
    i = text.find(CARD_MARK)
    if i < 0:
        new = text.rstrip() + "\n\n" + card + "\n"          # 没卡片过 ⇒ 追加
    else:
        j = text.find("\n## ", i + len(CARD_MARK))
        new = text[:i] + card + (text[j:] if j >= 0 else "\n")
    if new != text:
        path.write_text(new, encoding="utf-8")
    return path


def cmd_conventions(args):
    """换库第 0.5 步：用**已提交题的金标**统计本库的写作惯例（把猜惯例换成查惯例）。

    只统计形状/口径（计数形态、主表、DISTINCT、*100、区间写法…），不产出答案。
    `--write-card` 把**同一份统计**写回 db/<库>.md 的惯例卡片（卡片 = 工具输出）。
    """
    stats = _convention_stats(args.db)
    if not stats:
        fail("没有可统计的已提交题（conventions 只看已提交题的金标，避免污染未做的题）")
    if args.write_card and not (args.db or args.all):
        fail("--write-card 需要指定 --db <库> 或 --all")
    for db in sorted(stats, key=lambda d: -stats[d]["n"]):
        print(render_conventions(db, stats[db], args.examples))
        print()
        if args.write_card:
            path = write_card(db, stats[db])
            print(f"  ✎ 惯例卡片已刷新 -> {path}（n={stats[db]['n']}）")
    print("读法：COUNT(列) 多 → 默认 `COUNT(主表.主键列)`；COUNT(DISTINCT) 多 → 这个库习惯去重；")
    print("      主表分布决定『FROM 第一张表』选谁；JOIN 数大 → 金标常用 WITH 多步聚合。")
    print("      卡片与这里同源：`conventions --db <库> --write-card` 刷新后数字必然一致。")


def cmd_audit(args):
    """复盘用：对已提交题重算 EX，并按**失败类型 + 结构特征差异**归因。

    产出的是错因分布（列数/行集/值 各自多少道、哪个结构特征差得最多），不是答案。
    """
    from collections import Counter

    questions = load_questions()
    answers = load_answers()
    gold = load_gold()
    n = correct = 0
    per_db: dict[str, list[int]] = {}
    buckets: dict[str, list[int]] = {}
    wrong = []
    ids: list[int] = []
    for i, q in enumerate(questions):
        key = str(i)
        if key not in answers:
            continue
        if args.difficulty and q["difficulty"] != args.difficulty:
            continue
        if args.db and q["db_id"] != args.db:
            continue
        mine = answers[key].split("\t")[0]
        ok, detail = compare_ex(db_path(q["db_id"]), mine, gold[i])
        n += 1
        ids.append(i)
        correct += bool(ok)
        stat = per_db.setdefault(q["db_id"], [0, 0])
        stat[0] += 1
        stat[1] += bool(ok)
        if ok:
            continue
        if "列数不同" in detail:
            kind = "A 形状·列数"
        elif "整行元组不同" in detail:
            kind = "B 形状·列序/多列"
        elif "行数不同" in detail:
            kind = "C 行集不同"
        elif "取值不同" in detail:
            kind = "D 值/口径不同"
        else:
            kind = "E 其他/执行失败"
        buckets.setdefault(kind, []).append(i)
        wrong.append((i, q, mine, detail))
    if not n:
        fail("该筛选条件下没有已提交的题")
    print(f"== 已答 {n}  正确 {correct}  EX = {correct / n * 100:.2f}% ==")
    print()
    print("各库: 正确/已答")
    for db, (tot, ok) in sorted(per_db.items(), key=lambda kv: kv[1][1] / kv[1][0]):
        print(f"  {db:<26} {ok:>3}/{tot:<3} {ok / tot * 100:5.1f}%")
    print()
    answered_sql = {i: answers[str(i)].split("\t")[0] for i in ids}
    probes_log = load_probes()
    no_probe = [i for i in ids if not probes_log.get(i)]
    concept_cov = [i for i in ids if any(is_concept_probe(p) for p in probes_log.get(i, []))]
    forced = [i for i in ids if any(p.get("kind") == "force" for p in probes_log.get(i, []))]
    shaped = [i for i in ids if parse_shape(answered_sql[i])]
    print(
        f"合规：探针覆盖 {len(ids) - len(no_probe)}/{len(ids)}"
        f" ｜ 概念探针 {len(concept_cov)}/{len(ids)}"
        f" ｜ --force {len(forced)}"
        f" ｜ 写了形状声明 {len(shaped)}/{len(ids)}"
    )
    if no_probe:
        print(f"  无探针 idx：{no_probe[:20]}{' …' if len(no_probe) > 20 else ''}")
    if not shaped:
        print("  （形状声明为 0 属正常 —— 这批答案早于闸门；闸门启用后新提交的都会有。）")
    print()
    print(f"错题 {len(wrong)} 道，失败类型分布：", end="")
    print()
    print("-" * 8)
    for kind in sorted(buckets):
        print(f"  {kind:<16} {len(buckets[kind]):>3}   {buckets[kind][:20]}")
    print()
    keys = ["main", "tables", "njoin", "count", "x100", "between", "like", "strftime", "cast"]
    print("错题里『我的结构特征 ≠ 金标』的频次（最大的是首要根因）：")
    tally = []
    for k in keys:
        d = sum(1 for i, q, mine, _ in wrong if _sql_profile(mine)[k] != _sql_profile(gold[i][0])[k])
        tally.append((d, k))
    for d, k in sorted(tally, reverse=True):
        print(f"  {k:<10} {d:>3}/{len(wrong)}")
    print()
    shown: dict[str, int] = {}
    for i, q, mine, detail in wrong:
        kind = next((b for b, ids in buckets.items() if i in ids), "E")
        if shown.get(kind, 0) >= args.list:
            continue
        shown[kind] = shown.get(kind, 0) + 1
        f, g = _sql_profile(mine), _sql_profile(gold[i][0])
        diffk = [k for k in keys if f[k] != g[k]]
        print("-" * 96)
        print(f"[{i}] {q['db_id']} | {detail}")
        print(f"  Q   : {q['question'][:95]}")
        print(f"  MY  : {mine[:190]}")
        print(f"  GOLD: {' '.join(gold[i][0].split())[:190]}")
        print("  差异特征: " + ", ".join(f"{k}={f[k]} vs {g[k]}" for k in diffk))


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


PROBE_LOG = WORK_DIR / "probe_log.jsonl"
CONCEPT_KINDS = {"cols", "find"}
SHAPE_RE = re.compile(r"shape\s*:\s*(\d+|\?)\s*[x×*]\s*(\d+)", re.I)
PROBE_ONLY = {"answer", "score", "answers", "reset", "info", "list"}


def parse_shape(sql: str):
    """从 SQL 里取形状声明 `/* shape: 行数x列数 */`（闸门 2 的依据）。

    行数写 `?` 表示“不知道几行”（列表题常见）—— 那就只校验列数，但会提醒实测行数。
    能预判行数的题（计数题、极值题、单实体题）**必须写数字**，否则行数类错误拦不住。
    """
    m = SHAPE_RE.search(sql)
    if not m:
        return None
    rows = None if m.group(1) == "?" else int(m.group(1))
    return (rows, int(m.group(2)))


def _probe_ids(args) -> list[int]:
    raw = getattr(args, "for_idx", None)
    if not raw:
        return []
    return [int(x) for x in re.split(r"[,\s]+", str(raw)) if x.strip().isdigit()]


def _probe_record(idx: int, db_id: str, kind: str, detail: str):
    import datetime

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with PROBE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "idx": idx,
                    "db": db_id,
                    "ds": DATASET_KEY,
                    "kind": kind,
                    "detail": str(detail)[:200],
                    "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def log_probe(args):
    """把“我真的跑过查询”这件事记进 work/probe_log.jsonl。

    关键：只有**工具真的执行了**才会写日志 —— 不能凭空声称“我查过了”。
    `bird_answer` 的闸门 1 就是读这个日志。
    """
    idxs = _probe_ids(args)
    if not idxs:
        return
    kind = getattr(args, "command", "?") or "?"
    detail = (
        getattr(args, "pattern", None)
        or getattr(args, "word", None)
        or getattr(args, "sql", "")
        or getattr(args, "table", "")
        or ""
    )
    db_id = getattr(args, "db_id", None) or getattr(args, "db", None) or ""
    for i in idxs:
        _probe_record(i, str(db_id), str(kind), str(detail))
    print(f"🔎 已记探针：{kind} → idx {idxs}（db={db_id}）")


def load_probes() -> dict[int, list[dict]]:
    """读探针日志。

    ⭐ 按数据集过滤：三个数据集的 idx 体系互相重叠（dev2025 的 344 与 minidev 的 344 是
    两道完全不同的题），不隔离就会出现“在 A 集查过 ⇒ B 集同号题也能交”的假通过。
    早期没有 ds 字段的历史记录按“兼容”处理（视为当前数据集）。
    """
    out: dict[int, list[dict]] = {}
    if not PROBE_LOG.exists():
        return out
    for line in PROBE_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("ds") and rec["ds"] != DATASET_KEY:
            continue
        if isinstance(rec.get("idx"), int):
            out.setdefault(rec["idx"], []).append(rec)
    return out


def is_concept_probe(p: dict) -> bool:
    """算不算“概念探针”（列名/取值真的被查过）？"""
    if p.get("kind") in CONCEPT_KINDS:
        return True
    return p.get("kind") == "run" and "DISTINCT" in (p.get("detail") or "").upper()


REFS = Path(os.environ["BIRD_REFS"]) if os.environ.get("BIRD_REFS") else (
    ROOT / ".pi" / "skills" / "bird-sql" / "references"
)  # 覆盖点给测试用（tools/tests/*）：把惯例卡片写进临时目录，不动真档案
PUSH_RE = re.compile(r"<!--\s*push\s+step=([0-9.]+)\s*-->(.*?)<!--\s*/push\s*-->", re.S)


def push_blocks(step: str | None = None):
    """从 reference 知识库里抽出带 `<!-- push step=N -->` 标记的片段。

    文档是**唯一数据源**：改文件 = 改推送内容，不会出现“文档与工具两份说法”。
    """
    blocks = []
    if not REFS.exists():
        return blocks
    for f in sorted(REFS.glob("*.md")):
        for m in PUSH_RE.finditer(f.read_text(encoding="utf-8", errors="replace")):
            if step and m.group(1) != str(step):
                continue
            body = m.group(2).strip()
            if body:
                blocks.append((m.group(1), f.name, body))
    return blocks


CARD_MARK = "## 惯例卡片"


def brief_for_db(db_id: str) -> tuple[str | None, str | None]:
    """当前库档案：返回 (必查小节, **整个档案文本**)。

    ⭐ 不再按小节名“猜”要推什么：整份档案都推，新增小节会自动送到眼前。
    位置猜测正是缺陷源头 —— 曾经夹在必查与惯例卡片之间的『值域陷阱』（card_games）、
    『补充（第 24 轮实测 40 道 moderate）』（thrombosis，53 行）**永远不会被送达**。
    """
    path = REFS / "db" / f"{db_id}.md"
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return _must_section(text), text


def _must_section(text: str) -> str | None:
    """档案里的『交题前必查』小节（交题瞬间要回放的那几条）。"""
    m = re.search(r"##\s*[^\n]*交题前必查[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.S)
    return m.group(1).strip() if m else None


def _card_section(text: str) -> str | None:
    """档案里的『惯例卡片』小节。"""
    i = text.find(CARD_MARK)
    if i < 0:
        return None
    j = text.find("\n## ", i + len(CARD_MARK))
    return text[i : j if j >= 0 else len(text)].strip()


def cmd_brief(args):
    """决策点推送：把知识库真正递到我眼前，而不是指望我“主动去读”。"""
    step = None if args.step in (None, "all") else str(args.step)
    if args.db_id:
        _, profile = brief_for_db(args.db_id)
        print(f"╔══ 库档案 {args.db_id} ══")
        if profile:
            print(f"（整份档案 {len(profile.splitlines())} 行，全文送上 —— 不按小节名筛，"
                  f"避免中间新增的小节静默丢失）")
            print(profile)
        else:
            print(f"⚠️ 还没有 db/{args.db_id}.md 档案：先用 bird_schema 摸清库结构，再建一份")
        print()
    blocks = push_blocks(step)
    print(f"╔══ 知识库推送（step={step or 'all'}，共 {len(blocks)} 段）══")
    for s, name, body in blocks:
        print(f"\n──[step {s}] {name} ──")
        print(body)
    if not blocks:
        print("（没有带 push 标记的片段 —— 去 references/*.md 里用 <!-- push step=N --> 包住要推送的内容）")


def cmd_answer(args):
    questions = load_questions()
    if not 0 <= args.idx < len(questions):
        fail(f"idx 越界，合法范围 0–{len(questions) - 1}")
    db_id = questions[args.idx]["db_id"]
    sql = guard_sql(args.sql)

    probes = load_probes()
    mine = probes.get(args.idx, [])

    # ══ 闸门 1：探针覆盖 —— “我查过了”必须有工具日志作证 ══
    if not mine and not args.force:
        fail(
            f"拒绝记录（闸门 1：探针覆盖）：第 {args.idx} 题没有任何探针记录。\n"
            f"  先跑一次真实查询并带上 --for {args.idx}，例如：\n"
            f'    run  {db_id} "SELECT DISTINCT 列 FROM 表 LIMIT 5" --for {args.idx}\n'
            f'    cols {db_id} "概念正则" --for {args.idx}\n'
            f'    find {db_id} 关键词 --for {args.idx}\n'
            "  确实一目了然、不需要任何探测的题，加 --force（会在 probe_log 留痕，audit 会统计）。"
        )

    # ══ 闸门 2：形状预演 —— 行列数必须写进 SQL 注释，并被实测验证 ══
    expected = parse_shape(sql)
    if expected is None and not args.force:
        fail(
            "拒绝记录（闸门 2：形状预演）：SQL 里没有形状声明。\n"
            "  请在 SQL 最前面写上预测的结果集形状注释：\n"
            "    /* shape: 行数x列数 */  SELECT ...    （例：预测 3 行 1 列 → /* shape: 3x1 */；\n"
            "     列表题不知道几行时写 /* shape: ?x2 */ —— 那就只校验列数，但会提醒你实测行数）\n"
            "  这是防『列数 / 列序 / 行数』类错误的硬闸门：声明与实测不符会被拒绝。"
        )

    # ⭐ P13 修复：形状校验必须基于**完整结果**，不能拿被截断的数字去比行数。
    #   ① 先按大上限取一次（VERIFY_LIMIT，与 --max-rows 无关）；
    #   ② 若仍被截断，用 COUNT(*) 把真实行数数准；
    #   ③ 连数都数不出来，才退化为「只校验列数」并**明确说出来**。
    #   `--max-rows` 从此只影响**预览打印**。
    VERIFY_LIMIT = 50000
    try:
        columns, rows, truncated, _ = run_sql(db_id, sql, max_rows=VERIFY_LIMIT)
    except sqlite3.Error as exc:
        fail(f"SQL 在 {db_id} 上执行失败，未记录：{exc}")

    n_rows = len(rows)
    if truncated:
        n_rows = _exact_rows(db_id, sql, fallback=None)
        if n_rows is None:
            print(f"⚠️ 结果超过 {VERIFY_LIMIT} 行且数不出准确行数 ⇒ 本次**只校验列数，不校验行数**。")
        else:
            print(f"ℹ️ 结果 {n_rows} 行（超过一次取回的上限 {VERIFY_LIMIT}，已用 COUNT(*) 数准）")
    print(f"执行通过：{n_rows if n_rows is not None else str(len(rows)) + '+'} 行，{len(columns)} 列")

    def _shape_fail(msg: str):
        if args.force:
            print(f"⚠️ {msg} 已用 --force 放行")
        else:
            fail(
                f"拒绝记录（闸门 2）：{msg}\n"
                "  先弄清差在哪里（题干漏列/多列？条件过严过松？主表选错？），改好再交。"
            )

    if expected and expected[1] != len(columns):
        _shape_fail(f"列数不符 —— 声明 {expected[1]} 列，实测 {len(columns)} 列。")
    elif expected and expected[0] is None:
        print(
            f"📐 形状：声明 ? 行（未预判）× {expected[1]} 列，实测 "
            f"{n_rows if n_rows is not None else '未知'} 行 —— 列数对上了；行数请自己对着题面再核一眼。"
        )
    elif expected and n_rows is None:
        print(f"📐 形状：声明 {expected[0]} 行 —— 结果太大数不出准确行数，**这一项没校验**（列数已对上）。")
    elif expected and expected[0] != n_rows:
        _shape_fail(
            f"形状预演不符：声明 {expected[0]} 行 × {expected[1]} 列，"
            f"实测 {n_rows} 行 × {len(columns)} 列。"
        )

    preview = rows[: args.max_rows]
    print()
    print(fmt_rows(columns, preview))
    if len(rows) > args.max_rows:
        print(f"\n... 预览只显示前 {args.max_rows} 行（形状校验用的是完整结果，不受 --max-rows 影响）")
    print()

    if args.force:
        _probe_record(args.idx, db_id, "force", f"expected={expected} kinds={[p.get('kind') for p in mine]}")
        print("⚠️ 本条用了 --force，已记进 probe_log（audit 会统计）")

    with answers_lock():
        answers = load_answers()
        answers[str(args.idx)] = f"{sql}\t----- bird -----\t{db_id}"
        save_answers(answers)
        total = len(answers)
    print(f"已记录第 {args.idx} 题（{db_id}），当前完成 {total} 题 -> {ANSWERS_FILE}")

    # ══ 知识推送的最后一环：交题瞬间回放本库必查与惯例 ══
    must, profile = brief_for_db(db_id)
    if profile:
        card = _card_section(profile)
        if card:
            lines = [ln for ln in card.splitlines() if ln.startswith("- ")]
            if lines:
                print("📌 惯例回放：" + " ｜ ".join(ln[2:].strip() for ln in lines[:2]))
    if must:
        items = [ln.strip() for ln in must.splitlines() if re.match(r"^\d+\.", ln.strip())]
        if items:
            print(f"📌 必查回放（{len(items)} 条，下一题前过一眼）：")
            for it in items:
                print("   " + it[:150])
    db_probes = [p for ps in probes.values() for p in ps if p.get("db") == db_id]
    if not any(is_concept_probe(p) for p in db_probes):
        print(
            f"⚠️ {db_id} 还没有任何概念探针（{'/'.join(sorted(CONCEPT_KINDS))} 或带 DISTINCT 的 run）：\n"
            "   列名靠猜是本项目最大失分源 —— 交完这批请补一次 `cols <db> 正则` / `find <db> 词`。"
        )


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
    p.add_argument("--for", dest="for_idx", help="把这次探针记给这些 idx（逗号分隔）")
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser(
        "find", help="概念词反查：库内哪张表哪一列含这个词（别用英文语感猜列名）"
    )
    p.add_argument("db_id")
    p.add_argument("word")
    p.add_argument("--samples", type=int, default=3, help="每个命中列显示几个真值")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--for", dest="for_idx", help="把这次探针记给这些 idx（逗号分隔）")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("cols", help="列名反查：这个概念（列名）出现在哪些表的哪些列（含非空/去重行数）")
    p.add_argument("db_id")
    p.add_argument("pattern", help="列名正则，例如 'type|kind|option'")
    p.add_argument("--samples", type=int, default=3)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--for", dest="for_idx", help="把这次探针记给这些 idx（逗号分隔）")
    p.set_defaults(func=cmd_cols)

    p = sub.add_parser("conventions", help="用已提交题的金标统计本库写作惯例（换库第 0.5 步）")
    p.add_argument("--db", help="只看某个库")
    p.add_argument("--examples", type=int, default=2, help="每个库打印几条计数题金标作形状示范")
    p.add_argument(
        "--write-card",
        dest="write_card",
        action="store_true",
        help="把同一份统计写回 db/<库>.md 的惯例卡片（卡片 = 工具输出，单一数据源）",
    )
    p.add_argument("--all", action="store_true", help="配合 --write-card：刷新所有库的卡片")
    p.set_defaults(func=cmd_conventions)

    p = sub.add_parser("audit", help="复盘：按失败类型与结构特征差异归因已提交的错题")
    p.add_argument("--difficulty", choices=["simple", "moderate", "challenging"])
    p.add_argument("--db")
    p.add_argument("--list", type=int, default=3, help="每类失败原因打印几条例子")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("brief", help="决策点推送：库档案（必查+惯例卡片）+ 知识库里带 push 标记的片段")
    p.add_argument("db_id", nargs="?")
    p.add_argument("--step", help="只推某个步骤的片段（0/1/3/3.5/4/5/6/7）")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("schema", help="表结构 + 行数 + 样例值")
    p.add_argument("db_id")
    p.add_argument("--table", help="只看某一张表")
    p.add_argument("--samples", type=int, default=3, help="每列显示几个去重样例值（0 关闭）")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--for", dest="for_idx", help="把这次探针记给这些 idx（逗号分隔）")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("desc", help="读人工标注的 database_description CSV")
    p.add_argument("db_id")
    p.add_argument("--table", help="只看某张表")
    p.add_argument("--for", dest="for_idx", help="把这次探针记给这些 idx（逗号分隔）")
    p.set_defaults(func=cmd_desc)

    p = sub.add_parser("run", help="在指定库上试跑只读 SQL")
    p.add_argument("db_id")
    p.add_argument("sql")
    p.add_argument("--max-rows", type=int, default=50)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--for", dest="for_idx", help="把这次探针记给这些 idx（逗号分隔）—— answer 的闸门 1 凭据")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("answer", help="记录第 idx 题的最终 SQL（有探针覆盖 + 形状预演两道闸门）")
    p.add_argument("idx", type=int)
    p.add_argument("sql")
    p.add_argument(
        "--max-rows",
        type=int,
        default=20,
        help="预览只打印这么多行；形状校验用完整结果，不受它影响（P13）",
    )
    p.add_argument("--force", action="store_true", help="跳过闸门 1/2（会在 probe_log 留痕）")
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
    # 探针留痕统一在分发层做：run / find / cols / schema / desc … 只要带了 --for 就记账，
    # 而 answer / score 自己不作为“探针”（避免用“提交动作”冒充“查证动作”）。
    if getattr(args, "for_idx", None) and getattr(args, "command", "") not in PROBE_ONLY:
        log_probe(args)


if __name__ == "__main__":
    main()
