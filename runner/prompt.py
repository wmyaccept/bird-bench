# -*- coding: utf-8 -*-
"""prompt 组装层：把 `prompt/` 里的规则 + **运行时查库得到的侦察结果** + 真库 schema 拼成一次请求。

  system  = 任务说明 + 规则（traps.md / shapes.md）—— 与库无关，任何库都是同一份
  user    = 题目 + evidence + schema（列名/类型/**低基数列的全量取值**）+ 人工标注 + 取值侦察

为什么不放库专属档案（历史上是 db/<db_id>.md 手写档案）：
那些档案只能覆盖我们事先见过的 11 个 dev 库，隐藏 test 库有 15 个、一个都命中不了 ——
方法会在 test 上退化成"规则 + DDL + 每列 3 个样例值"。现在改成**运行时查库**：
库里存了什么值、某个字面量落在哪张表哪一列，都由当场 SELECT 得到，对任何库都成立。

为什么 system 里只放 traps/shapes 而不放 SKILL.md/checklist.md：
那两份是**给我们 agent 的流程**（bird_* 工具、四道闸门、--checks 留痕），
对着一台只会写 SQL 的模型说这些是噪音。规则文本本身（traps/shapes）才是知识。
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
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


# β 实验臂：**换生成方法论**，其余（规则文件 / schema / 侦察 / 温度）与 direct 臂逐字节相同。
# 目的：测"方法论多样性"是否带来候选池增益 —— 对照是同骨架的 A 臂在并集里只贡献 1 题。
# ⚠️ 只准改推理流程与输出纪律，**不许**改硬约束（改了就会变成第二个混杂变量）。
PREAMBLE_DNC = """You are an expert SQLite analyst. Answer the question through three explicit stages,
then write ONE SQLite query.

Stage 1 — Decompose. List the minimal sub-facts the question needs. For each sub-fact name the
table and column that carries it, and say whether it needs a filter, a join, or an aggregate.

Stage 2 — Solve each sub-fact on its own. Write the small SQL fragment (plain text) that gets it,
including the exact WHERE literals, join keys and aggregate form. Check each fragment against the
schema before moving on.

Stage 3 — Compose. Merge the fragments into a single query, then re-check that every filter in the
question appears exactly once and that the SELECT list is exactly what was asked for.

Do NOT put the Stage 1/2 fragments inside a ```sql fence — that fence is reserved for the final
answer, and a fragment sitting in it would be mistaken for the answer.

Output format — a single fenced block at the end, nothing else:
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

VARIANTS = {"direct": PREAMBLE, "dnc": PREAMBLE_DNC}


def build_system(prompt_dir: Path, rules: list[str] | None = None,
                 variant: str = "direct") -> str:
    """system prompt = 任务说明 + 规则。**刻意与库无关**：任何库拿到的是同一份 system。

    `variant` 只换"怎么写"的方法论（direct / dnc），规则文件与硬约束逐字相同 ——
    于是两个臂的差异只剩生成方法论，不会混进"知识注入方式"这个变量。
    """
    parts = [VARIANTS[variant]]
    for name in (rules if rules is not None else RULES_FILES):
        p = prompt_dir / name
        if p.exists():
            parts.append(f"\n# Rules — {name}\n\n{p.read_text(encoding='utf-8').strip()}")
    return "\n".join(parts)


def schema_block(db_path: Path, samples: int = 3, max_sample_len: int = 30,
                 tables: list[str] | None = None, low_card_max: int = 12) -> str:
    """紧凑的 schema：表名(行数) → 每列 名称/类型/主键/取值。

    ⭐ 低基数列（去重取值 ≤ low_card_max）**把取值全列出来**，高基数列才只给 samples 个样例。
    这是替代"手写库档案"的主要机制：库里的封闭取值域（`'CZK'`/`'EUR'`、`'LAM'/'SME'/'KAM'`、
    日期到底是 `YYYYMM` 还是 `YYYY-MM-DD`）由当场查库得到，任何没见过的库都同样有效，
    而我们一个字都不用提前写。因为这本来就是同一条 `SELECT DISTINCT ... LIMIT k`，
    把 k 放大到 low_card_max 就顺便区分了"这就是全部取值"与"这只是样例"，几乎不额外花钱。
    """
    con = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND substr(name, 1, 7) != 'sqlite_' ORDER BY name")]
        if tables:
            names = [n for n in names if n in tables]
        probe_limit = max(samples, low_card_max) if low_card_max else samples
        out = []
        for name in names:
            count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            out.append(f"### {name}  ({count:,} rows)")
            for _cid, col, ctype, _nn, _dflt, pk in con.execute(f'PRAGMA table_info("{name}")'):
                line = f"  {col} {ctype or '?'}{' PK' if pk else ''}"
                if probe_limit > 0 and "BLOB" not in (ctype or "").upper():
                    try:
                        got = con.execute(
                            f'SELECT DISTINCT "{col}" FROM "{name}" '
                            f'WHERE "{col}" IS NOT NULL LIMIT {probe_limit + 1}').fetchall()
                        vals = [str(g[0]).replace("\n", " ")[:max_sample_len] for g in got]
                        if vals and low_card_max and len(vals) <= low_card_max:
                            line += f"   ALL {len(vals)} values: " + " | ".join(vals)
                        elif vals:
                            line += "   e.g. " + " | ".join(vals[:samples])
                            if len(vals) > samples:
                                line += " …"
                    except sqlite3.Error:
                        pass
                out.append(line)
            out.append("")
        return "\n".join(out).strip()
    finally:
        con.close()


# --------------------------------------------------------------- 运行时取值侦察
# 这是替代"手写库档案"的机制。历史档案里真正有用的只有两件事：
#   ① 库里的封闭取值域（'SVK' / 'LAM' / 日期到底是 YYYYMM 还是 YYYY-MM-DD）→ 由 schema_block 的低基数列全量取值给出；
#   ② 题干里的字面量落在哪张表哪一列 → 由下面的 reconnaissance 当场查出来。
# ⛔ 不要再往 prompt 目录里写任何"某个库专属"的笔记：隐藏 test 库有 15 个，命中率恒为 0。

STOPWORDS = frozenset("""
a an the and or not but if then than that this these those there here is are was were be been
being do does did doing have has had having can could should would may might must will shall
for with from into over under about above below between among during after before all any both
each every few more most other some such only own same so too very what which who whom whose
when where why how list find give show return report identify calculate determine provide name
count total average number sum per year month day first last top best highest lowest least
percent percentage ratio proportion mean median maximum minimum difference increase decrease
change growth rate frequency distribution largest smallest
sql sqlite select insert update delete drop create table join group order having limit offset
union using distinct case when null value values
max min avg sum count stddev variance length substr cast coalesce ifnull nullif round abs
""".split())

# 短的全大写串未必是取值（很多是 SQL 关键字/缩写），别浪费侦察预算
CAPS_BLOCK = frozenset("""
SQL NULL AND OR NOT SELECT FROM WHERE JOIN GROUP ORDER HAVING LIMIT OFFSET UNION AS ON BY
COUNT SUM AVG MIN MAX DISTINCT CASE WHEN THEN ELSE END WITH INSERT UPDATE DELETE DROP CREATE
USING ASC DESC IN IS LIKE BETWEEN EXISTS ALL ANY ID OK URL API EOF
""".split())


def extract_terms(question: str, evidence: str = "", max_terms: int = 8) -> list[str]:
    """从题干/evidence 里挑出"可能以取值形式躺在库里"的字面量。

    优先级：引号内字面量 > 全大写短码（'SVK'/'CZK'）> 首字母大写的实体词。
    宁少勿滥：每个词都要在整库所有列上扫一遍，所以默认只取 top `max_terms` 个。
    ⛔ 不抽数字/年份："2000/1/1" 里的 2000 会命中满屏的街道号/邮编（实测 15 列噪声），
      而日期格式本来就能从 schema 的降基数列取值里看出来（`ALL 4 values: 2012-08-25 | ...`）。
    """
    text = f"{question}\n{evidence or ''}"
    cands: list[tuple[int, str]] = []
    for m in re.finditer(r"['\u2018\u201c]([^'\"\u2018\u2019\u201c\u201d]{2,40})['\u2019\u201d]", text):
        cands.append((0, m.group(1)))
    for m in re.finditer(r"\b[A-Z]{2,5}\b", text):
        cands.append((1, m.group(0)))
    for m in re.finditer(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3}\b", text):
        word = m.group(0)
        # 句首/括号首的大写只是拼写规矩，不是实体；但多词组合（"Fresno County"）仍然当实体
        pre = text[:m.start()].rstrip()
        if " " not in word and (not pre or pre.endswith((".", "?", "!", ":", ";", "(", "\n"))):
            continue
        # 同一个词在文中也以小写形式出现过 ⇒ 它是普通英文词，不是专有名词
        if re.search(r"\b" + re.escape(word.lower()) + r"\b", text):
            continue
        cands.append((2, word))

    out: list[str] = []
    seen: set[str] = set()
    for _pri, word in sorted(cands, key=lambda x: x[0]):      # sorted 稳定 ⇒ 同优先级保持原顺序
        word = re.sub(r"\s+", " ", word).strip()
        low = word.lower()
        if len(word) < 2 or low in seen or low in STOPWORDS or word in CAPS_BLOCK:
            continue
        if all(part.lower() in STOPWORDS for part in word.split()):
            continue
        seen.add(low)
        out.append(word)
        if len(out) >= max_terms:
            break
    return out


# 验证候选值时用的边界正则：真值里必须是**独立的**词。
# `%Max%` 的子串匹配会把 'Maxx Marshall' / 'maximum-likelihood' / 'Maximize' 全拉进来，
# 而我们要的是 `Max` 这个取值本身（错了就会把"人名 Max"和"函数 max"混在一起）。
_VERIFY_POOL = 40


def _word_match(value: str, term: str) -> bool:
    return re.search(r"(?<![0-9A-Za-z])" + re.escape(term) + r"(?![0-9A-Za-z])",
                     value, re.I) is not None


def reconnaissance(db_path: Path, question: str, evidence: str = "", schema_text: str = "",
                   max_terms: int = 8, samples: int = 3, max_columns: int = 10,
                   budget_s: float = 25.0) -> dict:
    """题干/evidence 里的字面量，究竟躺在哪张表哪一列？—— 当场查库。

    返回 `{text: 塞进 prompt 的块, terms, scanned, hit_columns, seconds, truncated}`。

    - `schema_text` 里**已经能看见**的词直接跳过：那部分信息模型本来就有，再查一遍只是烧时间。
    - 查不到的词要显式写成 "NOT FOUND"：这恰恰是最有用的信号 —— 库里根本没有这个写法，
      多半存的是代码/缩写（"Slovakian" → `'SVK'`），不要把它原样塞进 WHERE。
    - 每列先一条 `OR ... LIMIT 1` 探一次（无命中就短路，不会全表扫）；命中后才去拿计数与真值。
      因此总扫描次数与词数无关，只与列数相关。
    """
    terms = extract_terms(question, evidence, max_terms=max_terms)
    if schema_text:
        low = schema_text.lower()
        terms = [t for t in terms if t.lower() not in low]
    stats = {"terms": terms, "scanned": 0, "hit_columns": 0, "seconds": 0.0, "truncated": False}
    if not terms:
        return {**stats, "text": ""}

    t0 = time.time()
    pats = [f"%{t}%" for t in terms]
    con = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    lines: list[str] = []
    matched: set[str] = set()
    try:
        con.execute("PRAGMA query_only = ON")
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND substr(name, 1, 7) != 'sqlite_' ORDER BY name")]
        for table in tables:
            for _cid, col, ctype, _nn, _dflt, _pk in con.execute(f'PRAGMA table_info("{table}")'):
                if "BLOB" in (ctype or "").upper():
                    continue
                if time.time() - t0 > budget_s:
                    stats["truncated"] = True
                    break
                stats["scanned"] += 1
                q = '"' + col.replace('"', '""') + '"'
                where = " OR ".join(f"CAST({q} AS TEXT) LIKE ?" for _ in terms)
                try:
                    if not con.execute(f'SELECT 1 FROM "{table}" WHERE {where} LIMIT 1',
                                       pats).fetchone():
                        continue
                    per: list[str] = []
                    for term, pat in zip(terms, pats):
                        cand = [str(r[0]).replace("\n", " ") for r in con.execute(
                            f'SELECT DISTINCT {q} FROM "{table}" WHERE CAST({q} AS TEXT) '
                            f'LIKE ? LIMIT ?', (pat, _VERIFY_POOL))]
                        good = [v for v in cand if _word_match(v, term)]
                        if not good:           # 只是"包含该子串"（Maxx / maximum）⇒ 不算命中
                            continue
                        n, nd = con.execute(
                            f'SELECT COUNT(*), COUNT(DISTINCT {q}) FROM "{table}" '
                            f'WHERE CAST({q} AS TEXT) LIKE ?', (pat,)).fetchone()
                        approx = "~" if len(good) < len(cand) else ""
                        per.append(f'"{term}" [{approx}{n} rows, {approx}{nd} distinct] e.g. '
                                   + " | ".join(repr(v[:40]) for v in good[:samples]))
                        matched.add(term.lower())
                    if per:
                        stats["hit_columns"] += 1
                        lines.append(f"- {table}.{col}: " + "; ".join(per))
                except sqlite3.Error:
                    continue
            if stats["truncated"]:
                break
    finally:
        con.close()
    stats["seconds"] = round(time.time() - t0, 2)

    missing = [t for t in terms if t.lower() not in matched]
    if not lines and not missing:
        return {**stats, "text": ""}
    head = (
        "## Live value reconnaissance\n\n"
        "I just ran these lookups against this database (terms taken from the question and the "
        f"evidence; {stats['scanned']} columns searched in {stats['seconds']}s). Lookups already "
        "visible in the schema samples above are omitted. \"NOT FOUND\" means the literal does "
        "not occur anywhere in this database - do not put it verbatim in a WHERE clause.\n"
    )
    body = list(lines[:max_columns])
    if len(lines) > max_columns:
        body.append(f"- ... {len(lines) - max_columns} more columns also matched (omitted)")
    for term in missing:
        body.append(f'- "{term}": NOT FOUND in any column of this database.')
    if stats["truncated"]:
        body.append(f"- (search truncated after {budget_s:.0f}s; later tables were not covered)")
    return {**stats, "text": head + "\n" + "\n".join(body)}


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
               descriptions: str = "", recon: str = "") -> str:
    """user prompt = schema → 人工标注 → 题目/evidence → **实时侦察** → 指令。

    侦察放在最后紧贴指令：那是"我刚刚为你查过的"事实，离生成位置最近时最容易被用上。
    """
    parts = [f"Database: {db_id}", "", "## Schema", schema]
    if descriptions:
        parts += ["", "## Column meanings (human-annotated)", descriptions]
    parts += ["", "## Question", question.strip()]
    if evidence and evidence.strip():
        parts += ["", "## Evidence (external knowledge you must use)", evidence.strip()]
    if recon:
        parts += ["", recon]
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
