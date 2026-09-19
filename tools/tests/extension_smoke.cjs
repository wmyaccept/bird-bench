/**
 * bird-sql extension 的端到端冒烟测试（P0 验收）。
 *
 * 做法：用 jiti 把 `.pi/extensions/bird-sql/index.ts` 真正加载起来，喂一个假的 pi API，
 * 然后逐个调用工具 —— 走的是 pi 在生产里用的**同一条执行路径**（真实 spawn `tools/bird.py`），
 * 不经过 LLM、不花任何 API 额度。
 *
 * 全部打在 fixture 数据集上（`BIRD_WORK_DIR` 指向 fixture/work），绝不碰真实作答文件。
 * 每一项都断言；有任何一项失败 → 退出码 1。
 *
 * 用法：
 *     python tools/tests/make_fixture.py          # 先造 fixture（幂等）
 *     node   tools/tests/extension_smoke.cjs      # 再跑本测试
 *
 * 环境变量（都有默认值）：
 *     BIRD_TEST_FIXTURE   fixture 根目录，默认 D:/tmp/bird/fixture
 *     BIRD_TEST_PROJECT   项目根目录，默认本文件的上两级
 *     PI_PACKAGE          pi-coding-agent 安装目录
 */
const path = require("node:path");
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");

const PI =
  process.env.PI_PACKAGE ||
  "C:/Users/30538/AppData/Roaming/npm/node_modules/@earendil-works/pi-coding-agent";
const PROJECT =
  process.env.BIRD_TEST_PROJECT || path.resolve(__dirname, "..", "..");
const FIXTURE = process.env.BIRD_TEST_FIXTURE || "D:/tmp/bird/fixture";
const PYTHON = process.env.BIRD_PYTHON || "D:/python/python";

process.env.BIRD_HOME = PROJECT;
process.env.BIRD_DATA_DIR = FIXTURE;
process.env.BIRD_WORK_DIR = FIXTURE + "/work";
process.env.BIRD_PYTHON = PYTHON;

const PROBE_LOG = FIXTURE + "/work/probe_log.jsonl";
const ANSWERS = FIXTURE + "/work/answers.json";

let pass = 0;
let fail = 0;
function check(name, cond, detail = "") {
  if (cond) {
    pass++;
    console.log(`  ✅ ${name}`);
  } else {
    fail++;
    console.log(`  ❌ ${name} ${detail}`);
  }
}

(async () => {
  if (!fs.existsSync(ANSWERS)) {
    console.error(`fixture 不存在：${ANSWERS}\n请先跑：python tools/tests/make_fixture.py`);
    process.exit(2);
  }

  const { createJiti } = require(path.join(PI, "node_modules", "jiti"));
  const jiti = createJiti(__filename, {
    moduleCache: false,
    alias: {
      typebox: path.join(PI, "node_modules", "typebox", "build", "index.mjs"),
      "@earendil-works/pi-coding-agent": path.join(PI, "dist", "index.js"),
    },
  });

  const mod = await jiti.import(path.join(PROJECT, ".pi/extensions/bird-sql/index.ts"));
  const factory = mod.default ?? mod;
  const tools = new Map();
  const pi = {
    on: () => {},
    registerTool: (def) => tools.set(def.name, def),
    registerCommand: () => {},
  };
  await factory(pi);

  console.log("── 工具注册");
  const expected = [
    "bird_info", "bird_list", "bird_question", "bird_schema", "bird_query",
    "bird_find", "bird_answer", "bird_score", "bird_attrs",
    "bird_brief", "bird_cols", "bird_conventions", "bird_audit",
  ];
  for (const n of expected) check(`注册了 ${n}`, tools.has(n));

  const ctx = { cwd: PROJECT, ui: { notify: () => {} } };
  async function call(name, params) {
    const tool = tools.get(name);
    if (!tool) throw new Error(`${name} 未注册`);
    try {
      const r = await tool.execute("smoke", params, undefined, undefined, ctx);
      const text = (r.content ?? []).map((c) => c.text ?? "").join("");
      return { ok: true, text };
    } catch (err) {
      return { ok: false, text: err.message };
    }
  }

  fs.rmSync(PROBE_LOG, { force: true }); // 探针日志从零开始
  const answersBefore = fs.readFileSync(ANSWERS, "utf8");
  const CHECKS_CORE = "1,1b,2,2b,8,8b,12,13,13b";
  const ATTRS_Q1 = "the least consumption"; // 1472 题干原文
  const ATTRS_Q2 = "how many customers";    // 1473 题干原文

  console.log("\n── 1. 新工具真的能跑（不是只有名字）");
  let r = await call("bird_brief", { db_id: "demo", dataset: "minidev" });
  check("bird_brief 输出含知识库推送标题", r.ok && /知识库推送/.test(r.text), r.text.slice(0, 120));
  check("bird_brief 带出了库档案", r.ok && /库档案|必查/.test(r.text));

  r = await call("bird_cols", { db_id: "demo", pattern: "Curr|Seg", samples: 2 });
  check("bird_cols 跑通且列出命中列", r.ok && /Currency|Segment/.test(r.text), r.text.slice(0, 160));

  r = await call("bird_conventions", { dataset: "minidev", examples: 1 });
  check("bird_conventions 跑通", r.ok && /惯例|计数形态|主表/.test(r.text), r.text.slice(0, 160));

  r = await call("bird_audit", { dataset: "minidev", list: 1 });
  check("bird_audit 跑通且含合规行", r.ok && /合规/.test(r.text), r.text.slice(0, 160));

  r = await call("bird_info", { dataset: "dev2025" });
  check("dataset 参数生效（能看到 dev2025 的进度）", r.ok && /dev2025/.test(r.text), r.text.slice(0, 200));

  console.log("\n── 2. 闸门 1（探针覆盖）：--for 真的写进日志了吗");
  check("清空后 probe_log 为空", !fs.existsSync(PROBE_LOG) || fs.readFileSync(PROBE_LOG, "utf8").trim() === "");
  r = await call("bird_answer", { idx: 1, sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers" });
  check("无探针提交被拒绝", !r.ok && /闸门 1/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_query", {
    db_id: "demo",
    sql: "SELECT DISTINCT Currency FROM customers",
    for_idx: 1,
  });
  check("bird_query 带 for_idx 跑通", r.ok, r.text.slice(0, 160));
  const probeText = fs.existsSync(PROBE_LOG) ? fs.readFileSync(PROBE_LOG, "utf8") : "";
  check("探针写进了 probe_log", /"kind": "run"/.test(probeText), probeText.trim());
  check("探针带了数据集字段 ds", /"ds": "minidev"/.test(probeText), probeText.trim());

  r = await call("bird_schema", { db_id: "demo", for_idx: 1 });
  check("bird_schema（tables 路径）能以探针留痕", r.ok && /已记探针/.test(r.text), r.text.slice(-160));
  r = await call("bird_schema", { db_id: "demo", descriptions: true, for_idx: 1 });
  check("bird_schema（desc 路径）能以探针留痕", r.ok && /已记探针/.test(r.text), r.text.slice(-160));
  r = await call("bird_find", { db_id: "demo", word: "LAM", for_idx: [0, 1] });
  check("bird_find 带 for_idx 数组留痕（一次记多题）", r.ok && /已记探针/.test(r.text), r.text.slice(-160));
  const probeLines = fs.readFileSync(PROBE_LOG, "utf8").trim().split("\n");
  check("探针条数 ≥ 5（一题多条也要各记）", probeLines.length >= 5, `实际 ${probeLines.length}`);

  console.log("\n── 3. 闸门 2（形状预演）");
  r = await call("bird_answer", { idx: 1, sql: "SELECT COUNT(*) FROM customers" });
  check("缺形状声明被拒绝", !r.ok && /闸门 2/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", { idx: 1, sql: "/* shape: 9x9 */ SELECT COUNT(*) FROM customers" });
  check("形状不符被拒绝", !r.ok && /形状预演不符|拒绝记录/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: ?x1 */ SELECT COUNT(*) FROM customers",
    checks: CHECKS_CORE,
    attrs: ATTRS_Q1,
  });
  check("? 行数 → 只校验列数，通过", r.ok && /已记录第 1 题/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", { idx: 2, sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers" });
  check(
    "闸门 1 不会被闸门 2 绕过（2 号题从没探过，形状写对了也交不上）",
    !r.ok && /闸门 1/.test(r.text),
    r.text.slice(0, 200),
  );

  console.log("\n── 3c. P13：形状校验必须用完整结果，--max-rows 只管预览");
  const rowsCTE = (n) =>
    `WITH RECURSIVE s(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM s WHERE x<${n}) SELECT x FROM s`;
  r = await call("bird_answer", { idx: 1, sql: `/* shape: 21x1 */ ${rowsCTE(21)}`, checks: CHECKS_CORE, attrs: ATTRS_Q1 });
  check(
    "真 21 行按 21 声明能通过（修前会被截断成「实测 20 行」而误拒）",
    r.ok && /执行通过：21 行/.test(r.text),
    r.text.slice(0, 200),
  );
  r = await call("bird_answer", { idx: 1, sql: `/* shape: 20x1 */ ${rowsCTE(21)}` });
  check("反向守卫：真 21 行却声明 20 行仍被拒（闸门没被削弱）", !r.ok, r.text.slice(0, 200));
  r = await call("bird_answer", { idx: 1, sql: `/* shape: 50001x1 */ ${rowsCTE(50001)}`, checks: CHECKS_CORE, attrs: ATTRS_Q1 });
  check(
    "超过一次取回的上限时用 COUNT(*) 把真实行数数准（50001 行按 50001 声明通过）",
    r.ok && /50001 行/.test(r.text),
    r.text.slice(0, 220),
  );
  r = await call("bird_answer", { idx: 1, sql: `/* shape: 50000x1 */ ${rowsCTE(50001)}` });
  check("超上限时行数也照样校验（真 50001 行声明 50000 仍被拒）", !r.ok, r.text.slice(0, 220));

  console.log("\n── 3d. P10：闸门 3（勾选留痕）");
  r = await call("bird_answer", { idx: 1, sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers" });
  check("不写 checks → 闸门 3 拒绝", !r.ok && /闸门 3/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: "1,1b,2,8,12,13",
  });
  check("核心条目缺一个（少 2b）→ 拒绝", !r.ok && /核心条目没勾齐/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: `0,${CHECKS_CORE},4,5,10`,
    attrs: ATTRS_Q1,
  });
  check("勾齐核心条目即通过", r.ok && /已记录第 1 题/.test(r.text), r.text.slice(0, 200));
  check(
    "勾选写进了 probe_log（kind=checks，audit 可统计）",
    /"kind": "checks"/.test(fs.readFileSync(PROBE_LOG, "utf8")),
  );

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: `${CHECKS_CORE},99`,
  });
  check(
    "编造条目号 → 拒绝（条目表由 checklist.md 现场解析，不是工具里写死的）",
    !r.ok && /不存在/.test(r.text),
    r.text.slice(0, 200),
  );

  // ⭐ 反向：checks 记录本身不能当探针用（否则一次失败的提交会给闸门 1 发假通行证）
  //   用 2 号题：它在本次跑里还没有任何真实探针（1 号题在 §2 就被 bird_find 留过痕了）
  fs.appendFileSync(
    PROBE_LOG,
    JSON.stringify({ idx: 2, db: "demo", ds: "minidev", kind: "checks", detail: CHECKS_CORE, ts: "2000-01-01 00:00:00" }) + "\n",
  );
  r = await call("bird_answer", {
    idx: 2,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: CHECKS_CORE,
  });
  check("checks 记录不算探针（2 号题仍被闸门 1 拦住）", !r.ok && /闸门 1/.test(r.text), r.text.slice(0, 200));

  console.log("\n── 3e. P16：闸门 4（属性清单）—— 专治「少给列」");
  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: CHECKS_CORE,
  });
  check("不写 attrs → 闸门 4 拒绝", !r.ok && /闸门 4/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: CHECKS_CORE,
    attrs: `${ATTRS_Q1}|the least consumption`,
  });
  check("清单 2 条但只有 1 列 → 拒绝（条数必须 == 列数）", !r.ok && /清单 2 条/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: CHECKS_CORE,
    attrs: "number of customers",
  });
  check(
    "清单条目必须在题干里逐字存在（编造/概括 → 拒绝）",
    !r.ok && /找不到原话/.test(r.text),
    r.text.slice(0, 200),
  );

  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x2 */ SELECT COUNT(*), COUNT(*) FROM customers",
    checks: CHECKS_CORE,
    attrs: `${ATTRS_Q1}|${ATTRS_Q1}`,
  });
  check("清单条目重复 → 拒绝（不许拿重复凑条数）", !r.ok && /重复/.test(r.text), r.text.slice(0, 200));

  r = await call("bird_attrs", { idx: 1 });
  check("bird_attrs 跑通并给出列数下界", r.ok && /列数下界/.test(r.text), r.text.slice(0, 200));
  check(
    "bird_attrs 摆出本库×难度的金标列数分布（做题前唯一的合法形状先验）",
    r.ok && /金标列数分布/.test(r.text),
    r.text.slice(0, 300),
  );

  // 4b：列数下界会拦住「少给列」——测试自己造状态：把 fixture 金标临时改成多列
  const GOLD = FIXTURE + "/MINIDEV/mini_dev_sqlite_gold.sql";
  const goldBefore = fs.readFileSync(GOLD, "utf8");
  fs.writeFileSync(
    GOLD,
    goldBefore
      .split("\n")
      .map((l) => (l.trim() ? l.replace(/^SELECT /, "SELECT 1 AS a, 2 AS b, 3 AS c, ") : l))
      .join("\n"),
  );
  r = await call("bird_attrs", { idx: 1 });
  check(
    "金标变 4 列后下界跟着升（先验来自已提交题的金标形状）",
    r.ok && /列数下界 = 4/.test(r.text),
    r.text.slice(0, 200),
  );
  r = await call("bird_answer", {
    idx: 1,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    checks: CHECKS_CORE,
    attrs: ATTRS_Q1,
  });
  check(
    "只给 1 列、低于列数下界 → 闸门 4 拒绝（少给列被机器拦住）",
    !r.ok && /列数下界/.test(r.text),
    r.text.slice(0, 200),
  );
  fs.writeFileSync(GOLD, goldBefore); // 按字节还原，后面的断言不受影响

    console.log("\n── 4. force 逃生口");
  r = await call("bird_answer", {
    idx: 2,
    sql: "/* shape: 1x1 */ SELECT COUNT(*) FROM customers",
    force: true,
  });
  check("force=true 能跳过闸门并记录", r.ok && /已记录第 2 题/.test(r.text), r.text.slice(0, 200));
  check("force 留痕（audit 可统计强制率）", /"kind": "force"/.test(fs.readFileSync(PROBE_LOG, "utf8")));

  console.log(String.fromCharCode(10) + "── 4b. P14：force 记录不能冒充探针（闸门 1 不许自我满足）");
  const os = require("node:os");
  const cli2 = (args, extraEnv = {}) =>
    execFileSync(PYTHON, [path.join(PROJECT, "tools", "bird.py"), ...args], {
      cwd: PROJECT,
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        BIRD_WORK_DIR: FIXTURE + "/work",
        ...extraEnv,
      },
    });
  let gate1Blocked = false;
  let gate1Msg = "";
  try {
    // 3 号题从未被探过；刚在上面被 --force 硬交过一次 ⇒ 旧实现下这里会放行
    cli2(["answer", "2", "/* shape: 1x1 */ SELECT COUNT(*) FROM customers", "--checks", CHECKS_CORE]);
  } catch (err) {
    gate1Msg = String(err.stderr || err.stdout);
    gate1Blocked = /闸门 1/.test(gate1Msg);
  }
  check("用 --force 交过一次之后，不用 force 再交同一题仍被闸门 1 拦住", gate1Blocked, gate1Msg.slice(0, 200));
  check("错误信息说清了哪些动作才算探针（checks/force 不算）", /checks、force 都不算/.test(gate1Msg));
  const auditOut = cli2(["audit"]);
  check("audit 仍统计 --force（指标没被顺手删掉）", /--force [1-9]/.test(auditOut), auditOut.slice(0, 200));
  check(
    "audit 的「探针覆盖」不再把 force 过的题算成已探过（无探针 idx 里含 2）",
    /无探针 idx：\[[^\]]*\b2\b/.test(auditOut),
    auditOut.slice(0, 400),
  );

  console.log(String.fromCharCode(10) + "── 4c. P10 加固：核心标记被清空时不许静默降级");
  // 先给 2 号题一个真探针（否则会先被闸门 1 拦住，测不到闸门 3）
  cli2(["run", "demo", "SELECT CustomerID FROM customers", "--for", "2"]);
  const nocore = fs.mkdtempSync(path.join(os.tmpdir(), "bird-nocore-"));
  fs.writeFileSync(
    path.join(nocore, "checklist.md"),
    fs
      .readFileSync(path.join(PROJECT, ".pi", "skills", "bird-sql", "references", "checklist.md"), "utf8")
      .replace(/<!-- core -->/g, ""),
  );
  let coreGuard = "";
  try {
    cli2(["answer", "2", "/* shape: 1x1 */ SELECT COUNT(*) FROM customers", "--checks", CHECKS_CORE], {
      BIRD_REFS: nocore,
    });
  } catch (err) {
    coreGuard = String(err.stderr || err.stdout);
  }
  check(
    "剥掉全部 `<!-- core -->` → 拒绝并报出 checklist.md 路径（fail-closed）",
    /核心条目标记/.test(coreGuard) && /checklist\.md/.test(coreGuard),
    coreGuard.slice(0, 200),
  );
  let coreForce = "";
  try {
    coreForce = cli2(["answer", "2", "/* shape: 1x1 */ SELECT COUNT(*) FROM customers", "--force"], {
      BIRD_REFS: nocore,
    });
  } catch (err) {
    coreForce = String(err.stderr || err.stdout);
  }
  check("同一条件下 --force 仍是唯一出口（且能交上）", /已记录第 2 题/.test(coreForce), coreForce.slice(0, 200));

  console.log("\n── 5. 数据集隔离（idx 重叠不能假通过）");
  const cli = (args) =>
    execFileSync(PYTHON, [path.join(PROJECT, "tools", "bird.py"), ...args], {
      cwd: PROJECT,
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        BIRD_WORK_DIR: FIXTURE + "/work",
        BIRD_DATA_DIR: undefined, // ★ 用真实 data/（fixture 里没有 DEV 集）
      },
    });
  let isolated = false;
  try {
    cli(["--dataset", "dev2025", "answer", "0", "/* shape: 1x1 */ SELECT 1"]);
  } catch (err) {
    isolated = /闸门 1/.test(String(err.stderr || err.stdout));
  }
  check("minidev 的 0 号探针不能给 dev2025 的 0 号题用", isolated);
  check(
    "dev2025 的答案文件没被创建（确实拦在写入之前）",
    !fs.existsSync(FIXTURE + "/work/answers_dev2025.json"),
  );

  console.log("\n── 5b. 工具参数 schema（provider 兼容性）");
  const qSchema = JSON.stringify(tools.get("bird_query").parameters);
  const aSchema = JSON.stringify(tools.get("bird_answer").parameters);
  check("bird_query schema 含 for_idx", /for_idx/.test(qSchema));
  check("bird_query schema 含 dataset", /dataset/.test(qSchema));
  check("bird_answer schema 含 force", /force/.test(aSchema));
  check("bird_answer schema 含 attrs（闸门 4 参数）", /attrs/.test(aSchema));

  console.log("\n── 6. fixture 只被动了该动的两题");
  const answersAfter = JSON.parse(fs.readFileSync(ANSWERS, "utf8"));
  check(
    "只有 0 / 1 / 2 三个键（没写出别的题）",
    JSON.stringify(Object.keys(answersAfter).sort()) === JSON.stringify(["0", "1", "2"]),
    JSON.stringify(Object.keys(answersAfter)),
  );
  // ⭐ 不许假设"进来时 fixture 恰好有几个键"（run_all 里别的套件可能先跑过、
  //    甚至已经答过同一题）——只断言"我这道题确实落盘了"
  check(
    "本套件作答的 idx 2 确实落盘",
    Object.prototype.hasOwnProperty.call(answersAfter, "2"),
    JSON.stringify(Object.keys(answersAfter)),
  );
  check("SQL 里保留了形状声明（导出时可剥）", /shape:/.test(answersAfter["1"]));

  console.log(String.fromCharCode(10) + "── 7. P4 回归：库档案整份送达（不再按小节名丢内容）");
  r = await call("bird_brief", { db_id: "card_games" });
  check("brief 声明推的是整份档案", r.ok && /整份档案/.test(r.text), r.text.slice(0, 200));
  check("之前永远送不到的『值域陷阱』现在送达", r.ok && /值域陷阱/.test(r.text));
  check("『交题前必查』小节照旧在", r.ok && /交题前必查/.test(r.text));
  check("『惯例卡片』小节照旧在", r.ok && /惯例卡片/.test(r.text));
  r = await call("bird_brief", { db_id: "thrombosis_prediction" });
  check("thrombosis 的『补充（第 24 轮…）』也送达", r.ok && /补充（第 24 轮/.test(r.text), r.text.slice(0, 200));

  console.log(String.fromCharCode(10) + "── 9. P8 回归：从 SKILL.md 搬进 references 的知识仍被推到决策点");
  r = await call("bird_brief", { step: "7" });
  check("brief --step 7 仍推得到「口径实验」", r.ok && /口径实验/.test(r.text), r.text.slice(0, 160));
  check("brief --step 7 仍推得到「挂起清单」集中复盘", r.ok && /挂起清单/.test(r.text));
  check("brief --step 7 仍推得到按类归因（≥2 道才毕业）", r.ok && /同一类 ≥2 道/.test(r.text));
  // ⭐ P18：未知 step 必须失败关闭（旧行为：静默返回“没有片段”，看起来像这一步没东西可读）
  r = await call("bird_brief", { step: "9" });
  check("brief --step 9（不存在）报错，而不是静默空手而归",
        !r.ok && /没有 step=9/.test(r.text), r.text.slice(0, 200));
  check("报错里列出了真实可用的步骤", /实际有内容的步骤/.test(r.text));

  console.log(String.fromCharCode(10) + "── 8. P2 回归：卡片能被工具刷新（参数真的接通）");
  const cSchema = JSON.stringify(tools.get("bird_conventions").parameters);
  check("bird_conventions schema 含 write_card", /write_card/.test(cSchema));
  check("bird_conventions schema 含 all", /"all"/.test(cSchema));
  r = await call("bird_conventions", { dataset: "minidev", db: "demo", write_card: true });
  check(
    "fixture 没有 db/demo.md 时报错清楚（证明 --write-card 传到了后端）",
    !r.ok && /档案/.test(r.text),
    r.text.slice(0, 300),
  );

  console.log(`\n════ 通过 ${pass} / 失败 ${fail} ════`);
  if (fail) process.exit(1);
})();
