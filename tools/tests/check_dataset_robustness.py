#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T2 · 数据集健壮性：**题目字段缺失**与**金标自身缺陷**都不许把工具打崩或说错话。

来历（都是实测抓到的，不是假想）：
  · 官方 train 集（T2 的 `gen` 数据集）**没有 `difficulty` 字段** ⇒ 闸门 4 的列数下界
    直接 `KeyError: 'difficulty'` 崩掉（rc=1），答案交不上去。
  · 同一个库里有金标**用错列**（题干说 diamond-shaped *load*，金标查 `shape`）⇒ 金标返回空集；
    旧诊断把它说成「列数不同」，复盘时会把它当成自己的口径错。

本套件自建 fixture（BIRD_DATA_DIR / BIRD_WORK_DIR 指到临时目录），**不碰任何真实数据**。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = os.environ.get("BIRD_PYTHON") or sys.executable
PASSED = FAILED = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


def core_items() -> str:
    """从 checklist.md 现场解析核心条目号 —— 不在测试里手抄（抄了必然漂移）。"""
    text = (ROOT / ".pi/skills/bird-sql/references/checklist.md").read_text(encoding="utf-8")
    items = []
    for line in text.splitlines():
        if "<!-- core -->" in line:
            m = re.match(r"- \[ \] \*\*([0-9]+[a-z]?)\.", line)
            if m:
                items.append(m.group(1))
    return ",".join(items)


QUESTIONS = [
    {   # 没有 difficulty 字段（模拟官方 train 集）
        "question_id": 900,
        "db_id": "demo",
        "question": "How many customers are there?",
        "evidence": "customers refers to the customers table",
        "SQL": "SELECT COUNT(*) FROM customers",
    },
    {   # 金标用错列 ⇒ 结果为空（模拟实测的 trains idx 15）
        "question_id": 901,
        "db_id": "demo",
        "question": "Which customer pays in USD?",
        "evidence": "USD is a value of Currency",
        "SQL": "SELECT CustomerID FROM customers WHERE Currency = 'USD'",
    },
]
GOLD_LINES = [
    "SELECT COUNT(*) FROM customers\t----- bird -----\tdemo",
    "SELECT CustomerID FROM customers WHERE Currency = 'USD'\t----- bird -----\tdemo",
]


def build_fixture(root: pathlib.Path) -> None:
    md = root / "data" / "MINIDEV"
    (md / "dev_databases" / "demo").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(md / "dev_databases" / "demo" / "demo.sqlite")
    con.execute("CREATE TABLE customers (CustomerID INTEGER, Currency TEXT)")
    con.executemany("INSERT INTO customers VALUES (?,?)",
                    [(1, "EUR"), (2, "CZK"), (3, "EUR")])
    con.commit()
    con.close()
    (md / "mini_dev_sqlite.json").write_text(json.dumps(QUESTIONS, ensure_ascii=False), encoding="utf-8")
    (md / "mini_dev_sqlite_gold.sql").write_text("\n".join(GOLD_LINES) + "\n", encoding="utf-8")
    (root / "work").mkdir(parents=True, exist_ok=True)


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="bird_nofield_"))
    build_fixture(tmp)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "BIRD_DATA_DIR": str(tmp / "data"), "BIRD_WORK_DIR": str(tmp / "work")}

    def run(*argv: str) -> tuple[int, str]:
        r = subprocess.run([PY, "tools/bird.py", *argv], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=600)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()

    print("── T2 数据集健壮性（无 difficulty 字段 / 金标自身为空）")
    rc, out = run("attrs", "0")
    check("题目没有 difficulty 字段时 `attrs` 不崩（rc=0）", rc == 0, out.splitlines()[-1][:90] if out else "")
    check("`attrs` 明说这个数据集没有难度字段（不是静默降级）", "没有 difficulty" in out, out[-160:])

    #   ⭐ T1：库存在但**零答案**时 —— 必须给冷启动口径，不能回一句「没有可统计的题」
    rc, out = run("conventions", "--db", "demo")
    check("零答案库的 conventions 失败关闭（rc=2）", rc == 2, f"rc={rc}")
    check("…并指向冷启动五查（不是「这库没有惯例」）",
          "冷启动五查" in out and "没有任何已提交答案" in out, out[-160:])

    rc, _ = run("run", "demo", "SELECT COUNT(*) FROM customers", "--for", "0,1")
    check("探针可记录（为下面的 answer 做准备）", rc == 0)
    rc, out = run("answer", "0", "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
                  "--checks", core_items(), "--attrs", "How many customers are there")
    check("无 difficulty 时闸门 4 不崩、正常记录（rc=0）", rc == 0, out.splitlines()[-1][:90] if out else "")

    rc, out = run("answer", "1", "/* shape: 1x1 */ SELECT CustomerID FROM customers WHERE Currency='EUR' LIMIT 1",
                  "--checks", core_items(), "--attrs", "Which customer pays in USD")
    check("第二题可提交（预测非空、金标为空）", rc == 0, out.splitlines()[-1][:90] if out else "")

    #   ⭐ T1：n 太少时不许写卡片（1~2 道题的"惯例"是噪声，写进档案会被当成事实读）
    rc, out = run("conventions", "--db", "demo", "--write-card")
    check("答案只有 1 道时拒绝写惯例卡片（n<3 下限）", "跳过写卡片" in out, out[-160:])
    check("那条跳过不是靠崩掉实现（rc=0）", rc == 0, f"rc={rc}")

    rc, out = run("score", "--list-wrong", "5")
    check("score 能跑完（rc=0）", rc == 0, out.splitlines()[-1][:90] if out else "")
    check("金标为空时诊断指向**金标缺陷**，而不是说成「列数/行数不同」",
          "金标结果为空" in out and "不该算在你的口径上" in out, out[-240:])
    check("金标为空的那题别被算成「值不对」之类的误导理由",
          "列数不同" not in out and "行数不同" not in out, out[-240:])

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n════ 通过 {PASSED} / 失败 {FAILED} ════")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
