# -*- coding: utf-8 -*-
"""Offline gamma audit. No model calls; does not alter runner defaults.

Gold SQL is used only by the evaluator, never by the sample-selection heuristic.
SQLite's authorizer records dependencies while EXPLAIN compiles SQL (no query execution).
Sizes are character counts, NOT tokenizer counts or measured EX improvements.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner import prompt as pm


def dependencies(con: sqlite3.Connection, sql: str) -> tuple[set[str], set[tuple[str, str]]]:
    """Resolve aliases, quoted identifiers, CTEs, wildcards via SQLite itself."""
    if not re.match(r"\s*(SELECT|WITH)\b", sql, re.I):
        raise ValueError("Only SELECT/WITH gold queries are accepted")
    tables, columns = set(), set()

    def auth(action, arg1, arg2, database, source):
        if action == sqlite3.SQLITE_READ:
            # SQLite reports database=None for the empty-column COUNT(*) read.
            if database in ("main", None) and arg1:
                tables.add(arg1)
                if arg2:
                    columns.add((arg1, arg2))
            return sqlite3.SQLITE_OK
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION,
                      sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    con.set_authorizer(auth)
    try:
        # Compile only. Do not fetch or execute the query being explained.
        con.execute("EXPLAIN " + sql)
    finally:
        con.set_authorizer(None)
    return tables, columns


def words(text: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return set(re.findall(r"[a-z]+|\d+", text.lower()))


def selected_columns(schema: dict, question: str, evidence: str) -> set[tuple[str, str]]:
    """Exploratory lexical selector. No DB-specific rules, gold, or substring matching."""
    tokens = words(question + "\n" + evidence)
    keep = set()
    for table, columns in schema.items():
        for column in columns:
            terms = words(column)
            if terms and (terms <= tokens or any(len(w) >= 5 and w in tokens
                                                 for w in terms - pm.STOPWORDS)):
                keep.add((table, column))
    return keep


def render_variant(full: str, schema: dict, mode: str,
                   selected: set[tuple[str, str]]) -> str:
    """Retain all table/column/type/PK lines; optionally strip sample suffixes."""
    table = None
    output = []
    for line in full.splitlines():
        if line.startswith("### "):
            table = next((t for t in schema if line.startswith(f"### {t}  (")), None)
        if table and line.startswith("  "):
            # These delimiters are emitted by runner.prompt.schema_block.
            match = re.search(r"   (?:ALL \d+ values: |e\.g\. )", line)
            if match:
                column = next((c for c in sorted(schema[table], key=len, reverse=True)
                               if line.startswith("  " + c + " ")), None)
                low_card = line[match.start():].startswith("   ALL ")
                retain = (mode == "full" or (mode == "low_card" and low_card)
                          or (mode == "selective" and
                              (low_card or (table, column) in selected)))
                if not retain:
                    line = line[:match.start()]
        output.append(line)
    return "\n".join(output).strip()


def self_test() -> None:
    con = sqlite3.connect(":memory:", cached_statements=0)
    try:
        con.executescript('CREATE TABLE a (id INTEGER, "odd name" TEXT, year INT);'
                          'CREATE TABLE b (id INTEGER, score REAL);')
        cases = [
            ('WITH x AS (SELECT id, `odd name` AS n FROM a) SELECT n FROM x',
             {("a", "id"), ("a", "odd name")}),
            ('SELECT year FROM a ORDER BY year', {("a", "year")}),
            ('SELECT * FROM a', {("a", "id"), ("a", "odd name"), ("a", "year")}),
            ('SELECT t.id FROM a t WHERE EXISTS (SELECT 1 FROM b t WHERE t.score > 0)',
             {("a", "id"), ("b", "score")}),
        ]
        for sql, expected in cases:
            _, cols = dependencies(con, sql)
            assert cols == expected, (sql, cols, expected)
        tables, cols = dependencies(con, 'SELECT COUNT(*) FROM a')
        assert tables == {"a"} and cols == set(), (tables, cols)
        try:
            dependencies(con, 'DELETE FROM a')
        except ValueError:
            pass
        else:
            raise AssertionError("write accepted")
        schema = {"a": ["id", "odd name", "year"]}
        full = ('### a  (0 rows)\n  id INTEGER   e.g. 1 | 2 …\n'
                '  odd name TEXT   ALL 2 values: A | B\n  year INT')
        for mode in ("full", "names", "low_card", "selective"):
            result = render_variant(full, schema, mode, {("a", "id")})
            for col in schema["a"]:
                assert "  " + col + " " in result
        assert render_variant(full, schema, "full", set()) == full
        assert "e.g." not in render_variant(full, schema, "low_card", set())
        assert "ALL 2 values" in render_variant(full, schema, "low_card", set())
        assert "e.g." in render_variant(full, schema, "selective", {("a", "id")})
        assert ("a", "year") not in selected_columns(schema, "yearbook", "")
    finally:
        con.close()
    print("Self-test passed: CTE/quotes/year/star/alias scopes/count/write guard/render/boundaries")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dataset", choices=["dev2025"], default="dev2025")
    ap.add_argument("--out", default="work/experiments/gamma_schema_audit.json")
    args = ap.parse_args()
    self_test()
    if args.self_test:
        return 0
    os.environ["BIRD_DATASET"] = args.dataset
    sys.path.insert(0, str(ROOT / "tools"))
    import bird
    assert bird.DATASET_KEY == args.dataset
    questions = bird.load_questions()
    system = pm.build_system(ROOT / ".pi/skills/bird-sql/references")
    cache = {}
    records, errors = [], []
    for idx, q in enumerate(questions):
        db_id = q["db_id"]
        if db_id not in cache:
            path = bird.db_path(db_id)
            con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                  cached_statements=0)
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            schema = {t: [r[1] for r in con.execute(
                'PRAGMA table_info("' + t.replace('"', '""') + '")')] for t in names}
            cache[db_id] = (con, schema, pm.schema_block(path),
                            pm.descriptions_block(db_id, path))
        con, schema, full, desc = cache[db_id]
        evidence = q.get("evidence") or ""
        selected = selected_columns(schema, q["question"], evidence)
        rec = {"idx": idx, "db_id": db_id, "difficulty": q.get("difficulty"),
               "system_chars": len(system), "descriptions_chars": len(desc), "sizes": {}}
        for mode in ("full", "names", "low_card", "selective"):
            rendered = render_variant(full, schema, mode, selected)
            # Check metadata preservation independently from gold extraction.
            for t, cols in schema.items():
                assert f"### {t}  (" in rendered
                for c in cols:
                    assert any(line.startswith("  " + c + " ")
                               for line in rendered.splitlines()), (idx, mode, t, c)
            user = pm.build_user(q["question"], evidence, db_id, rendered, desc)
            rec["sizes"][mode] = {"schema_chars": len(rendered),
                                   "base_prompt_chars": len(system) + len(user)}
        try:
            tables, cols = dependencies(con, q["SQL"])
            rec.update(gold_tables=len(tables), gold_columns=len(cols),
                       lexical_hits=len(cols & selected),
                       lexical_complete=cols <= selected)
        except (sqlite3.Error, ValueError) as exc:
            errors.append({"idx": idx, "db_id": db_id, "error": str(exc)})
        records.append(rec)
    for con, *_ in cache.values():
        con.close()
    groups = defaultdict(list)
    for r in records:
        groups["all"].append(r)
        groups[r["db_id"]].append(r)
    summary = {}
    for group, rows in groups.items():
        modes = {}
        for mode in ("full", "names", "low_card", "selective"):
            sc = sum(r["sizes"][mode]["schema_chars"] for r in rows)
            pc = sum(r["sizes"][mode]["base_prompt_chars"] for r in rows)
            modes[mode] = {"mean_schema_chars": sc / len(rows),
                           "mean_base_prompt_chars": pc / len(rows),
                           "schema_saved": 1 - sc / sum(r["sizes"]["full"]["schema_chars"] for r in rows),
                           "base_prompt_saved": 1 - pc / sum(r["sizes"]["full"]["base_prompt_chars"] for r in rows)}
        valid = [r for r in rows if "gold_columns" in r]
        summary[group] = {"n": len(rows), "dependencies_ok": len(valid), "modes": modes,
                          "lexical_complete": sum(r["lexical_complete"] for r in valid),
                          "lexical_column_recall": sum(r["lexical_hits"] for r in valid) /
                          max(1, sum(r["gold_columns"] for r in valid))}
    output = {"dataset": args.dataset, "units": "characters; not tokens",
              "scope": "Base prompt only; reconnaissance and retry messages excluded. No API calls.",
              "selection": "Lexical, no recon, no embeddings; not paper schema linking.",
              "summary": summary, "dependency_errors": errors, "records": records}
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to(ROOT):
        ap.error("Output must stay within the project")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["all"], ensure_ascii=False, indent=2))
    print(f"Dependency errors: {len(errors)}; results: {out.relative_to(ROOT)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
