/**
 * bird-sql —— 把 BIRD Mini-Dev 的解题流程做成 pi 的原生工具。
 *
 * 分工：
 *   - 这个 extension 负责"能做什么"：读题、看 schema、只读试跑、提交、算分。
 *   - .pi/skills/bird-sql/SKILL.md 负责"怎么做得好"：解题方法论与常见坑。
 *
 * 实现上故意做得很薄：所有 SQLite 操作都交给 tools/bird.py，这样同一套逻辑
 * 在终端里直接跑就能复现（老师复核时不需要装 pi）。
 *
 * 安全设计（写在工具层，而不是指望模型自觉）：
 *   - bird_question 不回传 gold SQL，抄不到答案；
 *   - bird_query 只允许 SELECT/WITH/EXPLAIN，且连接是只读的；
 *   - 输出统一截断，避免把上下文撑爆。
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** 单个工具返回给 LLM 的最大字符数，超过就截断并提示。 */
const MAX_CHARS = 40_000;

// ---------------------------------------------------------------- 环境探测

/** 找到项目根目录：优先 BIRD_HOME，其次从 cwd 逐级向上找 tools/bird.py。 */
function findProjectRoot(cwd: string): string | null {
  const fromEnv = process.env.BIRD_HOME;
  if (fromEnv && existsSync(path.join(fromEnv, "tools", "bird.py"))) {
    return path.resolve(fromEnv);
  }
  let dir = path.resolve(cwd);
  for (;;) {
    if (existsSync(path.join(dir, "tools", "bird.py"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

/** 找一个能用的 python。避开 WindowsApps 里的 Store 假别名。 */
function pythonCandidates(): string[] {
  const list: string[] = [];
  if (process.env.BIRD_PYTHON) list.push(process.env.BIRD_PYTHON);
  if (process.platform === "win32") {
    list.push("python", "python3", "D:\\python\\python.exe", "D:\\python\\python");
  } else {
    list.push("python3", "python");
  }
  return list;
}

function run(
  command: string,
  args: string[],
  options: { cwd: string; timeoutMs?: number; signal?: AbortSignal },
): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = options.timeoutMs
      ? setTimeout(() => {
          child.kill();
        }, options.timeoutMs)
      : undefined;

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      if (timer) clearTimeout(timer);
      if (settled) return;
      settled = true;
      reject(err);
    });
    child.on("close", (code) => {
      if (timer) clearTimeout(timer);
      if (settled) return;
      settled = true;
      resolve({ code, stdout, stderr });
    });
    options.signal?.addEventListener("abort", () => child.kill(), { once: true });
  });
}

class BirdBackend {
  private python: string | null = null;

  constructor(private readonly root: string) {}

  private script(): string {
    return path.join(this.root, "tools", "bird.py");
  }

  /** 探测一次可用的 python，结果缓存。 */
  private async resolvePython(ctx: ExtensionContext): Promise<string> {
    if (this.python) return this.python;
    const tried: string[] = [];
    for (const candidate of pythonCandidates()) {
      try {
        const probe = await run(candidate, ["-c", "import sqlite3,sys;print(sys.version)"], {
          cwd: this.root,
          timeoutMs: 15_000,
        });
        if (probe.code === 0 && probe.stdout.includes(".")) {
          this.python = candidate;
          return candidate;
        }
        tried.push(`${candidate} (exit ${probe.code})`);
      } catch (err) {
        tried.push(`${candidate} (${(err as Error).message})`);
      }
    }
    ctx.ui?.notify?.("bird-sql: 找不到可用的 python", "error");
    throw new Error(
      `找不到可用的 Python 解释器。试过：${tried.join(", ")}。` +
        `请在环境变量 BIRD_PYTHON 里指定 python.exe 的绝对路径。`,
    );
  }

  /** 执行 bird.py 子命令。用 spawn + 参数数组，不经过 shell，SQL 里的引号无需转义。 */
  async call(
    ctx: ExtensionContext,
    args: string[],
    signal?: AbortSignal,
  ): Promise<{ text: string; errorText: string; exitCode: number | null }> {
    const python = await this.resolvePython(ctx);
    const result = await run(python, [this.script(), ...args], {
      cwd: this.root,
      timeoutMs: 180_000,
      signal,
    });
    const stdout = result.stdout.trimEnd();
    const stderr = result.stderr.trimEnd();
    // 失败时只把 stderr 交给模型，别混进 stdout 的噪声
    const errorText = stderr.replace(/^ERROR:\s*/gm, "").trim() || stdout || "命令失败且无输出";
    let text = stdout;
    if (stderr) text += (text ? "\n\n" : "") + "[stderr]\n" + stderr;
    if (text.length > MAX_CHARS) {
      text =
        text.slice(0, MAX_CHARS) +
        `\n\n[输出被截断：共 ${text.length.toLocaleString()} 字符，仅显示前 ${MAX_CHARS.toLocaleString()}。` +
        `请用更精确的参数（--table / --limit / --max-rows）重试]`;
    }
    if (!text) text = "(无输出)";
    return { text, errorText, exitCode: result.code };
  }
}

// ---------------------------------------------------------------- 工具注册

const DB_ID_DESC = "BIRD 数据库 id，例如 debit_card_specializing / formula_1 / superhero";
const IDX_DESC = "题目序号 idx（不是 question_id！用 bird_list 查），从 0 开始";
const DATASET_DESC =
  "数据集：minidev（默认）| dev（旧版 Dev 1534）| dev2025（新版 Dev 1534，当前主战场）。" +
  "三者的题号与作答文件是分开的，统计类工具（bird_conventions / bird_audit）要传对，否则看到的是别集的数字。";
const DatasetType = Type.Optional(Type.String({ description: DATASET_DESC }));
const FOR_DESC =
  "把这次探测记给这些题号（数字 / 逗号串 / 数字数组都可，如 344 或 [344,345]）。" +
  "bird_answer 之前必须有至少一次带 for_idx 的真实探测，否则会被闸门 1 拒绝。";
const ForIdxType = Type.Optional(
  Type.Union([Type.Number(), Type.String(), Type.Array(Type.Number())], { description: FOR_DESC }),
);

/** `--dataset` 是 bird.py 的全局选项，必须放在子命令**之前**。 */
function withDataset(args: string[], dataset?: string): string[] {
  return dataset ? ["--dataset", dataset, ...args] : args;
}

/** for_idx 三种写法统一成 bird.py 的 `--for` 值。 */
function forArg(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (Array.isArray(value)) return value.map((x) => String(x)).join(",");
  const text = String(value).trim();
  return text ? text : null;
}

/** 把 `--for` 插进参数表（只在有值时插）。 */
function withFor(args: string[], value: unknown): string[] {
  const forValue = forArg(value);
  return forValue ? [...args, "--for", forValue] : args;
}

export default function (pi: ExtensionAPI) {
  let backend: BirdBackend | null = null;

  /** 延迟初始化：extension 工厂阶段不要做重活。 */
  function getBackend(ctx: ExtensionContext): BirdBackend {
    if (!backend) {
      const root = findProjectRoot(ctx.cwd);
      if (!root) {
        throw new Error(
          "找不到 BIRD 项目根目录（应包含 tools/bird.py）。" +
            "请在项目目录下启动 pi，或设置环境变量 BIRD_HOME 指向项目根目录。",
        );
      }
      backend = new BirdBackend(root);
    }
    return backend;
  }

  /** 把结果包成 pi 期望的返回值；exitCode 非 0 时抛错，pi 会把 isError 置为 true。 */
  function toResult(
    result: { text: string; errorText: string; exitCode: number | null },
    details: Record<string, unknown> = {},
  ) {
    if (result.exitCode !== 0 && result.exitCode !== null) {
      throw new Error(result.errorText);
    }
    return { content: [{ type: "text" as const, text: result.text }], details };
  }

  pi.registerTool({
    name: "bird_info",
    label: "BIRD Info",
    description:
      "查看 BIRD 数据集状态：数据是否就绪、题目总数、数据库列表、已作答数量。开始解 BIRD 题目时先调用它。",
    promptSnippet: "查看 BIRD 数据集状态、题目总数与作答进度",
    parameters: Type.Object({
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      return toResult(
        await getBackend(ctx).call(ctx, withDataset(["info"], params.dataset), signal),
      );
    },
  });

  pi.registerTool({
    name: "bird_list",
    label: "BIRD List",
    description:
      "按难度或数据库筛选题目，返回每题的 idx / difficulty / db_id / 题干摘要。用它挑下一道要做的题。",
    promptSnippet: "列出 BIRD 题目（可按 --difficulty / --db 筛选），拿到解题要用的 idx",
    promptGuidelines: [
      "解 BIRD 题时用 bird_list 挑题，不要自己猜 idx；题目编号 idx 与 question_id 不是一回事。",
    ],
    parameters: Type.Object({
      db: Type.Optional(Type.String({ description: "只列某个数据库，例如 financial" })),
      difficulty: Type.Optional(
        Type.String({ description: "难度筛选：simple | moderate | challenging" }),
      ),
      offset: Type.Optional(Type.Number({ description: "从第几条开始，默认 0" })),
      limit: Type.Optional(Type.Number({ description: "返回多少条，默认 20" })),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["list"];
      if (params.db) args.push("--db", params.db);
      if (params.difficulty) args.push("--difficulty", params.difficulty);
      args.push("--offset", String(params.offset ?? 0));
      args.push("--limit", String(params.limit ?? 20));
      return toResult(await getBackend(ctx).call(ctx, withDataset(args, params.dataset), signal));
    },
  });

  pi.registerTool({
    name: "bird_question",
    label: "BIRD Question",
    description:
      "读取第 idx 题的题干、evidence（外部知识提示）与所属数据库。刻意不返回 gold SQL，防止抄答案。",
    promptSnippet: "读取 BIRD 第 idx 题的题干与 evidence",
    promptGuidelines: [
      "写 BIRD 题的 SQL 前必须先 bird_question 读 evidence；BIRD 的题目故意留了外部知识，漏读 evidence 是最常见的失分原因。",
      "bird_question 不返回 gold SQL；不要为了找答案去直接读 data/MINIDEV/mini_dev_sqlite.json。",
    ],
    parameters: Type.Object({
      idx: Type.Number({ description: IDX_DESC }),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const result = await getBackend(ctx).call(
        ctx,
        withDataset(["question", String(params.idx)], params.dataset),
        signal,
      );
      return toResult(result, { idx: params.idx });
    },
  });

  pi.registerTool({
    name: "bird_schema",
    label: "BIRD Schema",
    description:
      "看数据库结构。不传 table：返回所有表名、行数、列名（建立全局认知，便宜）。传 table：返回该表的列类型、主键、去重样例值，并附带人工标注的字段描述。也可只取字段描述（descriptions=true）。",
    promptSnippet: "查看 BIRD 数据库的表结构、样例值与人工标注的字段说明",
    promptGuidelines: [
      "解 BIRD 题时先用 bird_schema 不带 table 看清表结构，再对关键表传 table 看样例值和字段说明。",
      "BIRD 的 database_description 是人工标注的字段含义，bird_schema 传 table 或 descriptions=true 可以取到，写 SQL 前应读。",
    ],
    parameters: Type.Object({
      db_id: Type.String({ description: DB_ID_DESC }),
      table: Type.Optional(
        Type.String({ description: "只看某一张表；省略则返回全体表的概览" }),
      ),
      descriptions: Type.Optional(
        Type.Boolean({ description: "true 时只输出人工标注的字段描述 CSV" }),
      ),
      samples: Type.Optional(
        Type.Number({ description: "每列显示几个去重样例值，默认 3，传 0 关闭" }),
      ),
      dataset: DatasetType,
      for_idx: ForIdxType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const bird = getBackend(ctx);
      if (params.descriptions) {
        const args = ["desc", params.db_id];
        if (params.table) args.push("--table", params.table);
        return toResult(
          await bird.call(ctx, withFor(withDataset(args, params.dataset), params.for_idx), signal),
        );
      }
      if (!params.table) {
        const args = withFor(["tables", params.db_id], params.for_idx);
        return toResult(await bird.call(ctx, withDataset(args, params.dataset), signal));
      }
      const args = ["schema", params.db_id, "--table", params.table];
      if (params.samples !== undefined) args.push("--samples", String(params.samples));
      return toResult(
        await bird.call(ctx, withFor(withDataset(args, params.dataset), params.for_idx), signal),
      );
    },
  });

  pi.registerTool({
    name: "bird_query",
    label: "BIRD Query",
    description:
      "在指定数据库上试跑一条只读 SQL（只允许 SELECT / WITH / EXPLAIN，连接强制只读），返回结果表格。用它验证列名、取值格式和 JOIN 路径，再决定最终答案。",
    promptSnippet: "在 BIRD 数据库上只读试跑 SQL，返回结果表格用于验证",
    promptGuidelines: [
      "bird_query 只接受 SELECT/WITH/EXPLAIN；它被故意做成只读，用来验证思路，不要试图用它改数据。",
      "对不确定的列名或脏数据取值，先用 bird_query 配合 SELECT DISTINCT 查一下，再写最终 SQL。",
    ],
    parameters: Type.Object({
      db_id: Type.String({ description: DB_ID_DESC }),
      sql: Type.String({ description: "单条只读 SQL（SELECT / WITH / EXPLAIN）" }),
      max_rows: Type.Optional(Type.Number({ description: "最多返回多少行，默认 50" })),
      dataset: DatasetType,
      for_idx: ForIdxType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["run", params.db_id, params.sql];
      args.push("--max-rows", String(params.max_rows ?? 50));
      return toResult(
        await getBackend(ctx).call(
          ctx,
          withFor(withDataset(args, params.dataset), params.for_idx),
          signal,
        ),
      );
    },
  });

  pi.registerTool({
    name: "bird_find",
    label: "BIRD Find",
    description:
      "概念词反查：题干里的一个词（如 'locally funded'、'continuation'、'Riverside'）究竟躺在哪张表哪一列。遍历所有表的全部列做取值全文匹配，报出命中列、命中行数和真值样本。写 SQL 前用它定列，别用英文语感猜列名。",
    promptSnippet: "反查一个概念词到底在哪张表哪一列（列名靠猜是最常见的失分原因）",
    promptGuidelines: [
      "题干出现'办学类型/资助类型/区码/职务'这类概念名词、而你不确定它对应哪一列时，先 bird_find 反查，再写 SQL。",
      "命中 ≥2 列时不要盲猜：evidence 点名就用它；只有一列命中就用它；多列命中且行集合相同则任选；否则选更专门的那列并把结论记进 db/<库>.md。",
      "概念是'列名'而不是'值'时（如 'district code'）bird_find 查不到，改用 bird_cols 按列名反查。",
      "探测时一定带上 for_idx：它既是 bird_answer 的闸门凭据，也让探测记录进 probe_log —— 复盘时能看出哪些题是没查就交的。",
    ],
    parameters: Type.Object({
      db_id: Type.String({ description: DB_ID_DESC }),
      word: Type.String({ description: "要反查的概念词（可以是片段，如 'funded'、'Continuation'）" }),
      samples: Type.Optional(Type.Number({ description: "每个命中列显示几个真值，默认 3" })),
      dataset: DatasetType,
      for_idx: ForIdxType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["find", params.db_id, params.word];
      if (params.samples !== undefined) args.push("--samples", String(params.samples));
      return toResult(
        await getBackend(ctx).call(
          ctx,
          withFor(withDataset(args, params.dataset), params.for_idx),
          signal,
        ),
      );
    },
  });

  pi.registerTool({
    name: "bird_answer",
    label: "BIRD Answer",
    description:
      "提交第 idx 题的最终 SQL。会先真的在数据库上跑一遍：跑不通会拒绝记录并回报错误，跑得通则把 SQL 记入 answers 文件。" +
      "四道机器闸门：① 本题必须已有带 for_idx 的真实探测；② SQL 最前面必须写 /* shape: 行数x列数 */；" +
      "③ 必须带 checks 列出这次真正勾过的 checklist 条目号（核心条目一条不能少）；" +
      "④ 必须带 attrs 属性清单（逐条抄题干原文，条数 == SELECT 列数；列数低于先验下界也会被拒——专治「少给列」）。",
    promptSnippet: "提交 BIRD 第 idx 题的最终 SQL（先试跑，失败会拒绝记录）",
    promptGuidelines: [
      "bird_answer 的闸门 1：本题在 probe_log 里必须已有记录（只有带 for_idx 的 bird_query/bird_cols/bird_find/bird_schema 才会写入）—— 不能凭空声称'我查过了'。",
      "bird_answer 的闸门 2：SQL 最前面必须写 /* shape: 行数x列数 */，与实测形状不符会被拒绝（列表题不知几行可写 /* shape: ?x2 */ 只校验列数；计数题/极值题必须写数字）。",
      "bird_answer 的闸门 3：checks 里列出的条目号必须都存在于 checklist.md；标了 core 的核心条目无条件适用、少一个就交不上（清单由后端现场解析 checklist.md，缺哪条它会告诉你）。留痕进 probe_log，bird_audit 会统计勾选率与最常被漏掉的条目。",
      "bird_answer 的闸门 4：attrs 是属性清单（用 | 分隔，逐条抄题干/evidence 里的原文片段），条数必须 == SELECT 列数；并且列数不能低于「同模板已提交题的金标列数」与「本库×难度金标列数 P20」的较大者（少给列会被拒）。写 SQL 前先 bird_attrs 看列数先验。",
      "确属一目了然、不必探测的题用 force=true 跳过闸门 —— 会记进 probe_log 并被 bird_audit 统计（强制率本身是要盯的指标）。",
    ],
    parameters: Type.Object({
      idx: Type.Number({ description: IDX_DESC }),
      sql: Type.String({ description: "你为该题定稿的只读 SQL" }),
      checks: Type.Optional(
        Type.String({
          description:
            '闸门 3 凭据：这次真正勾过的 checklist 条目号，逗号分隔（如 "0,1,1b,2,2b,4,5,8,10,12,13"）；核心条目（checklist.md 里带 core 标记的全部条目）必须出现',
        }),
      ),
      attrs: Type.Optional(
        Type.String({
          description:
            '闸门 4 凭据：属性清单，用 | 分隔（如 "the name|the email|the number of orders"）。每条必须是题干/evidence 里的原文片段，条数必须 == SELECT 列数',
        }),
      ),
      force: Type.Optional(
        Type.Boolean({ description: "true = 跳过四道闸门（会记进 probe_log，bird_audit 会统计强制率）" }),
      ),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["answer", String(params.idx), params.sql];
      if (params.checks) args.push("--checks", params.checks);
      if (params.attrs) args.push("--attrs", params.attrs);
      if (params.force) args.push("--force");
      const result = await getBackend(ctx).call(
        ctx,
        withDataset(args, params.dataset),
        signal,
      );
      return toResult(result, { idx: params.idx, sql: params.sql });
    },
  });

  pi.registerTool({
    name: "bird_attrs",
    label: "BIRD Attrs",
    description:
      "做题前看**列数先验**：题干最相似的已提交题给了几列 + 本库×难度的金标列数分布 + 闸门 4 的列数下界。" +
      "「少给列」是本项目最大单类错，写 SQL 前先跑它，再把手头的属性逐条抄成 attrs 清单。",
    promptSnippet: "看 BIRD 第 idx 题的列数先验（同模板已提交题给了几列）",
    promptGuidelines: [
      "题干出现 profile / comprehensive / statistics / including 这类多属性信号时，先 bird_attrs 看列数下界，再决定 SELECT 几列。",
      "它的数据只来自**已提交题**（金标形状没有做题前通道）——对全新模板的第一道题，只能看本库×难度的分布。",
    ],
    parameters: Type.Object({
      idx: Type.Number({ description: IDX_DESC }),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["attrs", String(params.idx)];
      const result = await getBackend(ctx).call(
        ctx,
        withDataset(args, params.dataset),
        signal,
      );
      return toResult(result, { idx: params.idx });
    },
  });

  pi.registerTool({
    name: "bird_score",
    label: "BIRD Score",
    description:
      "按 BIRD 官方口径（Execution Accuracy：预测结果集与金标结果集完全相同）给已提交的作答打分，输出总分、分难度、分数据库的准确率和错题原因。",
    promptSnippet: "按官方 EX 口径给已提交的 BIRD 作答打分",
    promptGuidelines: [
      "做完一批 BIRD 题后用 bird_score 看 EX 与错题原因，再针对错因回去修 SQL，而不是重复猜。",
    ],
    parameters: Type.Object({
      db: Type.Optional(Type.String({ description: "只评某个数据库" })),
      difficulty: Type.Optional(
        Type.String({ description: "只评某个难度：simple | moderate | challenging" }),
      ),
      list_wrong: Type.Optional(
        Type.Number({ description: "列出前 N 道错题及失败原因，默认 10" }),
      ),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["score"];
      if (params.db) args.push("--db", params.db);
      if (params.difficulty) args.push("--difficulty", params.difficulty);
      args.push("--list-wrong", String(params.list_wrong ?? 10));
      return toResult(await getBackend(ctx).call(ctx, withDataset(args, params.dataset), signal));
    },
  });

  // ────────────────────────────────────────── 知识库 / 诊断类工具（第 0.5、3.5、7 步）

  pi.registerTool({
    name: "bird_brief",
    label: "BIRD Brief",
    description:
      "决策点推送：把 references 知识库（带 <!-- push step=N --> 标记的片段）与**整份**当前库档案（必查 + 连接图与坑 + 值域陷阱/补充 + 惯例卡片）推到眼前。换库做第一题之前先跑一次 " +
      "bird_brief db_id=<库>；卡在某一步时用 step 只推那一步。知识库是唯一数据源，所以它推出来的就是文档里写着的。",
    promptSnippet: "把知识库与当前库档案推到决策点（换库先跑，step 可只推某一步）",
    promptGuidelines: [
      "换库第一题之前必须 bird_brief db_id=<库> —— 否则等于靠语感猜库级写法，实测这是准确率最大的单一来源。",
      "step 的合法取值由后端 available_steps() 现场生成（`bird.py brief --help` 可查），文档里不手抄；喂一个没有内容的 step 会失败关闭，不会静默返回空。",
    ],
    parameters: Type.Object({
      db_id: Type.Optional(Type.String({ description: "数据库 id（给出时推**整份**库档案：必查 + 连接图与坑 + 值域陷阱/补充 + 惯例卡片）" })),
      step: Type.Optional(Type.String({ description: "只推某一步的片段（合法值见 bird.py brief --help，由 available_steps() 生成）" })),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["brief"];
      if (params.db_id) args.push(params.db_id);
      if (params.step) args.push("--step", params.step);
      return toResult(await getBackend(ctx).call(ctx, withDataset(args, params.dataset), signal));
    },
  });

  pi.registerTool({
    name: "bird_cols",
    label: "BIRD Cols",
    description:
      "列名反查：把题干里的概念（'district code'、'funding type'、'区号'）当**列名正则**去所有表里找，报出每个命中的 '表.列' + 非空行数/去重数 + 样例值，末尾给裁决提示。" +
      "概念是取值时用 bird_find，概念是列名时用它 —— 列名靠猜是本项目最大失分源。",
    promptSnippet: "按列名反查概念落在哪些表的哪些列（含非空/去重行数，用来裁决同名列）",
    promptGuidelines: [
      "换库第一题之前跑 bird_cols db_id=<库> pattern=\"type|code|option|status\" 看清这个库的列名惯例。",
      "命中 ≥2 列时先比'非空行数'：差得远 ⇒ 是粒度不同的两列；再按 evidence 点名 > 更专门 > 行集合相同则任选 来裁决，并把结论写进 db/<库>.md。",
    ],
    parameters: Type.Object({
      db_id: Type.String({ description: DB_ID_DESC }),
      pattern: Type.String({ description: "列名正则，例如 'type|kind|option'" }),
      samples: Type.Optional(Type.Number({ description: "每个命中列显示几个真值，默认 3" })),
      dataset: DatasetType,
      for_idx: ForIdxType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["cols", params.db_id, params.pattern];
      if (params.samples !== undefined) args.push("--samples", String(params.samples));
      return toResult(
        await getBackend(ctx).call(
          ctx,
          withFor(withDataset(args, params.dataset), params.for_idx),
          signal,
        ),
      );
    },
  });

  pi.registerTool({
    name: "bird_conventions",
    label: "BIRD Conventions",
    description:
      "用**已提交题的金标**统计这个库的写作惯例：计数形态（COUNT(列)/DISTINCT/COUNT(*)）、主表（FROM 第一张）、SELECT DISTINCT 比例、*100、输出列数分布、JOIN 数分布。" +
      "换库第 0.5 步必跑 —— 惯例是分布问题，只能用统计回答，不能靠回忆猜。只统计已提交题，不会把未做的题漏进来。" +
      "write_card=true 时把**同一份统计**写回 db/<库>.md 的惯例卡片（卡片 = 工具输出，改一处不会漂移）。",
    promptSnippet: "查这个库自己的写法惯例（计数形态 / 主表 / DISTINCT 比例），只统计已提交题",
    promptGuidelines: [
      "结论写进 db/<库>.md 的惯例卡片；主表'几乎总是 X'就直接照用，'主表不固定'说明本库是错题重灾区，写 SQL 前必须单独确认主表。",
      "卡片数字会随做题漂移 —— 每批题做完用 write_card=true（配 all=true 刷全部库）刷新，不要手改卡片里的数字。",
    ],
    parameters: Type.Object({
      db: Type.Optional(Type.String({ description: "只看某个库，例如 card_games" })),
      examples: Type.Optional(Type.Number({ description: "每个库打印几条计数题金标作形状示范，默认 2" })),
      write_card: Type.Optional(
        Type.Boolean({
          description:
            "把同一份统计写回 db/<库>.md 的惯例卡片（替换从『## 惯例卡片』到下一个二级标题之间的内容）。需配 db 或 all。",
        }),
      ),
      all: Type.Optional(Type.Boolean({ description: "配合 write_card：刷新所有已有档案的库" })),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["conventions"];
      if (params.db) args.push("--db", params.db);
      if (params.examples !== undefined) args.push("--examples", String(params.examples));
      if (params.write_card) args.push("--write-card");
      if (params.all) args.push("--all");
      return toResult(await getBackend(ctx).call(ctx, withDataset(args, params.dataset), signal));
    },
  });

  pi.registerTool({
    name: "bird_audit",
    label: "BIRD Audit",
    description:
      "复盘归因：EX 与各库正确率 + 错题的**失败类型分布**（列数/列序/行集/值口径/执行失败）+ 错题里'我的结构特征 ≠ 金标'的频次（main/tables/ncount/x100/like/cast…）+ 闸门合规率（探针覆盖/概念探针/--force/写了形状声明）。" +
      "读法：main 差得多 ⇒ 概念定位或主表错；count 差得多 ⇒ 计数形态错；x100 ⇒ 百分比口径错。",
    promptSnippet: "复盘：错因分布 + 结构特征差异频次 + 闸门合规率",
    promptGuidelines: [
      "每批 10–20 题之后跑一次，按错因分类再回去改 skill，而不是重复猜。",
      "合规率里'探针覆盖'低 ⇒ 这批是靠 --force 交的，流程没真走。",
    ],
    parameters: Type.Object({
      difficulty: Type.Optional(
        Type.String({ description: "只复盘某个难度：simple | moderate | challenging" }),
      ),
      db: Type.Optional(Type.String({ description: "只复盘某个库" })),
      list: Type.Optional(Type.Number({ description: "每类失败原因打印几条例子，默认 3" })),
      dataset: DatasetType,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["audit"];
      if (params.difficulty) args.push("--difficulty", params.difficulty);
      if (params.db) args.push("--db", params.db);
      args.push("--list", String(params.list ?? 3));
      return toResult(await getBackend(ctx).call(ctx, withDataset(args, params.dataset), signal));
    },
  });

  // 会话级资源清理（这里没有长驻进程，留个口子方便以后加连接池）
  pi.on("session_shutdown", async () => {
    backend = null;
  });
}
