# -*- coding: utf-8 -*-
"""生成一个极小的 fixture 数据集，供 extension 冒烟测试使用（不碰真实数据）。

产物（默认写到 D:/tmp/bird/fixture，可用 --out 改）：
    MINIDEV/mini_dev_sqlite.json            2 道题（db_id = demo）
    MINIDEV/mini_dev_sqlite_gold.sql        对应金标
    MINIDEV/dev_databases/demo/demo.sqlite  两张表：customers(3 行) / yearmonth(3 行)
    work/answers.json                       预置两条作答（模拟“已答过”）

为什么要有它：extension/后端的闸门测试必须能**反复跑且不污染真实作答文件**。
用法：
    python tools/tests/make_fixture.py
    node tools/tests/extension_smoke.cjs
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

QUESTIONS = [
    {
        "question_id": 1471,
        "db_id": "demo",
        "question": "What is the ratio of customers who pay in EUR against customers who pay in CZK?",
        "evidence": "ratio = count(Currency='EUR') / count(Currency='CZK').",
        "SQL": "SELECT CAST(SUM(IIF(Currency='EUR',1,0)) AS FLOAT)/SUM(IIF(Currency='CZK',1,0)) AS ratio FROM customers",
        "difficulty": "simple",
    },
    {
        "question_id": 1472,
        "db_id": "demo",
        "question": "In 2012, who had the least consumption in LAM?",
        "evidence": "LAM refers to Segment = 'LAM'; year 2012 is the first 4 chars of Date.",
        "SQL": (
            "SELECT T1.CustomerID FROM customers T1 JOIN yearmonth T2 ON T1.CustomerID=T2.CustomerID "
            "WHERE T1.Segment='LAM' AND SUBSTR(T2.Date,1,4)='2012' ORDER BY T2.Consumption ASC LIMIT 1"
        ),
        "difficulty": "moderate",
    },
    {
        "question_id": 1473,
        "db_id": "demo",
        "question": "How many customers pay in EUR?",
        "evidence": "EUR is a value of Currency.",
        "SQL": "SELECT COUNT(*) FROM customers WHERE Currency='EUR'",
        "difficulty": "simple",
    },
]

CUSTOMERS = [(1, "LAM", "EUR"), (2, "SME", "CZK"), (3, "LAM", "EUR")]
YEARMONTH = [(1, "201201", 100.0), (1, "201202", 50.0), (2, "201201", 20.0)]


def main() -> None:
    ap = argparse.ArgumentParser(description="生成 extension 冒烟测试用的小 fixture 数据集")
    ap.add_argument("--out", default="D:/tmp/bird/fixture", help="fixture 根目录")
    args = ap.parse_args()

    root = Path(args.out)
    mini = root / "MINIDEV"
    db_dir = mini / "dev_databases" / "demo"
    work = root / "work"
    db_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    (mini / "mini_dev_sqlite.json").write_text(
        json.dumps(QUESTIONS, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (mini / "mini_dev_sqlite_gold.sql").write_text(
        "\n".join(f"{q['SQL']}\tdemo" for q in QUESTIONS) + "\n", encoding="utf-8"
    )

    db = db_dir / "demo.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE customers (CustomerID INTEGER, Segment TEXT, Currency TEXT)")
    con.execute("CREATE TABLE yearmonth (CustomerID INTEGER, Date TEXT, Consumption REAL)")
    con.executemany("INSERT INTO customers VALUES (?,?,?)", CUSTOMERS)
    con.executemany("INSERT INTO yearmonth VALUES (?,?,?)", YEARMONTH)
    con.commit()
    con.close()

    (work / "answers.json").write_text(
        json.dumps(
            {
                "0": f"{QUESTIONS[0]['SQL']}\t----- bird -----\tdemo",
                "1": "SELECT 999 AS CustomerID\t----- bird -----\tdemo",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (work / "probe_log.jsonl").unlink(missing_ok=True)

    print(f"✓ fixture 已生成 -> {root}")
    for f in ["MINIDEV/mini_dev_sqlite.json", "MINIDEV/mini_dev_sqlite_gold.sql",
              "MINIDEV/dev_databases/demo/demo.sqlite", "work/answers.json"]:
        print(f"    {f}")


if __name__ == "__main__":
    main()
