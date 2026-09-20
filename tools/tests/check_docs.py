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

    print("\n── P18 skill 全量审计：把「静态声明」全部机器化（本轮 9 类漂移都是这么漏的）")
    import argparse
    import contextlib
    import io

    live = [SKILL / "SKILL.md", REF / "checklist.md", REF / "traps.md", REF / "shapes.md",
            REF / "diagnosis.md", REF / "scoring.md", REF / "gold-style.md",
            REF / "naming-traps.md", REF / "sqlite-and-data.md", REF / "calibration.md",
            REF / "maintaining.md", *sorted((REF / "db").glob("*.md"))]

    # ① 闸门数：任何一处写成「两道/三道」都是陈年文本（连 bird.py 的 help 一起管）
    stale_gates = []
    for f, label in [(x, x.name) for x in live + [AGENTS]] + [(ROOT / "tools" / "bird.py", "bird.py")]:
        for i, ln in enumerate(txt(f).splitlines(), 1):
            if re.search(r"[两二三四]道(机器)?闸门", ln) and "四道" not in ln:
                stale_gates.append(f"{label}:{i}: {ln.strip()[:70]}")
    check("现役文档 + bird.py 里没有「两道/三道闸门」的陈年文本", not stale_gates,
          " ｜ ".join(stale_gates))

    # ② 文档里的 --checks 示例必须自身合法（否则照抄就被闸门 3 拒）
    core_ids = [i for i, c in _bird.checklist_items() if c]
    all_ids = [i for i, _ in _bird.checklist_items()]
    bad_checks = []
    for f in live:
        for m in re.finditer(r'--checks\s+"([^"]+)"', txt(f)):
            raw = m.group(1)
            if any(ch in raw for ch in "…<>"):        # 占位式示例，跳过
                continue
            got = [x.strip() for x in raw.split(",") if x.strip()]
            miss = [c for c in core_ids if c not in got]
            unk = [g for g in got if g not in all_ids]
            if miss or unk:
                bad_checks.append(f"{f.name}: 缺{miss} 未知{unk}")
    check("文档里可照抄的 --checks 示例都含全部核心条目且不含未知条目号", not bad_checks,
          " ｜ ".join(bad_checks))

    # ③ 骨架范围：SKILL 说的 A1–AN 必须等于 shapes.md 实际的最大骨架号
    shape_txt = txt(REF / "shapes.md")
    max_a = max(int(x) for x in re.findall(r"^##\s*A(\d+)\.", shape_txt, re.M))
    claimed = [int(x) for x in re.findall(r"A1[–\-—]A(\d+)", txt(SKILL / "SKILL.md"))]
    check(f"SKILL 说的骨架范围 == shapes.md 实际（A1–A{max_a}）",
          claimed and set(claimed) == {max_a}, f"SKILL 声称 {claimed}，实际最大 A{max_a}")

    # ④ brief --step：帮助文本列出的步骤 == 真有内容的步骤；未知 step 必须失败关闭
    steps_real = _bird.available_steps()
    help_txt = _bird.build_parser()._subparsers._group_actions[0].choices["brief"].format_help()
    m_step = re.search(r"--step[^\n]*?（([0-9./]+)", help_txt)
    claimed_steps = m_step.group(1).split("/") if m_step else []
    check(f"brief --step 的 help 步骤 == 实际有内容的步骤（{[*steps_real]}）",
          claimed_steps == steps_real, f"help 写 {claimed_steps}，实际 {steps_real}")
    ok_all = True
    for s in steps_real:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                _bird.cmd_brief(argparse.Namespace(db_id=None, step=s))
        except SystemExit as exc:
            ok_all = ok_all and not exc.code
    closed = False
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            _bird.cmd_brief(argparse.Namespace(db_id=None, step="9"))
    except SystemExit as exc:
        closed = bool(exc.code)
    check("每个真实步骤都能推出内容；未知 step（9）失败关闭（不是静默空手而归）",
          ok_all and closed, f"ok_all={ok_all} closed={closed}")

    # ⑤ 库档案「交题前必查」必须恰好 3 条、编号 1/2/3（financial 曾出现 1. 1. 2. 3.）
    bad_db = []
    for d in sorted((REF / "db").glob("*.md")):
        head = txt(d).split("## 连接图")[0]
        nums = re.findall(r"^(\d+)\. ", head, re.M)
        if nums != ["1", "2", "3"]:
            bad_db.append(f"{d.name}: {nums}")
    check("每份库档案的「交题前必查」都是 3 条、编号 1/2/3", not bad_db, " ｜ ".join(bad_db))

    # ⑥ SKILL 承诺的档案小节名必须真的存在（"体检单"就是这么漏的：承诺了一节没人建）
    promised = set(re.findall(r"`## ([^`]+)`", txt(SKILL / "SKILL.md")))
    profiles = "\n".join(txt(d) for d in sorted((REF / "db").glob("*.md")))
    missing_sections = [s for s in promised if f"## {s}" not in profiles]
    check("SKILL 承诺的 db 档案小节名真实存在", not missing_sections, str(missing_sections))

    # ⑦ 挂起清单：唯一出处 + 别处只指路（它曾经是个"没有落点"的产物）
    SENT_HANG = "<!-- canon:hangs"
    holders = [f.name for f in live if SENT_HANG in txt(f)]
    check(f"挂起清单落盘说明的哨兵只在 diagnosis.md（实际：{holders}）",
          holders == ["diagnosis.md"], str(holders))
    diag_txt = txt(REF / "diagnosis.md")
    check("diagnosis.md 写明了挂起清单的落盘形式（不另设文件 ⇒ 就是 audit 错题明细 + 档案实测小节）",
          "不另设文件" in diag_txt and "audit" in diag_txt)
    loose = [f.name for f in [SKILL / "SKILL.md", REF / "checklist.md", REF / "traps.md"]
             if "挂起" in txt(f) and "diagnosis.md" not in txt(f)]
    check("提到「挂起」的现役文档都指路到 diagnosis.md", not loose, str(loose))

    # ⑧ 会随提交量增长的统计数字不许写成裸数字（以工具输出为准）
    grow = []
    for f in [REF / "traps.md", REF / "checklist.md"]:
        for i, ln in enumerate(txt(f).splitlines(), 1):
            if re.search(r"\d{3,}\s*道(已提交|金标)", ln) and "conventions" not in ln:
                grow.append(f"{f.name}:{i}: {ln.strip()[:70]}")
    check("「N 道已提交题的金标」这类会涨的数字都带「以 conventions 为准」", not grow,
          " ｜ ".join(grow))

    # ⑨ 流程入口：选题（这是整条链的前端，曾完全没写）
    check("SKILL.md 写了选题入口（bird_list / list --db）",
          "bird_list" in txt(SKILL / "SKILL.md") or "list --db" in txt(SKILL / "SKILL.md"))

    print("\n── P19 三类元缺陷的类级守卫（不是只管住那几个实例）")
    # ⭐ 类①「无落点的产物」：SKILL.md 每个「📤 产出」步骤都必须在注册表登记，且落点真实存在
    maint = txt(REF / "maintaining.md")
    check("产物↔落点注册表存在且有哨兵（唯一出处）", "<!-- canon:artifacts" in maint)
    sk_txt = txt(SKILL / "SKILL.md")
    steps_out, cur = [], None
    for ln in sk_txt.splitlines():
        m = re.match(r"###\s*第\s*([0-9.]+)\s*步", ln)
        if m:
            cur = m.group(1)
        if "📤" in ln and "产出" in ln and cur:
            steps_out.append(cur)
    registered = set(re.findall(r"^\|\s*第\s*([0-9.]+)\s*步\s*\|", maint, re.M))
    has_any = bool(re.search(r"^\|\s*任意步\s*\|", maint, re.M))
    missing = sorted(set(steps_out) - registered)
    extra = sorted(registered - set(steps_out))
    check(f"每个含「📤 产出」的步骤都在注册表里（SKILL 有 {len(set(steps_out))} 个）",
          not missing, f"没登记：{missing}")
    check("注册表里没有指向已不存在步骤的行", not extra, f"多出：{extra}")
    check("注册表登记了「任意步」的产物（挂起清单）", has_any)
    profiles = "\n".join(txt(d) for d in sorted((REF / "db").glob("*.md")))
    bad_sink = []
    for row in re.findall(r"^\|\s*第\s*[0-9.]+\s*步\s*\|([^|]*)\|([^|]*)\|", maint, re.M):
        sink = row[1]
        for sec in re.findall(r"##\s*([^`|]+)", sink):
            sec = sec.strip()
            if sec and f"## {sec}" not in profiles:
                bad_sink.append(f"承诺小节「{sec}」不存在")
        for path in re.findall(r"`([\w/]+\.(?:md|json|jsonl))`", sink):
            if not any((d / path).exists() for d in (ROOT, REF, SKILL, ROOT / "work")):
                bad_sink.append(f"落点文件不存在：{path}")
    check("注册表里的落点容器都真实存在（档案小节 / 文件）", not bad_sink, " ｜ ".join(bad_sink))

    # ⭐ T1：SKILL 第 0 步说「没有档案就跑 traps ⓪-1 冷启动五查」—— 这个指针必须真的通
    traps = txt(REF / "traps.md")
    check("traps.md 有 ⓪-1 冷启动五查小节（SKILL 第 0 步指路的目标）", "## ⓪-1" in traps)
    check("SKILL 第 0 步指路到 ⓪-1（没有档案时不是「无路可走」）", "⓪-1" in sk_txt)
    check("五查的五项都在（表数/列名/JOIN 命中率/值域/NULL）",
          all(k in traps for k in ("表数", "列名", "JOIN 命中率", "值域", "NULL")))
    check("冷启动小节点明「档案是缓存不是依赖」+「conventions 在这是空的」",
          "缓存" in traps and "没有任何已提交答案" in traps)
    #    ⭐ T1：库存在但零答案时，conventions 必须给**冷启动口径**，不能说成「这库没惯例」
    t1_src = (ROOT / "tools" / "bird.py").read_text(encoding="utf-8")
    check("conventions 空库文案指路冷启动五查（不是「没有可统计的题」一句话）",
          "冷启动五查" in t1_src and "没有任何已提交答案" in t1_src)
    check("write_card 有噪声下限（不许拿 1~2 道题写卡片）", "跳过写卡片" in t1_src)

    # ⭐ T1+T2（本轮）：push 标记必须成对、不许嵌套；同义表必须真有落点；
    #    做题路径不许写「看金标行数再改」；COUNT/JULIANDAY 只留一套默认。
    PUSH_OPEN = re.compile(r"<!--\s*push\s+step=([0-9.]+)\s*-->")
    PUSH_CLOSE = re.compile(r"<!--\s*/push\s*-->")
    nest_bad, unbal = [], []
    for f in sorted(REF.glob("*.md")):
        # 剥围栏/行内代码：maintaining.md 用 `<!-- push … /push -->` 当语法示例，不算真标记
        raw = re.sub(r"```.*?```", "", txt(f), flags=re.S)
        raw = re.sub(r"`[^`]*`", "", raw)
        depth, stack = 0, []
        tokens = sorted(
            [(m.start(), "open", m.group(1)) for m in PUSH_OPEN.finditer(raw)]
            + [(m.start(), "close", None) for m in PUSH_CLOSE.finditer(raw)]
        )
        for pos, kind, step in tokens:
            if kind == "open":
                if depth > 0:
                    nest_bad.append(f"{f.name}: nested push step={step} inside {stack[-1]}")
                depth += 1
                stack.append(step)
            else:
                if depth == 0:
                    unbal.append(f"{f.name}: extra /push")
                else:
                    depth -= 1
                    stack.pop()
        if depth:
            unbal.append(f"{f.name}: unclosed push depth={depth}")
    check("push 标记不许嵌套（每个 push 块不能再含 push）", not nest_bad, " ｜ ".join(nest_bad[:4]))
    check("push 标记成对（每个 push 恰好一个 /push）", not unbal, " ｜ ".join(unbal[:4]))
    traps_blocks = [(s, b) for s, fn, b in _bird.push_blocks(None) if fn == "traps.md"]
    traps_steps = {s for s, _ in traps_blocks}
    check("traps.md 的 ①–④ 被推进 step=4（不再只推冷启动）",
          "4" in traps_steps and any("## ①" in b and "## ④" in b for s, b in traps_blocks if s == "4"),
          f"traps steps={sorted(traps_steps)}")
    check("traps.md 的 ⓪ 概念定位被推进 step=3.5",
          any(s == "3.5" and "概念先定位" in b for s, b in traps_blocks))
    check("traps.md 的 ⓪-1 冷启动被推进 step=1",
          any(s == "1" and "冷启动" in b for s, b in traps_blocks))
    miss_syn = [p.name for p in sorted((REF / "db").glob("*.md"))
                if not re.search(r"^## 同义表\s*$", txt(p), re.M)]
    check("11 份库档案都有 ## 同义表（checklist 8b / 值层六问第 1 条的落点）",
          not miss_syn, ",".join(miss_syn))
    live_doing = [SKILL / "SKILL.md", REF / "traps.md", REF / "shapes.md",
                  REF / "checklist.md", REF / "gold-style.md", REF / "calibration.md",
                  *sorted((REF / "db").glob("*.md"))]
    gold_look = []
    GOLD_LOOK_RE = re.compile(
        r"用金标行数反推|detail 说行数|失败了就换另一种写法|"
        r"bird_score 的行数会立刻|先试行级，错了换|失败再换\*\*去重"
    )
    for f in live_doing:
        for i, ln in enumerate(txt(f).splitlines(), 1):
            if GOLD_LOOK_RE.search(ln):
                gold_look.append(f"{f.name}:{i}: {ln.strip()[:70]}")
    check("做题路径不再写「看金标行数再改 / 失败了等 score」",
          not gold_look, " ｜ ".join(gold_look[:4]))
    count_star_default = []
    COUNT_STAR_RE = re.compile(r"先试(\*\*)?行数|先试 COUNT\(\*\)|没 DISTINCT 先试不去重")
    for f in [REF / "traps.md", REF / "shapes.md", REF / "calibration.md",
              REF / "checklist.md", SKILL / "SKILL.md"]:
        for i, ln in enumerate(txt(f).splitlines(), 1):
            if COUNT_STAR_RE.search(ln):
                count_star_default.append(f"{f.name}:{i}: {ln.strip()[:70]}")
    check("COUNT 默认不再写成先试 COUNT(*) / 先试行数",
          not count_star_default, " ｜ ".join(count_star_default[:4]))
    juli = txt(REF / "traps.md") + txt(REF / "calibration.md")
    check("JULIANDAY 口径统一为「跨度用 JULIANDAY、年份差看档案」",
          "跨度用" in juli and "年份差" in juli and "别自作主张用" not in juli)

    # ⭐ 类②「同一事实多处手写」：文档说的闸门数必须 == 代码常量（单一数据源）
    n_gates = _bird.N_GATES
    cn = {2: "两", 3: "三", 4: "四", 5: "五", 6: "六"}
    bad_n = []
    for f in live + [AGENTS]:
        for m in re.finditer(r"([两二三四五六])道(?:机器)?闸门", txt(f)):
            if cn.get(n_gates) != m.group(1):
                bad_n.append(f"{f.name}: {m.group(0)}")
    check(f"现役文档里的闸门个数都 == bird.N_GATES（{n_gates}）", not bad_n, " ｜ ".join(bad_n))
    _acts = _bird.build_parser()._subparsers._group_actions[0]._choices_actions
    src = (ROOT / "tools" / "bird.py").read_text(encoding="utf-8")
    ans_help = next(x.help or "" for x in _acts if x.dest == "answer")
    check("answer 的 help 里闸门数由 N_GATES/_CN_NUM 生成（源码不留字面量）",
          _bird._CN_NUM[n_gates] in ans_help, ans_help)
    check("bird.py 的 GATES 条数 == N_GATES（常量自洽）", len(_bird.GATES) == n_gates)
    #    ⭐ 光看"输出里有没有『四』"抓不到"改回手写"（手写的也是『四』）⇒ 必须查**源码**：
    #    answer 的 help 要用 _CN_NUM[N_GATES] 拼，不能出现字面的「N 道闸门」。
    check("answer 的 help 是 _CN_NUM[N_GATES] 拼出来的（源码不留字面闸门数）",
          "_CN_NUM[N_GATES]" in src
          and not re.search(r'help=f?"[^"]*[两二三四五]道(?:机器)?闸门', src),
          "源码里出现了手写的闸门数字")
    # 扩展侧也不能另抄一份步骤列表（同一事实多处手写 = 早晚漂移）
    ext = (ROOT / ".pi/extensions/bird-sql/index.ts").read_text(encoding="utf-8")
    check("index.ts 不手抄 step 取值列表（指路后端）",
          not re.search(r"step 取值：[0-9]", ext) and "available_steps" in ext)
    # 套件个数：文档说的数字 == run_all.py 里真实的套件数
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_run_all", ROOT / "tools/tests/run_all.py")
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)          # run_all 的重活都在 main() 里，导入无副作用
    n_suites = _mod.N_SUITES
    ag = txt(AGENTS)
    cn_map = {2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七"}
    bogus = [m.group(0) for m in re.finditer(r"[两三五六七八]个套件|四个套件", ag)
             if m.group(0)[0] != cn_map.get(n_suites)]
    check(f"AGENTS.md 不再手抄套件个数（真实 {n_suites} 个）", not bogus, str(bogus))

    check("brief 的 --step help 由 available_steps() 生成（不留手写步骤列表）",
          "available_steps()" in src and not re.search(r'--step", help="[^"]*（[0-9]/', src))

    print("\n── P8 SKILL.md 常驻预算（搬出去的知识必须还有落点）")
    budget = 14500  # 常驻上下文上限：SKILL.md 实测 18.3KB 时启用（P8），改小要先搬东西出去
    #   ⭐ 必须**按 LF 归一后**数字节：Windows 上 git（autocrlf）会把工作区 checkout 成 CRLF，
    #   每行多 1 字节 ⇒ 同一个文件在不同机器上会得出不同的"字节数"，预算判定跟着漂移
    #   （实测差 210 字节 = 210 行，Linux CI 过、Windows 挂）。
    #   ⭐ 必须按**内容**（LF 归一后）数字节，不能用 stat().st_size：Windows 上 git（autocrlf）把
    #   工作区 checkout 成 CRLF，每行多 1 字节 ⇒ 同一个文件在不同机器上"字节数"不同，预算判定跟着
    #   漂移（实测差 210 = 行数：Linux CI 过、Windows 挂）。read_text 的通用换行已把 CRLF 折成 LF。
    size = len((SKILL / "SKILL.md").read_text(encoding="utf-8").encode("utf-8"))
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
                      r"|旧笔记|旧结论|旧规则|旧口径|原来那条|原规则"
                      r"|Mini-Dev 版|Mini-Dev 时代|minidev 版|minidev 时代")
    naked = []
    for f in [*sorted((REF / "db").glob("*.md")), REF / "traps.md", REF / "checklist.md", REF / "shapes.md"]:
        lines = txt(f).splitlines()
        for i, ln in enumerate(lines):
            win = lines[max(0, i - 4):i + 5]
            marked = any("⛔" in x and "已作废" in x for x in win)
            if TRIG.search(ln) and not marked:
                naked.append(f"{f.name}:{i + 1}")
    check("现役文件提到旧版本时同一处有『⛔ 已作废』标记", not naked, "，".join(naked))

    print("\n── P20 库档案硬约束：串味 / 陈年数字 / 不存在的表列")
    arch = sorted((REF / "db").glob("*.md"))
    check(f"库档案有 {len(arch)} 份（≥11）", len(arch) >= 11, str(len(arch)))
    # 3.1 表头必须标数据集（表头数字来自旧 dev，卡片来自 dev2025）
    head_bad = []
    for f in arch:
        line = txt(f).splitlines()[0]
        if not re.search(r"simple EX [\d.]+%", line):
            head_bad.append(f"{f.name}（没有 simple EX 表头）")
        elif not re.search(r"旧 dev|dev2025|minidev", line):
            head_bad.append(f"{f.name}：{line[:60]}")
    check("每份档案表头都标了数据集（旧 dev / dev2025）", not head_bad, " ｜ ".join(head_bad))
    # 3.2 手写「N 道 M 对」也必须标数据集
    stat_bad = []
    for f in arch:
        for i, ln in enumerate(txt(f).splitlines(), 1):
            # 只有声称「全量/全库成绩」的行会被读成"当前水平"，必须标数据集；
            # 「首批 13 道」这类自带范围的批次不算。
            if "全量" in ln and re.search(r"\d+\s*道[^。\n]{0,12}\d+\s*对", ln) and not re.search(
                    r"旧 dev|dev2025|minidev|Mini-Dev", ln):
                stat_bad.append(f"{f.name}:{i}")
    check("档案里声称「全量」的手写成绩都标了数据集", not stat_bad, "，".join(stat_bad))
    # 3.3 提到本库没有的表/列，必须落在否定语境
    NEG_CTX = ("没有", "不成立", "不存在", "已作废", "no such column", "别去", "别拿",
               "不要照抄", "别照抄", "直接报错")
    FILEY = re.compile(r"\.(md|py|json|jsonl|ts|cjs|sqlite)$")
    data_dir = ROOT / "data" / "DEV" / "dev_databases"
    if not data_dir.exists():
        print("  ⏭ SKIP 3.3/3.4（没有 data/DEV/dev_databases：这两个守卫需要真库 schema）")
    else:
        import sqlite3
        own_tables, all_tables = {}, {}
        for f in arch:
            dbp = data_dir / f.stem / f"{f.stem}.sqlite"
            if not dbp.exists():
                own_tables[f.stem] = None
                continue
            con = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
            tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            own_tables[f.stem] = tabs
            all_tables[f.stem] = ({c.lower() for tb in tabs
                                   for c in (r[1] for r in con.execute(f'PRAGMA table_info("{tb}")'))},
                                  {tb.lower() for tb in tabs})
            con.close()
        missing_db = [f.name for f in arch if own_tables.get(f.stem) is None]
        check("11 份档案对应的真库都在本地", not missing_db, "，".join(missing_db))
        # 3.5 表头写的「N 表」== 真库用户表数（排除 sqlite_% 内部表 —— sqlite_sequence 也是 type='table'）
        cnt_bad = []
        for f in arch:
            m = re.search(r"（(\d+) 表）", txt(f).splitlines()[0])
            if own_tables.get(f.stem) is None:
                continue
            n_real = len([x for x in own_tables[f.stem] if not x.lower().startswith("sqlite_")])
            if not m or int(m.group(1)) != n_real:
                cnt_bad.append(f"{f.name}: 表头 {m.group(1) if m else '?'} vs 真库 {n_real}")
        check("档案表头的「N 表」== 真库用户表数", not cnt_bad, " ｜ ".join(cnt_bad))
        alien, alias = [], re.compile(r"^[A-Za-z]?\d+$")
        for f in arch:
            tabs = own_tables.get(f.stem)
            if tabs is None:
                continue
            own_low = {x.lower() for x in tabs}
            cols_all, tabs_all = all_tables[f.stem]
            lines = txt(f).splitlines()
            for i, ln in enumerate(lines, 1):
                win = lines[max(0, i - 2):i]          # 否定常写在上一行（跨行句子）
                if any(k in x for x in win for k in NEG_CTX):
                    continue
                for m in re.finditer(r"`([A-Za-z_][A-Za-z0-9_]*)`", ln):
                    tok = m.group(1)
                    if FILEY.search(tok) or alias.match(tok) or tok.lower() in own_low:
                        continue
                    others = [d for d, (c, tb) in all_tables.items() if d != f.stem and tok.lower() in tb]
                    if others and tok.lower() not in cols_all:
                        alien.append(f"{f.name}:{i} `{tok}`（属 {others[0]}）")
                for m in re.finditer(r"`([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)`", ln):
                    tb, cl = m.group(1).lower(), m.group(2).lower()
                    if tb in own_low:
                        continue
                    others = [d for d, (c, tb2) in all_tables.items() if d != f.stem and tb in tb2]
                    if others and (tb, cl) != ("", ""):
                        alien.append(f"{f.name}:{i} `{m.group(0)}`（表属 {others[0]}）")
        check(f"档案点名的「别库表」都落在否定语境（{len(alien)} 处违规）", not alien, " ｜ ".join(alien[:6]))
        # 3.4 档案里的题号必须是本库的题（数据依赖；dev2025 编号）
        qfile = ROOT / "data" / "DEV" / "dev_20251106.json"
        if not qfile.exists():
            print("  ⏭ SKIP 3.4（没有 dev_20251106.json）")
        else:
            import json
            qs = json.loads(qfile.read_text(encoding="utf-8"))
            # 白名单：只准「讲渲染误读」这类非题号数字，且必须在文件里仍然存在（过期即失败）
            WL = {("student_club.md", "1000"): "讲 bird_query 渲染把 100.0 看成 1000",
                  ("student_club.md", "100"): "同上"}
            for (fn, num), why in WL.items():
                f = REF / "db" / fn
                check(f"白名单仍然需要（{fn} `{num}`：{why}）",
                      f.exists() and f"`{num}`" in txt(f),
                      "白名单过期了，删掉它（否则它会掩盖新问题）")
            alien_idx, used_wl = [], set()
            for f in arch:
                lines = txt(f).splitlines()
                for i, ln in enumerate(lines, 1):
                    for m in re.finditer(r"`(\d{2,4})`", ln):
                        num = m.group(1)
                        if (f.name, num) in WL:
                            used_wl.add((f.name, num))
                            continue
                        if int(num) >= len(qs):
                            continue
                        owner = qs[int(num)]["db_id"]
                        if owner == f.stem:
                            continue
                        # 跨库/跨数据集题号必须**自证**：带 minidev 前缀，或当行点名它属于哪个库
                        labeled = re.search(r"(mini\s*dev|minidev|mini)\s*idx\s*$",
                                            ln[:m.start()], re.I)
                        named = owner in ln or owner in lines[max(0, i - 2):i][0]
                        if not (labeled or named):
                            alien_idx.append(
                                f"{f.name}:{i} `{num}` 实属 {owner}（既没标 minidev、也没点名库）")
            check(f"档案里的题号都属于本库（或自证式的跨库引用）（{len(alien_idx)} 处越界）",
                  not alien_idx, " ｜ ".join(alien_idx[:6]))
            check("白名单全部被用到（没有僵尸条目）", used_wl == set(WL), f"未用到：{set(WL) - used_wl}")

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
