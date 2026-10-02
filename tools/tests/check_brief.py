# -*- coding: utf-8 -*-
"""第 57 轮：`brief` 推送机制的端到端守卫（原 P4「库档案整份送达」的替代品）。

背景：库档案（`.pi/skills/bird-sql/references/db/*.md`）已**全部删除** —— 它们只在 dev 的
11 个库上有内容，而隐藏 test 用另外 15 个库，命中率恒为 0。原 P4 套件证的是"档案每一行都送达"，
那件事本身已经不存在了；现在要证的是**相反方向**的东西：

  ① `brief --step N` 只推**带 push 标记**的片段（标题与内容都对得上）；
  ② ⭐ 投毒：往 `references/` 里塞一份**库专属**假档案（`db/POISON.md`）+ 一份无标记的
     杂项文件，`brief` 的输出里**一个字都不许出现**（证明它是按标记推送，不是扫目录）；
  ③ `brief <库名>` 必须 **rc=2**（第 57 轮起 brief 不接受库参数）；
  ④ 合法步骤的推送量有量级记录（放大过头会淹没模型）；
  ⑤ `conventions` 的输出里**不许出现任何档案路径**（机制已废，别在文案里留回声）。

用法：python tools/tests/check_brief.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / ".pi" / "skills" / "bird-sql" / "references"
TMP = Path(os.environ.get("BIRD_TEST_REFS", "D:/tmp/bird/brieftest"))
PY = os.environ.get("BIRD_PYTHON", sys.executable)

POISON_DIR = "db"
POISON_NAME = "POISON_DB_CARD.md"
POISON_MARK = "☆投毒库档案☆SENTINEL_9F3A"      # 出现在 db/ 假档案里
POISON2_MARK = "☆无标记杂项☆SENTINEL_5C21"     # 出现在 references/ 顶层、不带 push 标记的文件里

pass_n = 0
fail_n = 0
notes: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  ✅ {name}")
    else:
        fail_n += 1
        print(f"  ❌ {name} {str(detail)[:300]}")
    return bool(cond)


def run(*args: str, refs: Path | None = None) -> tuple[int, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if refs is not None:
        env["BIRD_REFS"] = str(refs)
    else:
        env.pop("BIRD_REFS", None)
    r = subprocess.run([PY, str(ROOT / "tools" / "bird.py"), "--dataset", "dev2025", *args],
                       cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def normal(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> int:  # noqa: C901
    print("── ① 每个合法步骤都推得出东西，且推的是那一段（标题/关键内容对得上）")
    EXPECT = [
        ("1", ("库结构五查", "不预写")),
        ("3.5", ("概念先定位", "少给列")),
        ("4", ("值层六问",)),
    ]
    for step, keys in EXPECT:
        rc, out = run("brief", "--step", step)
        check(f"brief --step {step} → rc=0", rc == 0, out[-160:])
        check(f"--step {step} 的片段含 {'/'.join(keys)}", all(k in out for k in keys), out[:200])
        notes.append(f"    step={step:4s} {len(out.splitlines()):4d} 行 / {len(out):5d} 字符")

    print("\n── ② 投毒：库专属档案 + 无标记文件，都不许进 `brief` 的输出")
    if TMP.exists():
        shutil.rmtree(TMP)
    shutil.copytree(REF, TMP)
    (TMP / POISON_DIR).mkdir(exist_ok=True)
    (TMP / POISON_DIR / POISON_NAME).write_text(
        f"# 投毒档案\n\n## 交题前必查\n\n1. {POISON_MARK}\n", encoding="utf-8")
    (TMP / "ZZZ_notes.md").write_text(f"# 杂项\n\n{POISON2_MARK}\n", encoding="utf-8")
    for step in ("1", "3.5", "4"):
        _, out = run("brief", "--step", step, refs=TMP)
        check(f"--step {step} 的输出里没有投毒档案内容", POISON_MARK not in out)
        check(f"--step {step} 的输出里没有无标记杂项文件", POISON2_MARK not in out)
    _, out = run("brief", refs=TMP)
    check("不带 --step 的全量推送里也没有投毒内容",
          POISON_MARK not in out and POISON2_MARK not in out)

    print("\n── ③ `brief <库名>` 必须 rc=2（第 57 轮起不接受库参数）")
    for argv in (("brief", "no_such_db"), ("brief", "financial")):
        rc, out = run(*argv)
        check(f"`{' '.join(argv)}` → rc=2", rc == 2, f"rc={rc} {out.splitlines()[0][:90] if out else ''}")

    print("\n── ④ 机制本身：references/ 里**没有任何库专属文件**（推送只认 push 标记）")
    check("references/db/ 不存在", not (REF / "db").exists())
    check("references/ 顶层之外的 .md 一个都没有",
          [f.name for f in REF.rglob("*.md") if f.parent != REF] == [])
    orphans = []
    for f in sorted(REF.glob("*.md")):
        # 先剥掉围栏/行内代码：casebook / maintaining 把 `<!-- push … /push -->` 当语法例子
        body = re.sub(r"```.*?```", "", f.read_text(encoding="utf-8"), flags=re.S)
        body = re.sub(r"`[^`\n]*`", "", body)
        n_open = len(re.findall(r"<!--\s*push\s+step=[0-9.]+\s*-->", body))
        n_close = len(re.findall(r"<!--\s*/push\s*-->", body))
        if n_open != n_close:
            orphans.append(f"{f.name}:{n_open}/{n_close}")
    check("push 标记成对（否则片段会漏推或串段）", not orphans, "，".join(orphans))
    pushed: dict[str, int] = {}
    for f in sorted(REF.glob("*.md")):
        body = re.sub(r"```.*?```", "", f.read_text(encoding="utf-8"), flags=re.S)
        body = re.sub(r"`[^`\n]*`", "", body)
        for m in re.finditer(r"<!--\s*push\s+step=([0-9.]+)\s*-->", body):
            pushed[m.group(1)] = pushed.get(m.group(1), 0) + 1
    check("至少 3 个步骤有可推片段（1 / 3.5 / 4 是工作流主干）",
          all(s in pushed for s in ("1", "3.5", "4")), f"steps={sorted(pushed)}")

    print("\n── ⑤ `conventions` 的输出里不许留档案机制的回声（'写回卡片' / 'db/*.md'）")
    rc, out = run("conventions", "--db", "california_schools", "--examples", "0")
    if rc == 2:                      # 该库没答案时是合法负结果，换个有答案的库
        rc, out = run("conventions", "--db", "debit_card_specializing", "--examples", "0")
    check("conventions 能跑（rc=0）", rc == 0, out[-160:])
    check("输出里没有 'write-card' / '卡片' 的回声",
          "write-card" not in out and "惯例卡片" not in out, out[-200:])
    check("输出里没有库档案路径", "references/db" not in out and "db/*.md" not in out)

    if notes:
        print("\n📏 推送量级（人工核对用，不是断言）")
        for n in notes:
            print(n)

    print(f"\n{'=' * 4} brief 推送机制 通过 {pass_n} / 失败 {fail_n} {'=' * 4}")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
