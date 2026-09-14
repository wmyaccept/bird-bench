#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""准备 BIRD 数据集：下载 -> 选择性解压 -> 规范化。

支持两个数据集（用 `--dataset` 选，默认 minidev）：

  minidev  Mini-Dev 500（764 MiB）  → data/MINIDEV/
  dev      官方 Dev 集（330 MiB）   → data/DEV/

为什么不是简单的"下载 + 全解压"：

1. **选择性解压**：minidev.zip 里除了 SQLite 版，还塞了 MySQL 和 PostgreSQL 各自的
   1 GB 建库脚本。只做 SQLite 时默认跳过，省下约 2 GB。
2. **嵌套压缩包**：dev.zip 里的 `dev_databases.zip` 本身是个 zip，
   数据库在里面，必须二次解压。
3. **格式规范化**：minidev 的题目文件是 JSON **数组**，而官方评测脚本的
   `--diff_json_path` 只吃 **JSONL**。这里顺手生成 `.jsonl`，否则官方脚本一跑就崩。
   （dev.zip 直接给的就是 dev.json + dev.sql，不用转。）
4. **断点续传**：中断后重跑不会从头下载。

用法：
    python tools/setup_data.py                 # minidev（默认）
    python tools/setup_data.py --dataset dev   # 官方 Dev 集
    python tools/setup_data.py --dataset all   # 两个都要
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

OSS = "https://bird-bench.oss-cn-beijing.aliyuncs.com/"
SQLITE_DBS = [
    "debit_card_specializing", "financial", "formula_1", "california_schools",
    "card_games", "european_football_2", "thrombosis_prediction", "toxicology",
    "student_club", "superhero", "codebase_community",
]

DATASETS = {
    "minidev": {
        "name": "Mini-Dev 500",
        "url": OSS + "minidev.zip",
        "size": 800_943_648,          # 实测 Content-Length
        "dir": "MINIDEV",
        "questions": "mini_dev_sqlite.json",
        "gold": "mini_dev_sqlite_gold.sql",
        "strip": "minidev/",
        "skip": ("minidev/MINIDEV_mysql/", "minidev/MINIDEV_postgresql/"),
        "nested": None,
        "normalize": "minidev_jsonl",
        "n_questions": 500,
    },
    "dev": {
        "name": "BIRD Dev 1534",
        "url": OSS + "dev.zip",
        "size": 346_207_293,
        "dir": "DEV",
        "questions": "dev.json",
        "gold": "dev.sql",
        "strip": "dev_20240627/",
        "skip": (),
        "nested": "dev_databases.zip",   # 数据库在这个嵌套 zip 里
        "normalize": None,
        "n_questions": 1534,
    },
}


def human(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


DATA_DIR = env_path("BIRD_DATA_DIR", ROOT / "data")


def ds_dir(key: str) -> Path:
    return DATA_DIR / DATASETS[key]["dir"]


# ---------------------------------------------------------------- 下载


def download(url: str, target: Path, expected: int, proxy: str | None = None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size >= expected:
        print(f"  压缩包已完整：{target.name} ({human(target.stat().st_size)})，跳过下载")
        return target

    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)

    done = target.stat().st_size if target.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={done}-"} if done else {})
    print(f"  下载 {url}")
    if done:
        print(f"  检测到未完成的文件（{human(done)}），从断点继续")
    try:
        with opener.open(request, timeout=60) as response:
            resuming = bool(done) and response.status == 206
            if done and not resuming:
                print("  服务器不支持续传，从头开始")
                done = 0
                target.unlink(missing_ok=True)
            header_len = response.headers.get("Content-Length")
            total = int(header_len) + done if header_len and header_len.isdigit() else expected
            start = time.monotonic()
            start_bytes = done
            last = start
            with target.open("ab" if resuming else "wb") as fh:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last >= 1.0 or done >= total:
                        speed = (done - start_bytes) / max(now - start, 1e-9)
                        eta = (total - done) / speed if speed > 0 else 0
                        pct = done / total * 100 if total else 100
                        print(
                            f"\r  {pct:5.1f}%  {human(done)} / {human(total)}"
                            f"  {human(speed)}/s  ETA {int(eta) // 60:02d}:{int(eta) % 60:02d}",
                            end="", flush=True,
                        )
                        last = now
            print()
    except urllib.error.HTTPError as exc:
        sys.exit(f"ERROR: 下载失败 HTTP {exc.code}。若在公司网络下，试试 --proxy http://127.0.0.1:7890")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: 下载失败 {exc.reason}。检查网络，或用 --proxy 指定代理")

    actual = target.stat().st_size
    if total and actual < total:
        sys.exit(f"ERROR: 下载不完整，期望 {human(total)}，实际 {human(actual)}。重跑本脚本会自动续传。")
    print(f"  下载完成：{target.name} ({human(actual)})")
    return target


# ---------------------------------------------------------------- 解压


def extract(
    zip_path: Path,
    dest: Path,
    strip: str = "",
    skip: tuple[str, ...] = (),
    label: str = "",
) -> None:
    """把 zip 里（跳过 skip 前缀的）文件解压到 dest，去掉一层 strip 前缀。"""
    with zipfile.ZipFile(zip_path) as zf:
        members = []
        skipped = 0
        for info in zf.infolist():
            name = info.filename
            if info.is_dir():
                continue
            if name.startswith(skip):
                skipped += 1
                continue
            rel = name[len(strip):] if strip and name.startswith(strip) else name
            members.append((info, rel))

        total_bytes = sum(i.file_size for i, _ in members)
        tag = f"{label} " if label else ""
        print(f"  {tag}{len(members)} 个文件（跳过 {skipped} 个），解压后 {human(total_bytes)}")
        dest.mkdir(parents=True, exist_ok=True)
        written = 0
        start = time.monotonic()
        for index, (info, rel) in enumerate(members, 1):
            target = dest / rel
            if target.exists() and target.stat().st_size == info.file_size:
                written += info.file_size
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            written += info.file_size
            if index % 20 == 0 or index == len(members):
                elapsed = max(time.monotonic() - start, 1e-6)
                print(f"\r  {tag}{index}/{len(members)}  {human(written)}/{human(total_bytes)}  ({elapsed:.0f}s)", end="", flush=True)
        print()


# ---------------------------------------------------------------- 规范化


def normalize_minidev(dest: Path) -> None:
    """OSS 包给的是 JSON 数组，官方脚本要 JSONL；顺手生成缺的那份。"""
    source = dest / "mini_dev_sqlite.json"
    if not source.exists():
        sys.exit(f"ERROR: 解压后找不到 {source}")
    questions = json.loads(source.read_text(encoding="utf-8"))
    jsonl = dest / "mini_dev_sqlite.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for item in questions:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  已生成 {jsonl.name}（{len(questions)} 行，官方评测脚本需要）")

    gold = dest / "mini_dev_sqlite_gold.sql"
    n_gold = len([l for l in gold.read_text(encoding="utf-8").splitlines() if l.strip()])
    if n_gold != len(questions):
        print(f"  WARNING: 题目数 {len(questions)} 与金标行数 {n_gold} 不一致，评测会错位")


def verify(key: str) -> bool:
    spec = DATASETS[key]
    dest = ds_dir(key)
    print(f"\n  -- {spec['name']} 校验 --")
    ok = True

    missing = [db for db in SQLITE_DBS if not (dest / "dev_databases" / db / f"{db}.sqlite").exists()]
    if missing:
        ok = False
        print(f"  缺失数据库：{', '.join(missing)}")
    else:
        total = sum((dest / "dev_databases" / db / f"{db}.sqlite").stat().st_size for db in SQLITE_DBS)
        print(f"  11 个 SQLite 数据库就绪，合计 {human(total)}")

    for name in (spec["questions"], spec["gold"], "dev_tables.json"):
        path = dest / name
        print(f"  [{'OK ' if path.exists() else '缺失'}] {name}")
        ok = ok and path.exists()

    if spec["questions"].endswith(".json") and (dest / spec["questions"]).exists():
        rows = json.loads((dest / spec["questions"]).read_text(encoding="utf-8"))
        if isinstance(rows, list):
            got = len(rows)
            flag = "OK " if got == spec["n_questions"] else "?? "
            print(f"  [{flag}] 题目数 {got}（预期 {spec['n_questions']}）")
            ok = ok and got == spec["n_questions"]
    return ok


# ---------------------------------------------------------------- 主流程


def setup(key: str, args) -> bool:
    spec = DATASETS[key]
    print(f"\n{'=' * 70}\n[{key}] {spec['name']}  ->  {ds_dir(key)}\n{'=' * 70}")

    zip_path = DATA_DIR / "_download" / f"{key}.zip"
    if args.force and zip_path.exists():
        zip_path.unlink()
    if not args.no_download:
        zip_path = download(spec["url"], zip_path, spec["size"], args.proxy)
    elif not zip_path.exists():
        sys.exit(f"ERROR: 指定了 --no-download，但 {zip_path} 不存在")

    dest = ds_dir(key)
    extract(zip_path, dest, strip=spec["strip"], skip=spec["skip"],
            label=f"[{key}]")

    if spec["nested"]:
        nested = dest / spec["nested"]
        if not nested.exists():
            sys.exit(f"ERROR: 找不到嵌套压缩包 {nested}")
        print(f"  解开嵌套压缩包 {nested.name}")
        extract(nested, dest, label=f"[{key}] 数据库")
        nested.unlink()          # 里面的东西已经落到 dev_databases/，不再需要

    if spec["normalize"] == "minidev_jsonl":
        normalize_minidev(dest)

    return verify(key)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="下载并准备 BIRD 数据集")
    parser.add_argument("--dataset", choices=[*DATASETS, "all"], default="minidev",
                        help="要准备哪个数据集（默认 minidev）")
    parser.add_argument("--no-download", action="store_true", help="只用已有的压缩包")
    parser.add_argument("--force", action="store_true", help="删掉压缩包重新下载")
    parser.add_argument("--proxy", help="下载代理，例如 http://127.0.0.1:7890")
    args = parser.parse_args()

    print(f"数据目录：{DATA_DIR}")
    keys = list(DATASETS) if args.dataset == "all" else [args.dataset]
    results = {key: setup(key, args) for key in keys}

    print(f"\n{'=' * 70}")
    for key, ok in results.items():
        print(f"  {key:<8} {'✅ 就绪' if ok else '❌ 不完整（重跑本脚本，会续传/补解压）'}")
    print()
    for key in keys:
        print(f"  python tools/bird.py --dataset {key} info")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
