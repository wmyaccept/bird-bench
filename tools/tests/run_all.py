# -*- coding: utf-8 -*-
"""一键跑完所有回归测试，并打印真实断言数。

⭐ 数字只出现在**输出**里，不写进文档（文档手抄数字必然过期 —— 见 casebook 第 29/30/31 轮）。

用法：python tools/tests/run_all.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SUITES = [
    ("文档一致性（P1/P5/P6/P7/P9）", [PY, "tools/tests/check_docs.py"]),
    ("库档案整份送达（P4）", [PY, "tools/tests/check_brief_p4.py"]),
    ("惯例卡片可刷新且同源（P2）", [PY, "tools/tests/check_write_card.py"]),
    # 类③「失败开放」：喂不存在的键必须 rc=2（跑真 CLI，不是单元桩）
    ("失败关闭（P19：不存在的键）", [PY, "tools/tests/check_failclosed.py"]),
    ("数据集健壮性（T2：字段缺失/金标为空）", [PY, "tools/tests/check_dataset_robustness.py"]),
]
# 扩展套件要 node，单独放；⭐ 套件个数**只有这里一个出处**（N_SUITES），
# 文档 / check_docs 想引用就引用它，别自己数（手抄必然漂移）。
EXT_SUITE = ("扩展端到端（闸门/参数/隔离）", ["node", "tools/tests/extension_smoke.cjs"])
N_SUITES = len(SUITES) + 1


def main() -> int:
    total_pass = total_fail = 0
    failed_suites = []

    # fixture 是 extension_smoke 的测试床（隔离目录，绝不碰真答案）
    subprocess.run([PY, "tools/tests/make_fixture.py"], cwd=ROOT, capture_output=True)

    suites = list(SUITES) + [EXT_SUITE]
    for name, cmd in suites:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"通过 (\d+) / 失败 (\d+)", out)
        if m:
            p, f = int(m.group(1)), int(m.group(2))
            total_pass += p
            total_fail += f
            mark = "✅" if f == 0 else "❌"
            print(f"  {mark} {name:28s} 通过 {p:3d} / 失败 {f}")
            if f:
                failed_suites.append(name)
                print("\n".join(l for l in out.splitlines() if l.strip().startswith("❌")))
        else:
            total_fail += 1
            failed_suites.append(name)
            print(f"  ❌ {name}: 没解析到结果（脚本本身出错？）\n{out[-500:]}")

    print(f"\n════ 合计 通过 {total_pass} / 失败 {total_fail} ════")
    if failed_suites:
        print("失败的套件：" + "、".join(failed_suites))
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
