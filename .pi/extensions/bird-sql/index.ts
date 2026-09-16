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
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, signal, _onUpdate, ctx) {
      return toResult(await getBackend(ctx).call(ctx, ["info"], signal));
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
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["list"];
      if (params.db) args.push("--db", params.db);
      if (params.difficulty) args.push("--difficulty", params.difficulty);
      args.push("--offset", String(params.offset ?? 0));
      args.push("--limit", String(params.limit ?? 20));
      return toResult(await getBackend(ctx).call(ctx, args, signal));
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
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const result = await getBackend(ctx).call(ctx, ["question", String(params.idx)], signal);
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
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const bird = getBackend(ctx);
      if (params.descriptions) {
        const args = ["desc", params.db_id];
        if (params.table) args.push("--table", params.table);
        return toResult(await bird.call(ctx, args, signal));
      }
      if (!params.table) {
        return toResult(await bird.call(ctx, ["tables", params.db_id], signal));
      }
      const args = ["schema", params.db_id, "--table", params.table];
      if (params.samples !== undefined) args.push("--samples", String(params.samples));
      return toResult(await bird.call(ctx, args, signal));
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
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["run", params.db_id, params.sql];
      args.push("--max-rows", String(params.max_rows ?? 50));
      return toResult(await getBackend(ctx).call(ctx, args, signal));
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
      "概念是'列名'而不是'值'时（如 'district code'）bird_find 查不到，改用 bird_schema table=<表> 通读列名，别只 grep 关键词。",
    ],
    parameters: Type.Object({
      db_id: Type.String({ description: DB_ID_DESC }),
      word: Type.String({ description: "要反查的概念词（可以是片段，如 'funded'、'Continuation'）" }),
      samples: Type.Optional(Type.Number({ description: "每个命中列显示几个真值，默认 3" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["find", params.db_id, params.word];
      if (params.samples !== undefined) args.push("--samples", String(params.samples));
      return toResult(await getBackend(ctx).call(ctx, args, signal));
    },
  });

  pi.registerTool({
    name: "bird_answer",
    label: "BIRD Answer",
    description:
      "提交第 idx 题的最终 SQL。会先真的在数据库上跑一遍：跑不通会拒绝记录并回报错误，跑得通则把 SQL 记入 work/answers.json。",
    promptSnippet: "提交 BIRD 第 idx 题的最终 SQL（先试跑，失败会拒绝记录）",
    promptGuidelines: [
      "BIRD 每题定稿后用 bird_answer 提交；提交前建议先 bird_query 验证结果不是空集也不是明显异常值。",
    ],
    parameters: Type.Object({
      idx: Type.Number({ description: IDX_DESC }),
      sql: Type.String({ description: "你为该题定稿的只读 SQL" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const result = await getBackend(ctx).call(
        ctx,
        ["answer", String(params.idx), params.sql],
        signal,
      );
      return toResult(result, { idx: params.idx, sql: params.sql });
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
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["score"];
      if (params.db) args.push("--db", params.db);
      if (params.difficulty) args.push("--difficulty", params.difficulty);
      args.push("--list-wrong", String(params.list_wrong ?? 10));
      return toResult(await getBackend(ctx).call(ctx, args, signal));
    },
  });

  // 会话级资源清理（这里没有长驻进程，留个口子方便以后加连接池）
  pi.on("session_shutdown", async () => {
    backend = null;
  });
}
