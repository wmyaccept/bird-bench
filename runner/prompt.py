# -*- coding: utf-8 -*-
"""prompt 组装层：把 `prompt/` 里的规则 + 库档案 + 真库 schema + 人工标注 拼成一次请求。

  system  = 任务说明 + 规则（traps.md / shapes.md）+ 该库的档案（db/<db_id>.md）
  user    = 题目 + evidence + schema（列名/类型/样例值）+ 人工标注的列含义

为什么 system 里只放 traps/shapes 而不放 SKILL.md/checklist.md：
那两份是**给我们 agent 的流程**（bird_* 工具、四道闸门、--checks 留痕），
对着一台只会写 SQL 的模型说这些是噪音。规则文本本身（traps/shapes）才是知识。
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

RULES_FILES = ["traps.md", "shapes.md"]

PREAMBLE = """You are an expert SQLite analyst. Given a question about a database, write ONE SQLite
query that answers it.

Output format — a single fenced block, nothing else:
```sql
SELECT ...
```

Hard requirements:
- exactly one statement, read-only (SELECT / WITH). Never INSERT/UPDATE/DELETE/DROP/PRAGMA.
- SQLite dialect only (no T-SQL / MySQL / Postgres syntax).
- column order and the number of columns matter: give exactly the columns the question asks for,
  in the order asked. Do not add extra columns "for context".
- if the question asks "how many", return a single count; if it asks for a list, do not aggregate it.
- never rely on any ground-truth query: you only have the question, the evidence, and the schema.
"""


def build_system(prompt_dir: Path, db_id: str, rules: list[str] | None = None) -> str:
    """system prompt = 任务说明 + 规则 + 该库档案（有档案才加）。"""
    parts = [PREAMBLE]
    for name in (rules if rules is not None else RULES_FILES):
        p = prompt_dir / name
        if p.exists():
            parts.append(f"\n# Rules — {name}\n\n{p.read_text(encoding='utf-8').strip()}")
    card = prompt_dir / "db" / f"{db_id}.md"
    if card.exists():
        parts.append(
            f"\n# Notes collected on the database `{db_id}` (from earlier mistakes — trust them)\n\n"
            f"{card.read_text(encoding='utf-8').strip()}"
        )
    return "\n".join(parts)


def schema_block(db_path: Path, samples: int = 3, max_sample_len: int = 30,
                 tables: list[str] | None = None) -> str:
    """紧凑的 schema：表名(行数) → 每列 名称/类型/主键/去重样例值。"""
    con = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND substr(name, 1, 7) != 'sqlite_' ORDER BY name")]
        if tables:
            names = [n for n in names if n in tables]
        out = []
        for name in names:
            count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            out.append(f"### {name}  ({count:,} rows)")
            for _cid, col, ctype, _nn, _dflt, pk in con.execute(f'PRAGMA table_info("{name}")'):
                line = f"  {col} {ctype or '?'}{' PK' if pk else ''}"
                if samples > 0 and "BLOB" not in (ctype or "").upper():
                    try:
                        got = con.execute(
                            f'SELECT DISTINCT "{col}" FROM "{name}" '
                            f'WHERE "{col}" IS NOT NULL LIMIT {samples}').fetchall()
                        vals = [str(g[0]).replace("\n", " ")[:max_sample_len] for g in got]
                        if vals:
                            line += "   e.g. " + " | ".join(vals)
                    except sqlite3.Error:
                        pass
                out.append(line)
            out.append("")
        return "\n".join(out).strip()
    finally:
        con.close()


def descriptions_block(db_id: str, db_path: Path, column_meaning: dict | None = None) -> str:
    """人工标注的列含义：优先用库目录下的 database_description/*.csv，其次官方 column_meaning.json。"""
    lines: list[str] = []
    desc_dir = db_path.parent / "database_description"
    if desc_dir.exists():
        for f in sorted(desc_dir.glob("*.csv")):
            lines.append(f"### {f.stem}")
            with f.open(encoding="utf-8", errors="replace", newline="") as fh:
                for i, row in enumerate(csv.reader(fh)):
                    if i == 0 or not any(c.strip() for c in row):
                        continue          # 跳过表头与空行
                    if len(row) >= 3 and (row[2].strip() or (len(row) > 4 and row[4].strip())):
                        note = row[2].strip()
                        if len(row) > 4 and row[4].strip():
                            note += f" (values: {row[4].strip()})"
                        lines.append(f"  {row[0].strip()}: {note}")
            lines.append("")
    if not lines and column_meaning:
        lines = _descriptions_from_json(db_id, column_meaning)
    return "\n".join(lines).strip()


def _descriptions_from_json(db_id: str, cm: dict) -> list[str]:
    """容忍 column_meaning.json 的几种可能形状（官方只说"同 TA-SQL"，没给 schema）。"""
    out: list[str] = []

    def emit(table: str, col: str, note) -> None:
        if isinstance(note, dict):
            note = note.get("description") or note.get("column_description") or ""
        note = str(note or "").strip()
        if note:
            out.append(f"  {table}.{col}: {note}")

    sub = cm.get(db_id) if isinstance(cm, dict) else None
    if isinstance(sub, dict):
        for table, cols in sub.items():
            if isinstance(cols, dict):
                out.append(f"### {table}")
                for col, note in cols.items():
                    emit(table, col, note)
    if not out and isinstance(cm, dict):          # "db.table.col" → 描述
        for key, note in cm.items():
            if isinstance(key, str) and key.startswith(f"{db_id}."):
                bits = key.split(".")
                if len(bits) >= 3:
                    emit(bits[-2], bits[-1], note)
    if not out and isinstance(cm, list):          # [{db_id, table, column, description}]
        for rec in cm:
            if isinstance(rec, dict) and rec.get("db_id") == db_id:
                emit(rec.get("table", "?"), rec.get("column", "?"),
                     rec.get("description") or rec.get("column_description"))
    return out


def build_user(question: str, evidence: str, db_id: str, schema: str,
               descriptions: str = "") -> str:
    parts = [f"Database: {db_id}", "", "## Schema", schema]
    if descriptions:
        parts += ["", "## Column meanings (human-annotated)", descriptions]
    parts += ["", "## Question", question.strip()]
    if evidence and evidence.strip():
        parts += ["", "## Evidence (external knowledge you must use)", evidence.strip()]
    parts += ["", "Write the single SQLite query now."]
    return "\n".join(parts)


_FENCE = re.compile(r"```(?:sql|sqlite)?\s*(.+?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    """从模型回复里抽 SQL：优先 ```sql 围栏，其次整段文本。"""
    m = _FENCE.search(text or "")
    sql = (m.group(1) if m else (text or "")).strip()
    sql = re.sub(r"^(here (is|are)[^\n]*|sql[:：])\s*", "", sql, flags=re.I)
    sql = sql.strip().strip("`").strip()
    while sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql


def load_column_meaning(path: str | None) -> dict | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
