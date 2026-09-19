# -*- coding: utf-8 -*-
"""P19 · 类③「失败开放」守卫：给每个接受「名字 / 编号」的入口喂一个**不存在的值**。

为什么单独立一个套件：这类缺陷的形态是"查不到就安静地返回空"，而空结果**读起来像正常**：
  · `brief --step 3`   → “没有带 push 标记的片段”（真话，但像"这一步没东西要读"）
  · `brief <打错的库>`  → “还没有 db/x.md 档案”（把它当成"新库还没建档"，照样退出 0）
  · `list --db <打错的库>` → “筛选后 0 题”（像"这个库已经做完了"）
所以判据不是"有没有报错文案"，而是**退出码**：`fail()` 一律 `rc=2`。
（`rc=1` 是 python 自己崩了 —— 语法错误/异常，也算不合格，本测试同样不认。）

⭐ 唯一的白名单：**合法的负结果**。
  · `find <库> <查不到的词>` —— 查不到就是查不到，是有效信息 ⇒ rc=0
  · `list --difficulty <没有该难度的库>` —— 筛选为空，合法 ⇒ rc=0
白名单必须显式列出并附理由；新增入口忘了 fail-closed 就会在这里变红。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = os.environ.get("BIRD_PYTHON") or sys.executable
DATASET = os.environ.get("BIRD_DATASET", "dev2025")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

PASSED = FAILED = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


def run(argv: list[str]) -> tuple[int, str]:
    r = subprocess.run([PY, "tools/bird.py", "--dataset", DATASET, *argv], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=ENV, timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


# 不存在的值 ⇒ 必须 rc=2（fail-closed），且文案要指出"这个东西不存在"
MUST_FAIL = [
    ("brief --step 3（该步骤没有内容）", ["brief", "--step", "3"], "没有 step=3"),
    ("brief --step 9（从未有过）", ["brief", "--step", "9"], "没有 step=9"),
    ("brief <不存在的库>", ["brief", "no_such_db"], "既不是本地库"),
    ("brief <存在的库> --step 9", ["brief", "financial", "--step", "9"], "没有 step=9"),
    ("tables <不存在的库>", ["tables", "no_such_db"], "不存在"),
    ("schema <存在的库> --table <不存在的表>", ["schema", "financial", "--table", "no_such_table"], "不存在"),
    ("desc <不存在的库>", ["desc", "no_such_db"], "不存在"),
    ("conventions --db <不存在的库>", ["conventions", "--db", "no_such_db"], "不存在"),
    ("cols <不存在的库>", ["cols", "no_such_db", "type"], "不存在"),
    ("find <不存在的库>", ["find", "no_such_db", "foo"], "不存在"),
    ("audit --db <不存在的库>", ["audit", "--db", "no_such_db"], "不存在"),
    ("attrs <越界 idx>", ["attrs", "999999"], "越界"),
    ("question <越界 idx>", ["question", "999999"], "越界"),
    ("list --db <不存在的库>", ["list", "--db", "no_such_db"], "不存在"),
    ("run <不存在的库>", ["run", "no_such_db", "SELECT 1"], "不存在"),
    ("answer <越界 idx>", ["answer", "999999", "/* shape: 1x1 */ SELECT 1"], "越界"),
]

# 合法的负结果（rc=0）—— 附理由，防"把白名单当万能借口"
MAY_BE_EMPTY = [
    ("find <存在的库> 查不到的词（查不到就是有效信息）",
     ["find", "financial", "zzz_no_such_word_zzz"], "未命中"),
]


def main() -> int:
    print("── 类③ 失败开放：喂不存在的键，必须 rc=2（不是 rc=0 的“安静空结果”）")
    for label, argv, hint in MUST_FAIL:
        rc, out = run(argv)
        first = out.splitlines()[0] if out else ""
        check(f"{label} → rc=2 且指出原因", rc == 2 and hint in out,
              f"rc={rc} out={first[:90]}")
    print("\n── 白名单：合法的负结果不许被强行报错")
    for label, argv, hint in MAY_BE_EMPTY:
        rc, out = run(argv)
        check(f"{label} → rc=0", rc == 0, f"rc={rc} out={out.splitlines()[0][:90] if out else ''}")

    print(f"\n{'=' * 4} 失败关闭 通过 {PASSED} / 失败 {FAILED} {'=' * 4}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
