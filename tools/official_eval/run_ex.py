#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑 BIRD 官方评测脚本（evaluation_ex.py）。

为什么需要这个包装：官方仓库里的 `run_evaluation.sh` 写死了相对路径和 `python3`，
在 Windows + Git Bash 下不能直接用。这里把路径和参数拼好，然后调用
`tools/official_eval/evaluation_ex.py`，口径与官方完全一致。

前置依赖（官方脚本需要）：
    pip install func-timeout

用法：
    python tools/official_eval/run_ex.py                      # 评测 work/score 里的预测文件
    python tools/official_eval/run_ex.py --pred path/to.json  # 指定预测文件
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


DATA_DIR = env_path("BIRD_DATA_DIR", ROOT / "data")
WORK_DIR = env_path("BIRD_WORK_DIR", ROOT / "work")
MD_DIR = DATA_DIR / "MINIDEV"


def ensure_jsonl() -> Path:
    """官方脚本的 --diff_json_path 只吃 JSONL，而 OSS 包里给的是 JSON 数组。"""
    jsonl = MD_DIR / "mini_dev_sqlite.jsonl"
    if jsonl.exists():
        return jsonl
    source = MD_DIR / "mini_dev_sqlite.json"
    if not source.exists():
        sys.exit(f"ERROR: 找不到题目文件 {source}，先运行 python tools/setup_data.py")
    contents = json.loads(source.read_text(encoding="utf-8"))
    with jsonl.open("w", encoding="utf-8") as fh:
        for item in contents:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"已生成 {jsonl}（{len(contents)} 行）")
    return jsonl


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="运行 BIRD 官方 EX 评测")
    parser.add_argument(
        "--pred",
        default=str(WORK_DIR / "score" / "pred_mini_dev_sqlite.json"),
        help="预测文件（官方格式：{'0': 'SQL\\t----- bird -----\\tdb_id', ...}）",
    )
    parser.add_argument("--num-cpus", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    pred = Path(args.pred)
    if not pred.exists():
        sys.exit(
            f"ERROR: 找不到预测文件 {pred}\n"
            f"先生成预测文件：python tools/bird.py score --list-wrong 0"
        )

    try:
        import func_timeout  # noqa: F401
    except ImportError:
        sys.exit(
            "ERROR: 官方脚本依赖 func-timeout，请先安装：\n"
            "    pip install func-timeout\n"
            "（或者直接用 `python tools/bird.py score`，那个实现不依赖第三方包，\n"
            "  判定逻辑与官方 evaluation_ex.py 相同。）"
        )

    diff_json = ensure_jsonl()
    log_dir = WORK_DIR / "score"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"official_{pred.stem}.txt"

    cmd = [
        sys.executable,
        "-u",
        str(HERE / "evaluation_ex.py"),
        "--db_root_path",
        str(MD_DIR / "dev_databases") + os.sep,
        "--predicted_sql_path",
        str(pred),
        "--ground_truth_path",
        str(MD_DIR / "mini_dev_sqlite_gold.sql"),
        "--diff_json_path",
        str(diff_json),
        "--num_cpus",
        str(args.num_cpus),
        "--meta_time_out",
        str(args.timeout),
        "--sql_dialect",
        "SQLite",
        "--output_log_path",
        str(log_path),
    ]
    print("运行：" + " ".join(cmd))
    print("-" * 76)
    # evaluation_ex.py 以顶层模块方式 import evaluation_utils，必须在本目录下运行
    result = subprocess.run(cmd, cwd=str(HERE))
    print("-" * 76)
    if log_path.exists():
        print(f"官方评测日志 -> {log_path}")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
