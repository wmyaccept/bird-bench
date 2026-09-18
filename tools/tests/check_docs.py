# -*- coding: utf-8 -*-
"""文档一致性守卫（把"会漂移的文档"变成机器检查）。

对应本轮修的三个缺陷，全部做成**可复现的断言**，而不是"我这次记得改了"：

P1 条数不符     → checklist 标题里若写了条数，必须等于实际 `- [ ]` 个数
P6 手抄数字过期 → 常驻上下文的 SKILL.md 不许出现"实测统计型"数字（N/M、N 道）
P9 文档与代码相反 → AGENTS.md 不许再写"工具层固定用 minidev / extension 里写死了"
P7 死链（半自动）→ SKILL.md / db/*.md 里的 references 链接必须存在；
                    casebook 是历史账本，只列清单不判失败（见待办 P7）

用法：python tools/tests/check_docs.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".pi" / "skills" / "bird-sql"
REF = SKILL / "references"
AGENTS = ROOT / "AGENTS.md"

pass_n = 0
fail_n = 0
warn: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  ✅ {name}")
    else:
        fail_n += 1
        print(f"  ❌ {name} {str(detail)[:400]}")


def txt(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def main() -> int:
    print("── P1 checklist 条数自洽")
    cl = txt(REF / "checklist.md")
    actual = len(re.findall(r"^\s*- \[ \]", cl, re.M))
    head = cl.splitlines()[0]
    m = re.search(r"(\d+)\s*条", head)
    check(
        f"标题里的条数（若有）== 实际 {actual} 个勾选框",
        m is None or int(m.group(1)) == actual,
        f"标题写「{m.group(1)} 条」但实际 {actual} 个" if m else "",
    )
    check("标题不再写死条数（推荐形态）", m is None, f"仍在写死：{head}")

    live_docs = [AGENTS, SKILL / "SKILL.md", *sorted(REF.glob("*.md"))]
    bird_src = txt(ROOT / "tools" / "bird.py")
    stale = []
    for f in live_docs:
        if f.name == "casebook.md":       # 历史账本，允许出现"当时那 12 条"这类叙述
            continue
        for i, ln in enumerate(txt(f).splitlines(), 1):
            if re.search(r"\d+\s*条必勾|固定\s*\d+\s*条", ln):
                stale.append(f"{f.name}:{i}: {ln.strip()[:80]}")
    check("现役文档里没有写死的 checklist 条数", not stale, " ｜ ".join(stale))

    print("\n── P6 常驻上下文里不许有手抄的实测数字")
    skill = txt(SKILL / "SKILL.md")
    bad = []
    for i, ln in enumerate(skill.splitlines(), 1):
        if ln.lstrip().startswith("|") and "bird" in ln and "/" in ln:
            continue  # 工具映射表里可能合法出现路径
        for pat in (r"\d+/\d+\s*(道|\b)", r"\d{3,}\s*道"):
            if re.search(pat, ln):
                bad.append(f"L{i}: {ln.strip()[:90]}")
    check("SKILL.md 无 N/M 型统计数字", not bad, "\n".join(bad))

    print("\n── P9 文档不许与代码相反")
    ag = txt(AGENTS)
    check("AGENTS.md 不再写「固定用 minidev / extension 里写死了」",
          not re.search(r"固定用\s*`?minidev|extension 里写死", ag))
    check("AGENTS.md 说明了 dataset 参数可切换",
          "dataset" in ag and "dev2025" in ag)
    for tool in ["brief", "cols", "conventions", "audit", "force", "for_idx"]:
        check(f"AGENTS.md 的 pi 工具对照表提到 {tool}", tool in ag)

    print("\n── P6b 文档里不许写死“断言数”（手抄数字必然过期）")
    hard = []
    for f in [AGENTS, SKILL / "SKILL.md"]:
        for i, ln in enumerate(txt(f).splitlines(), 1):
            if re.search(r"\d+\s*项断言|共\s*\d+\s*项|\d+\s*项：", ln):
                hard.append(f"{f.name}:{i}: {ln.strip()[:80]}")
    check("AGENTS/SKILL 不写死测试断言数（让 run_all.py 打印）", not hard, " ｜ ".join(hard))

    print("\n── P10 勾选留痕：闸门 3 与核心条目标记必须真存在")
    core = re.findall(r"^-\s*\[ \]\s*\*\*([0-9]+[a-z]?)\..*<!-- core -->", cl, re.M)
    check(
        f"checklist.md 里有 `<!-- core -->` 标记的核心条目（{len(core)} 条：{','.join(core)}）",
        len(core) >= 3,
        str(core),
    )
    check(
        "闸门 3 会把勾选写进 probe_log（kind=checks）",
        'record(args.idx, db_id, "checks"' in bird_src,
    )
    check(
        "条目号由 checklist.md 现场解析（工具里不另存条目表）",
        "def checklist_items(" in bird_src and 'REFS / "checklist.md"' in bird_src,
    )
    check(
        "checks 记录不算探针（否则失败的提交能给闸门 1 发假通行证）",
        'p.get("kind") != "checks"' in bird_src,
    )
    for f in (AGENTS, SKILL / "SKILL.md"):
        t = txt(f)
        check(f"{f.name} 已改成「三道闸门」（与代码一致）", "三道" in t and "两道机器闸门" not in t)

    print("\n── P12 未修缺陷清单：待修的东西必须落盘，不许只活在会话里")
    SENT_ACT = "<!-- canon:active-defects"
    cb_txt = txt(REF / "casebook.md")
    act_holders = [f.name for f in live_docs if SENT_ACT in txt(f)]
    check(f"未修缺陷清单哨兵只在 casebook.md（实际：{act_holders}）",
          act_holders == ["casebook.md"], str(act_holders))
    act = cb_txt.split(SENT_ACT)[-1].split("\n## ")[1] if SENT_ACT in cb_txt else ""
    act_rows = [l for l in act.splitlines() if re.match(r"^\|\s*P\d+\s*\|", l)]
    check(f"未修缺陷清单有形如 `| P<n> |` 的行（{len(act_rows)} 条）或写『（无）』",
          len(act_rows) >= 1 or "（无）" in act, f"rows={len(act_rows)}")
    bad_act = [r[:50] for r in act_rows if "`rg" not in r and "wc -c" not in r]
    check("每条未修缺陷都带可复现的证据命令", not bad_act, " ｜ ".join(bad_act))
    stale = [f"P{n}" for n in (0, 1, 3, 5, 6, 7, 9, 10, 11, 13) if re.search(rf"^\|\s*P{n}\s*\|", act, re.M)]
    check("已修完的缺陷没有滞留在未修表里（P0/P1/P3/P5/P6/P7/P9/P10/P11/P13）", not stale, str(stale))

    print("\n── P3 作废索引：旧结论不许被当成现行规则")
    SENT_DEP = "<!-- canon:deprecated"
    live_docs = [SKILL / "SKILL.md", *sorted(REF.glob("*.md")), *sorted((REF / "db").glob("*.md"))]
    dep_holders = [f.name for f in live_docs if SENT_DEP in txt(f)]
    check(f"作废索引哨兵只在 casebook.md（实际：{dep_holders}）",
          dep_holders == ["casebook.md"], str(dep_holders))
    cb_txt = txt(REF / "casebook.md")
    idx = cb_txt.split(SENT_DEP)[-1].split("## 轮次索引")[0] if SENT_DEP in cb_txt else ""
    rows = [l for l in idx.splitlines() if l.strip().startswith("|") and "第" in l]
    check(f"作废索引有 {len(rows)} 条（≥5）", len(rows) >= 5, str(len(rows)))
    missing_kw = [k for k in ["T1", "DISTINCT", "mk_cards", "LIMIT 1", "930101"] if k not in idx]
    check("索引覆盖五个已知被推翻的旧结论（T1 / formula_1 DISTINCT / mk_cards / LIMIT 1 / 930101）",
          not missing_kw, f"缺：{missing_kw}")
    bad_rows = [r[:60] for r in rows
                if not re.search(r"第\s*\d+\s*轮", r)
                or not any((c / n).exists() for n in re.findall(r"([a-zA-Z0-9_./-]+\.md)", r)
                           for c in (REF, REF / "db", SKILL, ROOT))]
    check("索引每行都有『第 N 轮』+ 一个真实存在的目标文件", not bad_rows, " ｜ ".join(bad_rows))

    # 现场文件提到“上一版/写反了…”时，同一处必须打 ⛔（否则读者会把旧结论当现行）
    TRIG = re.compile(r"上一版|写反了|曾写错|原先写的是|曾经写错|已过时"
                      r"|旧笔记|旧结论|旧规则|旧口径|原来那条|原规则")
    naked = []
    for f in [*sorted((REF / "db").glob("*.md")), REF / "traps.md", REF / "checklist.md", REF / "shapes.md"]:
        lines = txt(f).splitlines()
        for i, ln in enumerate(lines):
            win = lines[max(0, i - 4):i + 5]
            marked = any("⛔" in x and "已作废" in x for x in win)
            if TRIG.search(ln) and not marked:
                naked.append(f"{f.name}:{i + 1}")
    check("现役文件提到旧版本时同一处有『⛔ 已作废』标记", not naked, "，".join(naked))

    print("\n── P5 重交白名单：正文只准有一处，别处只能指路")
    SENTINEL = "<!-- canon:resubmit"        # 只许出现在正文那一处；别处引用标题不算
    live = [AGENTS, SKILL / "SKILL.md", *sorted(REF.glob("*.md"))]
    holders = [f.name for f in live if SENTINEL in txt(f)]
    check(f"白名单正文哨兵只在 checklist.md（实际：{holders}）", holders == ["checklist.md"], str(holders))
    for f, who in [(SKILL / "SKILL.md", "SKILL.md"), (REF / "traps.md", "traps.md"),
                   (REF / "casebook.md", "casebook.md"), (AGENTS, "AGENTS.md")]:
        check(f"{who} 指路到白名单", "重交白名单" in txt(f))
    canon_txt = txt(REF / "checklist.md")
    missing = [k for k in ["no such column", "空集", "执行失败", "大小写", "闸门 2", "挂起清单"]
               if k not in canon_txt]
    check("白名单覆盖六类依据", not missing, f"缺：{missing}")
    check("白名单写明“看过金标不重交”", "看过金标" in canon_txt)

    print("\n── 链接有效性（含 casebook —— P7 修完后不再有豁免）")
    broken = []
    for f in [SKILL / "SKILL.md", *sorted(REF.glob("*.md")), *sorted((REF / "db").glob("*.md"))]:
        for target in re.findall(r"`([a-zA-Z0-9_./-]+\.md)`", txt(f)):
            name = target.split("/")[-1]
            cands = [REF / name, REF / target, REF / "db" / name,
                     SKILL / name, ROOT / name, ROOT / "tools" / name, ROOT / "data" / name]
            if not any(c.exists() for c in cands):
                broken.append(f"{f.name} -> {target}")
    check("所有 .md 引用都真实存在（不许指向已删文件）", not broken, "; ".join(broken))

    if warn:
        print("\n⚠️ 提醒（不影响通过）")
        for w in warn:
            print(f"  · {w}")

    print(f"\n════ 通过 {pass_n} / 失败 {fail_n} ════")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
