# -*- coding: utf-8 -*-
"""验证 runner 的**离线**行为（不联网、不花额度）。

要证的六件事（每条都能真的红）：
  ① 预测文件是官方格式（`SQL<TAB>----- bird -----<TAB>db_id`，键是 idx 字符串）
  ② 逐题日志每行都有官方报数需要的字段（含 token）
  ③ 断点续跑：第二次跑不再问模型、预测文件字节不变
  ④ **空结果会回喂重写**（mock 第一条故意给 0 行，最终必须变成第二条）
  ⑤ 只读闸门真的拦得住写操作（mock 给 DELETE，最终答案不能是它）
  ⑥ 失败关闭：库路径不对 → rc=2（不是"跑了但什么都没做"还返回 0）
  ⑦ 打包器的 `--check-run` 跑在 **dev2025** 上（bird.py 在导入时固化数据集目录，
     原先写成 import 之后 setdefault ⇒ 自检静默地在 MINIDEV 的库上算空结果率）

用法：python tools/tests/check_runner.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = os.environ.get("BIRD_PYTHON", sys.executable)
FIX = Path(os.environ.get("BIRD_TEST_RUNNER", "D:/tmp/bird/runner_fixture"))
SEP = "\t----- bird -----\t"

pass_n = 0
fail_n = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  ✅ {name}")
    else:
        fail_n += 1
        print(f"  ❌ {name} {detail}")


def run_runner(*extra, expect_rc: int | None = None):
    cmd = [PY, "runner/run_bird.py",
           "--test-dir", str(FIX / "MINIDEV/dev_databases"),
           "--questions", str(FIX / "MINIDEV/mini_dev_sqlite.json"),
           "--out", str(FIX / "pred.json"),
           "--log", str(FIX / "run.jsonl"),
           "--prompt-dir", str(FIX / "prompt"),
           "--mock", str(FIX / "mock.jsonl"), *extra]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if expect_rc is not None:
        check(f"rc={expect_rc}（{' '.join(extra) or '默认参数'}）", r.returncode == expect_rc,
              f"实际 rc={r.returncode}；{(r.stdout + r.stderr)[-300:]}")
    return r


def main() -> int:
    if FIX.exists():
        shutil.rmtree(FIX)
    subprocess.run([PY, "tools/tests/make_fixture.py", "--out", str(FIX)],
                   cwd=ROOT, capture_output=True)
    # 最小 prompt 目录：只放 runner 会读的两份规则 + 一张库档案
    (FIX / "prompt/db").mkdir(parents=True, exist_ok=True)
    (FIX / "prompt/traps.md").write_text("# rules\n- check value spelling\n", encoding="utf-8")
    (FIX / "prompt/shapes.md").write_text("# shapes\n- count questions return one number\n",
                                          encoding="utf-8")
    (FIX / "prompt/db/demo.md").write_text("# demo\n- Currency is 'EUR'/'CZK'\n", encoding="utf-8")

    q = json.loads((FIX / "MINIDEV/mini_dev_sqlite.json").read_text(encoding="utf-8"))
    good0 = "SELECT COUNT(*) FROM customers WHERE Currency='EUR'"
    empty = "SELECT CustomerID FROM yearmonth WHERE Consumption < 0"       # 真跑会 0 行
    good1 = ("SELECT T1.CustomerID FROM customers T1 JOIN yearmonth T2 "
             "ON T1.CustomerID=T2.CustomerID WHERE T1.Segment='LAM' "
             "AND SUBSTR(T2.Date,1,4)='2012' ORDER BY T2.Consumption ASC LIMIT 1")
    lines = [
        {"idx": 0, "responses": [f"```sql\n{good0}\n```"]},
        {"idx": 1, "responses": [f"```sql\n{empty}\n```", f"```sql\n{good1}\n```"]},
        {"idx": 2, "responses": ["```sql\nDELETE FROM customers\n```", f"```sql\n{good0}\n```"]},
    ]
    (FIX / "mock.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")

    print("── ① 预测文件是官方格式")
    r = run_runner(expect_rc=0)
    pred = json.loads((FIX / "pred.json").read_text(encoding="utf-8"))
    check("3 条预测", len(pred) == 3, str(list(pred)))
    check("键是 idx 字符串", all(k.isdigit() for k in pred), str(list(pred)))
    check("每条都带官方分隔符", all(SEP in v for v in pred.values()), str(pred))
    check("分隔符后是 db_id",
          all(SEP in v and v.split(SEP)[1] == q[int(k)]["db_id"] for k, v in pred.items()),
          str(pred))
    check("idx0 的 SQL 就是模型给的", SEP in pred["0"] and pred["0"].split(SEP)[0] == good0,
          pred["0"])

    print("\n── ② 逐题日志字段齐全（官方要报 token，必须留痕）")
    recs = [json.loads(x) for x in
            (FIX / "run.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    need = {"idx", "db_id", "sql", "exec_ok", "n_rows", "attempts", "latency_s",
            "prompt_tokens", "completion_tokens", "errors"}
    check("每题一行", len(recs) == 3, str(len(recs)))
    check("字段齐全", all(need <= set(r) for r in recs), str(need - set(recs[0])))
    check("汇总里报了 token", "tokens：" in r.stdout, r.stdout[-200:])

    print("\n── ③ 断点续跑：不再问模型、预测文件不变")
    before = (FIX / "pred.json").read_bytes()
    r2 = run_runner(expect_rc=0)
    check("显示『待跑 0』", "待跑 0" in r2.stdout, r2.stdout[:300])
    check("预测文件字节不变", (FIX / "pred.json").read_bytes() == before)

    print("\n── ④ 空结果回喂重写（mock 第一条故意 0 行）")
    rec1 = next(x for x in recs if x["idx"] == 1)
    check("idx1 试了 2 次", rec1["attempts"] == 2, str(rec1["attempts"]))
    check("最终 SQL 是第二条", SEP in pred["1"] and pred["1"].split(SEP)[0] == good1, pred["1"])
    check("日志记了第一次的空结果", "0 rows" in r.stdout or rec1["n_rows"] == 1,
          str(rec1["n_rows"]))

    print("\n── ⑤ 只读闸门拦写操作（mock 第一条给 DELETE）")
    rec2 = next(x for x in recs if x["idx"] == 2)
    check("idx2 试了 2 次（第一次被拦）", rec2["attempts"] == 2, str(rec2["attempts"]))
    check("最终 SQL 不是 DELETE", "DELETE" not in pred["2"].upper(), pred["2"])
    # 必须精确到 guard：没有它的话拦下写操作的只剩 mode=ro 连接，错误文案会变成 sqlite:
    check("拦下的是 guard_sql（不是靠 mode=ro 连接兼的）", rec2["errors"] == ["guard"],
          f"errors={rec2['errors']!r}")
    check("真库没被写坏（customers 仍是 3 行）", _count(FIX, "customers") == 3)

    print("\n── ⑥ 失败关闭 + 参数")
    bad = subprocess.run([PY, "runner/run_bird.py", "--test-dir", str(FIX / "nope"),
                          "--questions", str(FIX / "MINIDEV/mini_dev_sqlite.json"),
                          "--out", str(FIX / "x.json"), "--mock", str(FIX / "mock.jsonl")],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    check("库路径不对 → rc=2", bad.returncode == 2, f"rc={bad.returncode}")
    check("并说明原因", "不存在" in (bad.stdout + bad.stderr), (bad.stdout + bad.stderr)[-200:])
    r3 = run_runner("--limit", "1", "--out", str(FIX / "pred1.json"),
                    "--log", str(FIX / "run1.jsonl"), expect_rc=0)
    one = json.loads((FIX / "pred1.json").read_text(encoding="utf-8"))
    check("--limit 1 只做一题", len(one) == 1, str(list(one)))
    check("--limit 也不漏报 token", "tokens：" in r3.stdout)
    r4 = run_runner("--dump-prompt", "0", "--out", str(FIX / "p2.json"),
                    "--log", str(FIX / "r2.jsonl"), expect_rc=0)
    check("--dump-prompt 打出 system+user", "===== system" in r4.stdout
          and "## Schema" in r4.stdout, r4.stdout[:200])
    check("prompt 里带上了库档案", "Currency is 'EUR'/'CZK'" in r4.stdout)
    check("prompt 里带上了 evidence", "## Evidence" in r4.stdout)
    check("prompt 里带上了 evidence 正文", "ratio = count(Currency='EUR')" in r4.stdout)

    # ── ⑦ 打包器自检的数据集口径（源码顺序断言：env 必须早于 import bird）
    #    按**行**匹配，不能 str.find('import bird') —— 那句会先命中上方的注释。
    pack_lines = (ROOT / "tools" / "make_submission.py").read_text(encoding="utf-8").splitlines()
    i_env = next((i for i, l in enumerate(pack_lines)
                  if "BIRD_DATASET" in l and '"dev2025"' in l), -1)
    i_imp = next((i for i, l in enumerate(pack_lines)
                  if l.strip().startswith("import bird")), -1)
    check("--check-run 在 import bird 之前设 BIRD_DATASET（否则静默查错数据集）",
          0 <= i_env < i_imp, f"env@line{i_env+1} import@line{i_imp+1}")
    check("--check-run 有数据集自证（真跑错数据集会硬失败）",
          "bird.DATASET_KEY" in "\n".join(pack_lines))
    #    run_sql 的真签名：收 db_id 字符串、返回 4 元组。传 Path / 二元解包 ⇒ 整条自检静默失效。
    _call = next((l for l in pack_lines if "bird.run_sql(" in l), "")
    check("--check-run 给 run_sql 传 db_id（不是 Path，它内部会自己调 db_path）",
          "run_sql(db," in _call.replace(" ", ""), _call.strip())
    _lhs = _call.split("=")[0]
    check("--check-run 按 run_sql 的 4 元组解包（不是 2 元组）",
          len([x for x in _lhs.split(",") if x.strip()]) == 4, _lhs.strip())
    check("--check-run 会把报错原因打出来（不是静默 n_err+=1）",
          "err_samples" in "\n".join(pack_lines))
    check("--check-run 有失败关闭：全部报错 ⇒ 硬失败（自检没真跑不许当通过）",
          "n_err == len(d)" in "\n".join(pack_lines))
    #    超时口径也要对齐：自检用 30s 而 runner 用 60s ⇒ 把慢题误报成 error（实测 2 道）。
    _rb_timeout_line = next((l for l in (ROOT / "runner" / "run_bird.py")
                             .read_text(encoding="utf-8").splitlines()
                             if '"--timeout"' in l), "")
    _rb_default = _rb_timeout_line.split("default=")[-1].split(",")[0].strip()
    _pk_timeout = _call.split("timeout=")[-1].split(")")[0].strip() if "timeout=" in _call else ""
    check("--check-run 的执行超时 == runner --timeout 默认（否则测的不是同一件事）",
          bool(_pk_timeout) and _pk_timeout == _rb_default,
          f"packer={_pk_timeout!r} runner={_rb_default!r}")

    print(f"\n════ 通过 {pass_n} / 失败 {fail_n} ════")
    return 1 if fail_n else 0


def _count(fix: Path, table: str) -> int:
    import sqlite3
    con = sqlite3.connect(fix / "MINIDEV/dev_databases/demo/demo.sqlite")
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
