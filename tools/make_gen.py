#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 `data/GEN/gen.json`：泛化测量用的「无档案新库」题集（官方 train 集抽样）。

为什么要有它：11 份库档案占了决策路径近一半的字节，「换库之后通用层还有多少增益」是唯一
没被验证过的假设。这个脚本把那次测量变成**可复现**的（固定 seed），而不是一次性实验。
结论与局限见 `.pi/skills/bird-sql/references/calibration.md` 的「泛化实测」小节。

数据准备（两步，都不是这个脚本能代劳的联网动作）：
    1. 题目：官方 train 集 9428 题 / 95 库 —— HF `ShHugging/BIRD-SQL-TRAIN` 的 `train.json`
       （OSS 上的 `train.zip` 是 8.9 GB，别下）。
    2. 库：HF `CChurney/bird-train-databases` 按库分目录，单库直下即可
       （本测量用的是 `trains`，2 表 63 行），放到 `data/GEN/databases/<db_id>/<db_id>.sqlite`。
    然后用 `tools/bird.py --dataset gen info` 验证管线（`gen` 数据集已在后端注册，`gold: None`）。

用法：
    python tools/make_gen.py --train D:/tmp/bird/bird_train.json            # 默认库 trains / 20 题
    python tools/make_gen.py --train ... --db music_tracker --per-arm 10
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="从官方 train 集抽一个库的题，生成泛化测量题集")
    ap.add_argument("--train", required=True, help="官方 train.json 路径（含 question/evidence/SQL/db_id）")
    ap.add_argument("--db", default="trains", help="要抽的库（必须**不是** dev 那 11 个库，否则失去意义）")
    ap.add_argument("--per-arm", type=int, default=10, help="每臂题数；idx 0..n-1 零点臂 / n..2n-1 skill 臂")
    ap.add_argument("--seed", type=int, default=20260920, help="固定 seed ⇒ 抽样可复现")
    ap.add_argument("--out", default=None, help="默认 data/GEN/gen.json")
    args = ap.parse_args()

    train = json.loads(pathlib.Path(args.train).read_text(encoding="utf-8"))
    pool = [q for q in train if q.get("db_id") == args.db]
    need = 2 * args.per_arm
    if len(pool) < need:
        sys.exit(f"{args.db} 在 train 集里只有 {len(pool)} 题，不够 {need} 题（换库或减 --per-arm）")

    order = list(range(len(pool)))
    random.Random(args.seed).shuffle(order)
    picked = [pool[i] for i in order[:need]]

    out = []
    for i, q in enumerate(picked):
        out.append({
            "question_id": f"gen_{args.db}_{i:02d}",
            "db_id": q["db_id"],
            "question": q["question"],
            "evidence": q.get("evidence", ""),
            "SQL": q["SQL"],                                  # 金标随题写入（评分靠它）
            "arm": "zeroshot" if i < args.per_arm else "skill",
        })

    target = pathlib.Path(args.out) if args.out else ROOT / "data" / "GEN" / "gen.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"✓ {target}：{len(out)} 题（{args.per_arm} 零点臂 + {args.per_arm} skill 臂），池子 {len(pool)} 题")
    print("（金标已写进 SQL 字段，**不打印**到屏幕 —— 零点臂必须先交完再跑探针）")
    print()
    print("── 题目清单（不含 SQL）──")
    for i, q in enumerate(out):
        print(f"[{i:02d}][{q['arm']}] {q['question']}")
        if q["evidence"]:
            print(f"        evidence: {q['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
