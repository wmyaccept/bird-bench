# -*- coding: utf-8 -*-
"""第 57 轮：新的类级不变式 —— **`references/` 是只读知识库，且不含任何库专属知识**。

原来的「惯例卡片」套件证的是"卡片可刷新且与工具同源"。第 57 轮把卡片机制整体废除
（库知识不预写：dev 的 11 份档案在隐藏 test 库上命中率恒为 0），那个套件随之失去对象。
本套件接替它，并把它升级成**不变式**（不是某个功能的行为）：

  ① **静态**：任何会被执行的源码（py / ts / cjs / js）里，不许出现"写 `references/`"的语句；
  ② **动态**：跑一串真实工具命令后，整棵 `references/` 树的（文件名 + 内容哈希）**逐字节不变**；
  ③ **结构**：`references/db/` 不存在；`references/` 顶层之外没有 `.md`；
  ④ **打包器**：`references/db/` 一旦被塞回文件，`make_submission.py` 必须**拒绝打包**（fail-closed），
     且拒绝信息要点名那个文件（不是一句"打包失败"）；
  ⑤ `MANIFEST` 里不许有 `prompt/db`（库档案不许进提交包）。

用法：python tools/tests/check_refs_readonly.py
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
REF = ROOT / ".pi" / "skills" / "bird-sql" / "references"
PY = os.environ.get("BIRD_PYTHON", sys.executable)

pass_n = 0
fail_n = 0


def check(name: str, cond: bool, detail: str = "") -> bool:
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  ✅ {name}")
    else:
        fail_n += 1
        print(f"  ❌ {name} {str(detail)[:300]}")
    return bool(cond)


def tree_hash(root: Path) -> dict[str, str]:
    """把整棵树的 (相对路径 -> 内容 sha256) 摊平，用来证明"一个字都没变"。"""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def run(*args: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([PY, "tools/bird.py", "--dataset", "dev2025", *args], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


#   只扫**会被执行的**源码；.md 是给人看的，里面提到 `references/db/…` 是正当引用（如本文件的说明）。
#   `tools/tests/` 单独处理：守卫脚本**必须**把这个危险写法写成字面量（正则/探针样本），
#   把那目录整个排掉会留缺口 ⇒ 改成“数量守恒”：那里命中它的文件数必须是已知的 2 个，
#   多出一个（真的有人写了写 references 的测试）就变红。
SRC_GLOBS = ("**/*.py", "**/*.ts", "**/*.cjs", "**/*.js")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pi/skills", "data"}
TESTS_ALLOWED = 2          # check_docs.py（守卫里的正则）+ check_refs_readonly.py（本文件的探针样本）
#   允许出现 `references/` 字样的两条正当用途：读它 / 拒绝它。除此之外的写法都要人来审。
WRITE_PAT = re.compile(
    r"(REFS|REF_DIR|refs_dir|references)"
    r"[^\n]{0,80}?"
    r"(write_text|write_bytes|open\([^)]*['\"][wa]|\.mkdir|shutil\.(copy|move|rmtree)|"
    r"unlink|os\.remove|rmtree)",
    re.I,
)


def main() -> int:  # noqa: C901
    print("── ① 静态：源码里不许有「写 references/」的语句")
    hits = []
    test_hits = []
    for pat in SRC_GLOBS:
        for p in ROOT.glob(pat):
            rel = p.relative_to(ROOT).as_posix()
            if any(rel.startswith(d) or f"/{d}/" in rel for d in SKIP_DIRS):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            found = [(text[:m.start()].count("\n") + 1, m.group(0)[:70].replace(chr(10), " "))
                     for m in WRITE_PAT.finditer(text)]
            if not found:
                continue
            if rel.startswith("tools/tests/"):
                test_hits.append(rel)
            else:
                hits += [f"{rel}:{ln}: {snip}" for ln, snip in found]
    check("没有**产品源码**会写 references/（知识库只读）", not hits, " ｜ ".join(hits[:4]))
    check(f"写 references/ 的守卫文件数守恒（{TESTS_ALLOWED} 个：守卫正则 + 本文件探针）",
          len(test_hits) == TESTS_ALLOWED, f"实际 {len(test_hits)}：{test_hits}")
    #   反向断言：这条正则在"真去写"的样本上必须命中（否则整条守卫是空转的）
    probe = 'REFS = Path("x")\n(REFS / "db").mkdir(exist_ok=True)\n'
    check("（元）该正则在“真去写 references/”的样本上会命中（守卫不是空转）",
          bool(WRITE_PAT.search(probe)))

    print("\n── ② 结构：没有库专属文件（库知识不预写）")
    check("references/db/ 不存在", not (REF / "db").exists())
    check("references/ 顶层之外没有任何 .md",
          [f.name for f in REF.rglob("*.md") if f.parent != REF] == [])
    names = sorted(p.stem for p in REF.glob("*.md"))
    check(f"references/ 只剩通用知识文件（{len(names)} 份）", len(names) >= 8, str(names))
    db_ids = ["california_schools", "card_games", "codebase_community", "debit_card_specializing",
              "european_football_2", "financial", "formula_1", "student_club", "superhero",
              "thrombosis_prediction", "toxicology"]
    check("文件名里没有任何库 id（不许再长出库专属文件）",
          not [n for n in names if n in db_ids], str(names))

    print("\n── ③ 动态：跑一串真实命令后，整棵 references/ 逐字节不变")
    before = tree_hash(REF)
    run("brief")
    run("brief", "--step", "4")
    run("conventions", "--db", "debit_card_specializing", "--examples", "0")
    run("cols", "debit_card_specializing", "type")
    run("find", "debit_card_specializing", "Slovakian")
    after = tree_hash(REF)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    check(f"references/ 无新增/删除/修改（{len(after)} 个文件）",
          not (added or removed or changed),
          f"新增{added[:2]} 删除{removed[:2]} 改{changed[:2]}")

    print("\n── ④ 打包器：库档案一旦被塞回，必须拒绝打包并点名文件")
    poison = REF / "db" / "POISON_STRAY.md"
    stray_dir_made = not (REF / "db").exists()
    try:
        poison.parent.mkdir(parents=True, exist_ok=True)
        poison.write_text("# 投毒：库档案不该存在\n", encoding="utf-8")
        r = subprocess.run([PY, "tools/make_submission.py", "--dry-run"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=300,
                           **({} if os.name == "nt" else {}))
        out = (r.stdout or "") + (r.stderr or "")
        check("references/db/ 里有文件时，打包器拒绝（非 0 退出）", r.returncode != 0,
              f"rc={r.returncode} {out[-160:]}")
        check("拒绝信息点名了那份文件（不是一句“打包失败”）",
              "POISON_STRAY.md" in out or "库专属档案" in out, out[-200:])
    finally:
        if poison.exists():
            poison.unlink()
        if stray_dir_made and (REF / "db").exists():
            (REF / "db").rmdir()
        check("投毒已清理干净（references/db/ 不存在）", not (REF / "db").exists())

    print("\n── ⑤ MANIFEST 里没有库专属档案（prompt/ 不许有子目录）")
    import importlib.util as ilu
    sp = ilu.spec_from_file_location("_mk_refs", ROOT / "tools" / "make_submission.py")
    mk = ilu.module_from_spec(sp)
    sys.modules["_mk_refs"] = mk
    sp.loader.exec_module(mk)
    dsts = [d for d, _s in mk.MANIFEST]
    check("打包清单里没有 prompt/db/*", not [d for d in dsts if d.startswith("prompt/db")],
          str([d for d in dsts if "db" in d]))
    check("prompt/ 只装通用规则（traps/shapes 那一档）",
          all(not d.startswith("prompt/db") for d in dsts))

    print(f"\n{'=' * 4} references 只读且无库知识 通过 {pass_n} / 失败 {fail_n} {'=' * 4}")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
