# -*- coding: utf-8 -*-
"""验证 `conventions --write-card`（P2 的验收）。

要证的三件事：
  ① 卡片确实能被**工具**刷新（不再依赖仓库外的一次性脚本）；
  ② 卡片数字与工具输出**同源**（n 一致）—— 消灭“工具一套数、卡片另一套数”；
  ③ 写入可被 `BIRD_REFS` 重定向（所以本测试能跑在临时目录里，**不动真档案**），且幂等。

用法：python tools/tests/check_write_card.py
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_DB = ROOT / ".pi" / "skills" / "bird-sql" / "references" / "db"
TMP_REFS = Path(os.environ.get("BIRD_TEST_REFS", "D:/tmp/bird/cardtest"))
PY = os.environ.get("BIRD_PYTHON", sys.executable)
DB = "financial"

pass_n = 0
fail_n = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  ✅ {name}")
    else:
        fail_n += 1
        print(f"  ❌ {name} {detail}")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def run(*args: str, refs: Path | None = TMP_REFS) -> str:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if refs is not None:
        env["BIRD_REFS"] = str(refs)
    else:
        env.pop("BIRD_REFS", None)
    r = subprocess.run(
        [PY, str(ROOT / "tools" / "bird.py"), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    if not REAL_DB.exists():
        print(f"找不到真档案目录 {REAL_DB}")
        return 2

    if TMP_REFS.exists():
        shutil.rmtree(TMP_REFS)
    TMP_REFS.mkdir(parents=True)
    shutil.copytree(REAL_DB, TMP_REFS / "db")

    real_card = REAL_DB / f"{DB}.md"
    before = md5(real_card)

    print("── ① 工具能刷新卡片（写进 BIRD_REFS 指向的目录）")
    dirty = TMP_REFS / "db" / f"{DB}.md"
    dirty.write_text(
        re.sub(r"n=\d+", "n=999", dirty.read_text(encoding="utf-8")), encoding="utf-8"
    )
    check("先把副本弄脏（n=999）", "n=999" in dirty.read_text(encoding="utf-8"))

    out = run("--dataset", "dev2025", "conventions", "--db", DB, "--examples", "0", "--write-card")
    check("命令跑通并报出刷新路径", "惯例卡片已刷新" in out, out[-300:])
    card_text = dirty.read_text(encoding="utf-8")
    check("副本里的脏数字被修好", "n=999" not in card_text)
    check("真档案 md5 不变（写入被 BIRD_REFS 重定向）", md5(real_card) == before)

    print("\n── ② 卡片数字 = 工具输出（同源，不再两套数）")
    m_tool = re.search(r"###\s+\S+\s+\(n=(\d+)", out)
    m_card = re.search(r"## 惯例卡片（实测统计，n=(\d+)", card_text)
    check("工具输出里有 n", bool(m_tool), out[:200])
    check("卡片里有 n", bool(m_card))
    if m_tool and m_card:
        check(f"两边 n 相同（{m_tool.group(1)}）", m_tool.group(1) == m_card.group(1))

    print("\n── ③ 卡片包含固定字段与刷新指路")
    for field in ["计数形态", "主表（FROM 第一张）", "SELECT DISTINCT", "输出列数分布", "JOIN 数分布"]:
        check(f"字段 {field}", field in card_text)
    check("写明刷新命令（防止手改数字）", "write_card=true" in card_text)
    check("写明数据集（口径可追溯）", re.search(r"数据集 (minidev|dev|dev2025)", card_text) is not None)

    print("\n── ④ 幂等：再刷一次，字节完全相同")
    snap = dirty.read_bytes()
    run("--dataset", "dev2025", "conventions", "--db", DB, "--examples", "0", "--write-card")
    check("内容零变化", dirty.read_bytes() == snap)

    print("\n── ⑤ 没有档案时报错清楚（而不是静默写失败）")
    missing = run(
        "--dataset", "dev2025", "conventions", "--db", DB, "--write-card", refs=TMP_REFS / "empty"
    )
    check("给出『没有库档案』的提示", "档案" in missing, missing[-200:])

    print(f"\n════ 通过 {pass_n} / 失败 {fail_n} ════")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
