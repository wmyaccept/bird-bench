#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打官方提交包（BIRD Test Set Submission）。

用法：
    python tools/make_submission.py                 # 检查 + 打包
    python tools/make_submission.py --dry-run       # 只检查，不写 zip
    python tools/make_submission.py --check-run     # 额外真跑 dev 预测，统计空结果率（慢）

为什么要有这个脚本（而不是手敲 zip）：
官方 Submission Guidelines 有两条硬要求 ——
  ① "please make your submission files concise only containing related files about your work,
      please remove irrelevant files"
  ② "if more than 5% of SQL outputs are abnormal (e.g., NULL/empty outputs) and/or runtime
      errors occur, we will contact the team for fixes"（非高峰最多 3 次修订）
这两条都是**容易漏**的：漏 `data/` 会让包变成 5 GB，空结果率高会在他们那边被打回。
所以把"包内容"和"自检"写死在这里，每次打包都跑一遍。

退出码：0 打包成功 / 2 有硬失败（不许提交）/ 3 有警告（能打包但不该提交）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 包内容清单（唯一出处）：(zip 内路径, 仓库内来源)
MANIFEST = [
    ("README.md", "submission/README.md"),
    ("SUBMISSION.md", "submission/CHECKLIST.md"),
    ("requirements.txt", "requirements.txt"),
    ("runner/", "runner/"),
    ("tools/bird.py", "tools/bird.py"),
    ("tools/setup_data.py", "tools/setup_data.py"),
    ("tools/official_eval/", "tools/official_eval/"),
    ("prompt/", "submission/prompt/"),          # 方法 = prompt 文本（由 make_submission 生成）
    ("dev_pred/dev2025_pred.json", "work/runner_pred_dev2025.json"),
]

# prompt 目录只放"推理时真的会读"的文本；casebook/calibration/maintaining 是内部账本，不进去。
PROMPT_FILES = [
    "SKILL.md", "traps.md", "checklist.md", "shapes.md", "scoring.md",
    "diagnosis.md", "gold-style.md", "naming-traps.md", "sqlite-and-data.md",
]
PROMPT_DIRS = ["db"]

# 硬失败：出现即不许提交
HARD_BAN = [
    (re.compile(r"\.sqlite$|\.db$"), "数据库文件（官方自己有 test_databases）"),
    (re.compile(r"^data/"), "data/ 目录（5.3 GB，且是官方数据）"),
    (re.compile(r"(^|/)\.git/|(^|/)__MACOSX/|\.DS_Store$"), "版本库/系统垃圾"),
    (re.compile(r"(^|/)answers(_dev|_dev2025|_gen)?\.json$"), "别集的作答文件（只交 dev_pred/ 里那一份）"),
]
# 密钥泄露扫描（值必须够长才算真命中，避免把 `BIRD_API_KEY=your-key-here` 误报）
SECRET_PAT = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|apikey|secret|password|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"),
]
# 本机绝对路径：不算泄密，但会让官方 README 显得没法跑
ABSPATH_PAT = [
    re.compile(r"[A-Za-z]:[\\/](Users|school|tmp|python|Git|pi-harness)"),
    re.compile(r"/d/(tmp|school)"),
]
SIZE_LIMIT_MB = 20


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def collect(src: str) -> list[Path]:
    """把清单里的一项展开成文件列表（目录递归）。"""
    p = ROOT / src
    if not p.exists():
        return []
    if p.is_file():
        return [p]
    return sorted(f for f in p.rglob("*")
                  if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc")


def build_prompt_dir() -> tuple[list[tuple[Path, str]], list[str]]:
    """生成 submission/prompt/（方法文本）。返回 (文件, 备注)。"""
    src = ROOT / ".pi/skills/bird-sql"
    refs = src / "references"
    out: list[tuple[Path, str]] = []
    notes: list[str] = []
    for f in PROMPT_FILES:
        p = refs / f
        if p.exists():
            out.append((p, f"prompt/{f}"))
    for d in PROMPT_DIRS:
        for p in sorted((refs / d).glob("*.md")):
            out.append((p, f"prompt/{d}/{p.name}"))
    if (src / "SKILL.md").exists():
        out.append((src / "SKILL.md", "prompt/SKILL.md"))
    # 内部账本，明确不进包
    for skipped in ("casebook.md", "calibration.md", "maintaining.md"):
        if (refs / skipped).exists():
            notes.append(f"不打包 prompt/{skipped}（内部账本，非推理所需）")
    return out, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="输出 zip 路径")
    ap.add_argument("--dry-run", action="store_true", help="只检查不写 zip")
    ap.add_argument("--check-run", action="store_true",
                    help="真跑 dev 预测统计空结果率（官方 5%% 阈值，慢）")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="即使有硬失败也强行写出 zip（只用于本地看包结构，不许提交）")
    args = ap.parse_args()

    tag = date.today().strftime("%Y%m%d")
    out_zip = Path(args.out) if args.out else ROOT / "work/submission" / f"bird_submission_{tag}.zip"

    prompt_files, prompt_notes = build_prompt_dir()

    # ── 1. 展开清单
    items: list[tuple[Path, str]] = []
    missing: list[str] = []
    for dst, src in MANIFEST:
        if src == "submission/prompt/":
            continue
        files = collect(src)
        if not files:
            missing.append(f"{dst} ← {src}")
            continue
        for f in files:
            if dst.endswith("/"):
                items.append((f, dst + f.relative_to(ROOT / src).as_posix()))
            else:
                items.append((f, dst))
    items += prompt_files

    # ── 2. 硬检查
    hard: list[str] = []
    warn: list[str] = []

    for f, dst in items:
        for pat, why in HARD_BAN:
            if pat.search(dst):
                hard.append(f"{dst}：{why}")

    # 密钥 / 绝对路径
    for f, dst in items:
        if f.suffix.lower() not in {".md", ".py", ".txt", ".json", ".ts", ".cjs", ".sh", ".yml"}:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pat in SECRET_PAT:
            m = pat.search(text)
            if m:
                hard.append(f"{dst}：疑似密钥泄露 → {m.group(0)[:24]}…")
        if not dst.startswith("prompt/"):          # prompt 是散文，可能引示例路径
            for pat in ABSPATH_PAT:
                m = pat.search(text)
                if m:
                    warn.append(f"{dst}：含本机绝对路径 → {m.group(0)}")

    # 必需件
    names = {dst for _, dst in items}
    for need in ("README.md", "requirements.txt", "dev_pred/dev2025_pred.json"):
        if need not in names:
            hard.append(f"缺必需件：{need}")
    if "runner/run_bird.py" not in names:
        warn.append("缺 runner/run_bird.py —— 官方会真的跑代码，没有 runner 这个包无法在 test 上出结果")

    # README 得有可执行命令
    readme = next((f for f, d in items if d == "README.md"), None)
    if readme:
        t = readme.read_text(encoding="utf-8")
        n_cmd = t.count("```bash") + t.count("```shell") + t.count("```console")
        if n_cmd < 3:
            hard.append(f"README.md 里只有 {n_cmd} 个命令块（官方要求 detailed readme with commands）")

    # 给官方的文件里不许留占位符 / 内部备注（这两样最容易“忘了填就发出去”）
    for f, dst in items:
        if dst not in ("README.md", "SUBMISSION.md"):
            continue
        t = f.read_text(encoding="utf-8")
        holes = sorted(set(re.findall(r"<FILL[^>]*>", t)))
        if holes:
            hard.append(f"{dst} 里还有 {len(holes)} 处未填占位符：{'、'.join(holes[:3])}")
        if "<!--" in t:
            hard.append(f"{dst} 里还有内部备注（<!-- -->）没删")

    # dev 预测文件体检
    pred = next((f for f, d in items if d == "dev_pred/dev2025_pred.json"), None)
    pred_info = ""
    if pred:
        try:
            d = json.loads(pred.read_text(encoding="utf-8"))
            bad_fmt = [k for k, v in d.items() if "\t----- bird -----\t" not in v]
            empty = [k for k, v in d.items() if not v.split("\t----- bird -----\t")[0].strip()]
            dbs = {v.split("\t----- bird -----\t")[-1] for v in d.values()}
            pred_info = (f"{len(d)} 条 / {len(dbs)} 库 / 格式不合规 {len(bad_fmt)} / 空 SQL {len(empty)}")
            if bad_fmt:
                hard.append(f"dev 预测文件格式不合规 {len(bad_fmt)} 条（须含 \\t----- bird -----\\t）")
            if empty:
                hard.append(f"dev 预测文件里有 {len(empty)} 条空 SQL")
            if len(d) != 1534:
                warn.append(f"dev 预测文件只有 {len(d)} 条（dev2025 应为 1534）")
        except Exception as e:
            hard.append(f"dev 预测文件读不了：{e}")

    # 空结果率（官方 5% 阈值）—— 真跑一遍
    empty_rate = None
    if args.check_run and pred:
        sys.path.insert(0, str(ROOT / "tools"))
        import bird  # noqa: E402
        import os
        os.environ.setdefault("BIRD_DATASET", "dev2025")
        d = json.loads(pred.read_text(encoding="utf-8"))
        n_empty = n_err = 0
        for k, v in d.items():
            sql = v.split("\t----- bird -----\t")[0]
            db = v.split("\t----- bird -----\t")[-1]
            try:
                rows, _ = bird.run_sql(bird.db_path(db), sql)
                if not rows:
                    n_empty += 1
            except Exception:
                n_err += 1
        empty_rate = (n_empty + n_err) / max(1, len(d))
        print(f"  空结果 {n_empty} / 报错 {n_err} → 异常率 {empty_rate:.2%}（官方阈值 5%）")
        if empty_rate > 0.05:
            hard.append(f"dev 上异常率 {empty_rate:.2%} > 5%：官方会打回，先在本地修")

    # ── 3. 报告
    print("═" * 68)
    print(f"提交包清单（{len(items)} 个文件）")
    print("═" * 68)
    by_dir: dict[str, list[str]] = {}
    for _, dst in items:
        key = dst.split("/")[0] if "/" in dst else "（顶层）"
        by_dir.setdefault(key, []).append(dst)
    for d, fs in sorted(by_dir.items()):
        label = d + "/" if d != "（顶层）" else d
        print(f"  {label:24s} {len(fs):3d} 个   {', '.join(sorted(f.split('/')[-1] for f in fs)[:4])}"
              + (" …" if len(fs) > 4 else ""))
    print(f"\n  dev 预测：{pred_info}")
    for n in prompt_notes:
        print(f"  {n}")

    total = sum(f.stat().st_size for f, _ in items)
    print(f"\n  解压后合计：{total/1024/1024:.2f} MB（阈值 {SIZE_LIMIT_MB} MB）")
    if total > SIZE_LIMIT_MB * 1024 * 1024:
        hard.append(f"包体积 {total/1024/1024:.2f} MB 超过 {SIZE_LIMIT_MB} MB")

    if missing:
        print("\n⚠️ 清单里找不到的来源：")
        for m in missing:
            print(f"    {m}")
    if warn:
        print(f"\n⚠️ 警告 {len(warn)} 条：")
        for w in warn:
            print(f"    {w}")
    if hard:
        print(f"\n❌ 硬失败 {len(hard)} 条（不许提交）：")
        for h in hard:
            print(f"    {h}")
        if not args.allow_incomplete:
            return 2
        print("\n⚠️ --allow-incomplete：仍然写出 zip（仅供本地看结构，**不许提交**）")

    if args.dry_run:
        print("\n✅ 检查通过（--dry-run，未写 zip）")
        return 3 if warn else 0

    # ── 4. 写 zip（顶层带一层目录名，解压不散落）
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    top = f"bird_submission_{tag}"
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f, dst in items:
            z.write(f, f"{top}/{dst}")
    print(f"\n✅ 已写出：{rel(out_zip)}（{out_zip.stat().st_size/1024/1024:.2f} MB）")
    if hard:
        print(f"❌ 这个包有 {len(hard)} 条硬失败 —— 只当草稿看，不要发出去")
        return 2
    if warn:
        print(f"⚠️ 但有 {len(warn)} 条警告 —— 先看上面，别急着发邮件")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
