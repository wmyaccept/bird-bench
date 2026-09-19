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
        "checks/force 都不算探针（否则失败的提交/硬交过的一次能给闸门 1 发假通行证）",
        'p.get("kind") != "checks"' in bird_src or 'kind") in PROBE_KINDS' in bird_src,
    )
    # ⭐ P14：探针判定必须是**白名单**（黑名单会被新写法绕过：force 就绕过过）
    m_probe = re.search(r"PROBE_KINDS = \{([^}]*)\}", bird_src)
    ck = set(re.findall(r'"([a-z]+)"', m_probe.group(1))) if m_probe else set()
    check(
        f"探针种类是白名单且不含 checks/force（实际：{sorted(ck)}）",
        bool(m_probe) and not ("checks" in ck or "force" in ck) and len(ck) >= 4,
        str(sorted(ck)),
    )
    check(
        "闸门 1 与 audit 覆盖统计都用这个白名单（两处以上）",
        bird_src.count('get("kind") in PROBE_KINDS') >= 2,
        str(bird_src.count('get("kind") in PROBE_KINDS')),
    )
    check(
        "强制率在过滤**之前**统计（否则 --force 永远是 0 —— 指标又说谎）",
        "for p in probes_all.get(i, [])" in bird_src,
    )
    for f in (AGENTS, SKILL / "SKILL.md"):
        t = txt(f)
        check(f"{f.name} 已改成「四道闸门」（与代码一致）", "四道" in t and "三道" not in t)
        check(
            f"{f.name} 的闸门 1 口径写清了 checks/force 不算探针（P14）",
            "`checks` 与 `force` 不算" in t,
        )

    print("\n── P16 闸门 4（属性清单）：治「少给列」")
    ext_src = (ROOT / ".pi/extensions/bird-sql/index.ts").read_text(encoding="utf-8")
    check(
        "answer 支持 --attrs 且属性清单会被校验（不是只加个参数）",
        '"--attrs"' in bird_src
        and "def parse_attrs(" in bird_src
        and "attrs_traceable(" in bird_src
        and "len(attrs) != len(columns)" in bird_src,
    )
    check(
        "闸门 4 的列数下界用了两个来源（同模板已提交题 + 本库×难度 P20）",
        "def attrs_lower_bound(" in bird_src
        and "def similar_submitted(" in bird_src
        and "def gold_ncol_prior(" in bird_src,
    )
    check(
        "attrs 记录不算探针（闸门 1 的凭据只能是真探针）",
        '"attrs"' in bird_src and '"attrs"' not in set(re.findall(r'"([a-z]+)"', re.search(r"PROBE_KINDS = \{([^}]*)\}", bird_src).group(1))),
    )
    check(
        "闸门 4 有自我标定（audit 会算它会拦下几道错题 / 误拦几道对题）",
        "闸门 4 列数下界自标定" in bird_src,
    )
    # ⭐ P17：核心条目必须用**闸门自己的解析器**断言 —— 上一轮把 13b 的 `<!-- core -->`
    #    写在续行上，闸门（按行匹配）根本没认，而这里用 re.S 的宽松断言却放过了（测试比实现松）。
    import sys as _sys

    if str(ROOT / "tools") not in _sys.path:
        _sys.path.insert(0, str(ROOT / "tools"))
    import bird as _bird

    _core = [i for i, c in _bird.checklist_items() if c]
    check(
        "核心条目 == 闸门现场解析出来的集合（含 13b 属性清单 / 8b 值层六问）",
        set(_core) == {"1", "1b", "2", "2b", "8", "8b", "12", "13", "13b"},
        _core,
    )
    _orphan = [
        l for l in txt(REF / "checklist.md").splitlines()
        if "<!-- core -->" in l
        and not l.lstrip().startswith(">")
        and not re.match(r"^\s*-\s*\[ \]\s*\*\*[0-9]+[a-z]?\.", l)
    ]
    check(
        "没有『孤儿 core 标记』（写在条目续行上闸门会静默忽略）",
        not _orphan,
        [x.strip()[:40] for x in _orphan[:2]],
    )
    check(
        "traps.md 有『值层六问』且带 205 道错题的实测道数（不是只写个标题）",
        "值层六问" in txt(REF / "traps.md") and "70 道（34%）" in txt(REF / "traps.md"),
    )
    _profiles = list((REF / "db").glob("*.md"))
    _with = [p.name for p in _profiles if "值层实测" in p.read_text(encoding="utf-8")]
    check(
        "11 份库档案都补了『值层实测』（D 类错题按库落地）",
        len(_with) == len(_profiles) == 11,
        f"{len(_with)}/{len(_profiles)}",
    )
    check(
        "AGENTS/SKILL 不再手抄核心条目号",
        not re.search(r"核心条目（`1`/`1b`", txt(AGENTS) + txt(SKILL / "SKILL.md")),
    )
    check(
        "pi 扩展侧同步：bird_answer 有 attrs 参数 + bird_attrs 工具",
        "attrs: Type.Optional" in ext_src and 'name: "bird_attrs"' in ext_src,
    )
    check(
        "SKILL.md 不抄闸门 4 的标定数字（或移到了 traps.md）",
        "0.83%" not in txt(SKILL / "SKILL.md") and "0.83%" in txt(REF / "traps.md"),
    )

    print("\n── P8 SKILL.md 常驻预算（搬出去的知识必须还有落点）")
    budget = 14500  # 常驻上下文上限：SKILL.md 实测 18.3KB 时启用（P8），改小要先搬东西出去
    size = (SKILL / "SKILL.md").stat().st_size
    check(
        f"SKILL.md ≤ {budget} 字节（现 {size}；超了就搬进 references/ 再指路）",
        size <= budget,
        f"超 {size - budget} 字节",
    )
    landed = {
        "calibration.md 里有「口径实验」（从 SKILL.md 搬过去的）": (REF / "calibration.md"),
        "diagnosis.md 里有「挂起清单」集中复盘（从 SKILL.md 搬过去的）": (REF / "diagnosis.md"),
        "maintaining.md 存在且含「维护约定」（从 SKILL.md 搬过去的）": (REF / "maintaining.md"),
        "maintaining.md 含「下次又漏了规则」自查": (REF / "maintaining.md"),
    }
    for name, path in landed.items():
        t = txt(path) if path.exists() else ""
        key = {
            0: "口径实验",
            1: "挂起清单",
            2: "维护约定",
            3: "下次又漏了规则",
        }[list(landed).index(name)]
        check(name, key in t, f"{path.name} 里找不到「{key}」")
    sk = txt(SKILL / "SKILL.md")
    check("SKILL.md 指路到 maintaining.md（不是把维护规则又抄回来）", "maintaining.md" in sk)
    check("SKILL.md 指路到 calibration.md（口径实验）", "calibration.md" in sk)

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
    stale = [f"P{n}" for n in (0, 1, 3, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15) if re.search(rf"^\|\s*P{n}\s*\|", act, re.M)]
    check("已修完的缺陷没有滞留在未修表里（P0/P1/P3/P5/P6/P7/P8/P9/P10/P11/P13/P14/P15）", not stale, str(stale))

    print("\n── P15 金标形状是「提交后」产物（讲反推手法的地方必须写明前提）")
    SENT_SHAPE = "<!-- canon:shape-after-submit"
    diag = txt(REF / "diagnosis.md")
    scor = txt(REF / "scoring.md")
    check("diagnosis.md 写了前提声明哨兵（唯一出处）", SENT_SHAPE in diag)
    check("scoring.md 讲金标行数约束时也带同一哨兵（指路）", SENT_SHAPE in scor)
    check(
        "诊断文档明确写了「提交并评分之后」+「做题前没有任何逐题通道」",
        "提交并评分之后" in diag and "做题前没有任何逐题通道" in diag,
    )
    check(
        "诊断文档提醒了这招不许回头改已看过的题（指回重交白名单）",
        "绝不许拿已看到的形状回头改那道题" in diag and "重交白名单" in diag,
    )

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
