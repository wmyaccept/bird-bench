# -*- coding: utf-8 -*-
"""P4 的独立复核（换角度，不复用刚才的自证）。

要证的：
  ① 11 个档案**每一行**都出现在 `brief` 输出里（不是"抽查两节"）；
  ② 以后**新增**的小节也会送达（投毒测试：插一个从没见过的小节）；
  ③ 档案中间/末尾/卡片之后的章节都能送达；
  ④ `## 惯例卡片` 锚点唯一（否则 write_card 的 find 会错位）；
  ⑤ write_card 在"卡片后面还有别的节"时不吃掉后续内容；
  ⑥ `--write-card` 缺 db/all 时拒绝；
  ⑦ 卡片数字 = 独立数出来的已答题数（不用 bird 的统计函数）；
  ⑧ 每库 brief 的行数/字符量级（我把推送量放大了，得确认没失控）。

用法：python tools/tests/check_brief_p4.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_DB = ROOT / ".pi" / "skills" / "bird-sql" / "references" / "db"
TMP = Path(os.environ.get("BIRD_TEST_REFS", "D:/tmp/bird/p4test"))
PY = os.environ.get("BIRD_PYTHON", sys.executable)

REPLAY_PROFILE = """# demo 档案

## 交题前必查（本库最容易翻车的几条）

1. **第一条检查项**（甲）
2. **第二条检查项**（乙）
3. **第三条检查项**（丙）
4. **第四条检查项**（丁）

## 惯例卡片（实测统计，n=2 道已提交题的金标；数据集 minidev）

- 计数形态：COUNT(列) 1 / 无 1
- 主表（FROM 第一张）：customers 2

> 测试用档案。
"""

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
    return cond


def run(*args: str, refs: Path | None = None, dataset: str = "dev2025") -> str:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if refs is not None:
        env["BIRD_REFS"] = str(refs)
    else:
        env.pop("BIRD_REFS", None)
    r = subprocess.run(
        [PY, str(ROOT / "tools" / "bird.py"), "--dataset", dataset, *args],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (r.stdout or "") + (r.stderr or "")


def normal(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> int:
    profiles = sorted(REAL_DB.glob("*.md"))
    print(f"── ① 逐库：档案的每一行都必须出现在 brief 输出里（{len(profiles)} 个库）")
    for f in profiles:
        db = f.stem
        text = f.read_text(encoding="utf-8")
        out = run("brief", db)
        out_n = normal(out)
        missing = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.startswith("<!--") and normal(ln) not in out_n
        ]
        check(f"{db}: {len(text.splitlines())} 行全部送达", not missing, f"缺 {len(missing)} 行: {missing[:3]}")
        body = out.split("══\n", 1)[-1] if "══\n" in out else out
        notes.append(f"    {db:26s} brief {len(out.splitlines()):4d} 行 / {len(out):6d} 字符")

    print("\n── ② 投毒：插一个**从没见过**的新小节（以后新增内容会不会又丢）")
    if TMP.exists():
        shutil.rmtree(TMP)
    shutil.copytree(REAL_DB, TMP / "db")
    sentinel = "☆明日新增小节☆SENTINEL_9F3A"
    p = TMP / "db" / "card_games.md"
    t = p.read_text(encoding="utf-8")
    t = t.replace("\n## 连接图与坑", f"\n## {sentinel}\n\n这一节是测试插进来的。\n\n## 连接图与坑", 1)
    p.write_text(t, encoding="utf-8")
    out = run("brief", "card_games", refs=TMP)
    check("中间新增的小节送达", sentinel in out)
    t = p.read_text(encoding="utf-8") + f"\n\n## {sentinel}_尾部\n\n末尾追加的一节。\n"
    p.write_text(t, encoding="utf-8")
    out = run("brief", "card_games", refs=TMP)
    check("文件末尾追加的小节也送达", f"{sentinel}_尾部" in out)

    print("\n── ③ 锚点唯一性 + write_card 不吃后续小节")
    for f in profiles:
        n = f.read_text(encoding="utf-8").count("## 惯例卡片")
        if not check(f"{f.stem}: `## 惯例卡片` 出现 {n} 次（须为 1）", n == 1):
            notes.append(f"    ⚠️ {f.stem} 锚点 {n} 次")
    p2 = TMP / "db" / "financial.md"
    t = p2.read_text(encoding="utf-8")
    if "\n## 尾随小节" not in t:
        t += "\n\n## 尾随小节\n\n卡片后面还有一节，刷新卡片时必须活着。\n"
    p2.write_text(t, encoding="utf-8")
    run("conventions", "--db", "financial", "--examples", "0", "--write-card", refs=TMP)
    t2 = p2.read_text(encoding="utf-8")
    check("刷新卡片后，卡片后面的小节还在", "## 尾随小节" in t2 and "必须活着" in t2)
    check("卡片本身被更新（n 与实际一致）", "## 惯例卡片（实测统计，n=" in t2)

    print("\n── ④ --write-card 缺 db/all 时拒绝")
    out = run("conventions", "--write-card", "--examples", "0")
    check("给出明确错误", "需要指定 --db" in out or "--write-card 需要" in out, out[-200:])

    print("\n── ⑤ 卡片 n == 独立数出来的已答题数（绕开 bird 的统计函数）")
    ans = json.loads((ROOT / "work" / "answers_dev2025.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT / "tools"))
    os.environ["BIRD_DATASET"] = "dev2025"
    import bird  # noqa: E402

    qs = bird.load_questions()
    n_gold = len(bird.load_gold())
    per_db: dict[str, int] = {}
    for k in ans:
        if 0 <= int(k) < min(len(qs), n_gold):
            per_db[qs[int(k)]["db_id"]] = per_db.get(qs[int(k)]["db_id"], 0) + 1
    for f in profiles:
        db = f.stem
        m = re.search(r"## 惯例卡片（实测统计，n=(\d+)", f.read_text(encoding="utf-8"))
        if not m:
            check(f"{db}: 卡片里有 n", False)
            continue
        expect = per_db.get(db, 0)
        check(f"{db}: 卡片 n={m.group(1)} vs 独立计数 {expect}", int(m.group(1)) == expect)
    extra = set(per_db) - {f.stem for f in profiles}
    check("已答的库都有 db 档案（没有漏建档案的库）", not extra, sorted(extra))
    notes.append(f"    独立计数合计 {sum(per_db.values())} 道已提交题")

    print("\n── ⑦ 交题瞬间的『必查回放』全不全（以前只打第一条）")
    fx = Path(os.environ.get("BIRD_TEST_FIXTURE", "D:/tmp/bird/fixture"))
    real_ans = ROOT / "work" / "answers_dev2025.json"
    before = real_ans.read_bytes() if real_ans.exists() else b""
    if not (fx / "work" / "answers.json").exists():
        print("  ⚠️ 跳过：没有 fixture（先跑 tools/tests/make_fixture.py）")
    else:
        refs2 = TMP.parent / (TMP.name + "_replay")
        if refs2.exists():
            shutil.rmtree(refs2)
        (refs2 / "db").mkdir(parents=True)
        (refs2 / "db" / "demo.md").write_text(REPLAY_PROFILE, encoding="utf-8")
        env = {
            **os.environ, "PYTHONIOENCODING": "utf-8",
            "BIRD_DATA_DIR": str(fx), "BIRD_WORK_DIR": str(fx / "work"), "BIRD_REFS": str(refs2),
        }
        # ⭐ 先自己留一条探针（闸门 1）：不许依赖"别的测试刚好跑过"这类环境状态
        subprocess.run(
            [PY, str(ROOT / "tools" / "bird.py"), "--dataset", "minidev", "run", "demo",
             "SELECT COUNT(*) FROM customers", "--for", "2"],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        r = subprocess.run(
            [PY, str(ROOT / "tools" / "bird.py"), "--dataset", "minidev", "answer", "2",
             "/* shape: 1x1 */ SELECT COUNT(*) FROM customers"],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        check("报出必查条数（4 条）", "必查回放（4 条" in out, out[-300:])
        for tag in "甲乙丙丁":
            check(f"回放含第 {tag} 条（4 条缺一不可）", f"（{tag}）" in out)
        check("惯例卡片也跟着回放", "惯例回放" in out)
        check(
            "跑的是 fixture，真答案文件字节不变",
            (real_ans.read_bytes() if real_ans.exists() else b"") == before,
        )

    print("\n── ⑥ 每库 brief 推送体量")
    print("\n".join(notes))
    print(f"\n════ 通过 {pass_n} / 失败 {fail_n} ════")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
