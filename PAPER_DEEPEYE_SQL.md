# DeepEye-SQL 论文精读笔记

- 论文：**DeepEye-SQL: A Software-Engineering-Inspired Text-to-SQL Framework**
- arXiv：<https://arxiv.org/abs/2510.17586>（本笔记基于 v2 全文 HTML）
- 作者：Chong Chen、Zhujun Xue、Yinan Mei（华为云 BU）、Yuyu Luo（HKUST(GZ)，通讯作者）
- 定位：**免训练（training-free）的 Prompting-based 框架**，把 Text-to-SQL 当成"开发一个小软件"来做。

> 一句话总结：**它不靠更强的模型，而是靠一套"软件工程式的流程编排"把单模型 62% 左右的水平拉到 73.5%**——先在数据里"接地"（值检索 + 三路 schema linking），再用三套**方法论不同**的生成器并行产出候选，然后用**确定性工具链**逐条检查并定向修复，最后按"执行结果聚类置信度"做带门限的裁决。

---

## 1. 要解决的问题（论文自己的动机）

BIRD 上 SOTA 长期卡在 ~70% EX。作者认为瓶颈**不在单个模块**（schema linking / reasoning / verification 都有人做好了），而在**缺少贯穿全流程的编排（orchestration）**，于是把四个失败点列成 C1–C4：

| 挑战 | 含义 | 对应阶段 |
|---|---|---|
| **C1** ambiguous requirement inference | 自然语言有歧义、schema 只看到一部分 | 需求分析 |
| **C2** 单点故障 | 只走一条推理路径、一套 prompt | 实现 |
| **C3** unreliable V&V | 用自一致性、部分执行反馈等**概率信号**当验证 | 验证 |
| **C4** 没有发布标准 | 缺**校准过的置信度**和可度量的接受准则 | 发布 |

解法就是照搬 SDLC（需求分析 → 实现 → 测试 → 发布/质量门），四个阶段逐一对应。

---

## 2. 四个阶段（核心内容）

### Phase-1 需求界定与语义接地（Intent Scoping & Semantic Grounding）

分两块：**语义值检索**（Semantic Value Retrieval）+ **鲁棒 schema linking**。

**（1）语义值检索** —— 解决"LLM 不知道库里到底存了什么值"（例如库里是 `'United States'`，模型写成 `'USA'`）。

- 离线一次：只抽 **TEXT 类型**列，用启发式**排除 UUID / 纯数字 ID**；每个去重值用 **Qwen3-Embedding-0.6B** 编码；用 **Chroma + HNSW** 建**按列**的向量索引。
- 在线：先让 LLM **抽关键词** K；对每个已索引列并行检索 top-K；汇总所有关键词的候选、按相似度排序、取 **top-K 去重值**，得到 `M_retrieved: 列 → 值集`。

**（2）鲁棒 Schema Linking** —— 三路并行，再取并集 + 补关系闭包：

| 策略 | 做法 | 论文的实测 |
|---|---|---|
| **Direct**（正向） | 直接让 LLM 根据题面 + 全 schema 列出相关表/列 | 最弱：列召回比 Reversed **低 13.1 个点** |
| **Reversed**（逆向，"reverse engineering"） | **先让 LLM 直接写一版草稿 SQL**，再用静态解析器从 SQL 里反解出用了哪些表/列 | 表 97.0% / 列 94.0%，明显强于 Direct |
| **Value-based**（值驱动/自底向上） | 若某列的检索值和题面关键词相似度 > **θ_val = 0.98**，就选该列 | 单独召回不高，但能**补漏** |

- **Union**：`D_union = D_direct ∪ D_reversed ∪ D_value`
- **EnforceClosure（关系闭包）**：并集可能是"断开的图"，于是把出现在并集里的表之间**所有主外键列自动补上**，保证最终 schema 是**连通图**，为 JOIN 打好基础。
- 结果：表召回 **98.1%**、列召回 **95.4%**，并把输入上下文从 **5486.2 → 627.4 tokens（约 9×）**。

> 论文的用例（BIRD QID 142）：题目问 "household payment"，Direct/Reversed 都没找到 `trans.k_symbol`（列名太隐晦），**Value-based 通过把 'SIPO' 这个值接上，才找回了关键列**——这就是"值驱动"不可替代的价值。

### Phase-2 N-version Programming（多版本生成）

借软件工程的 **N-version programming**（同一功能做多份独立实现，再裁决）来提供容错。**三个方法论不同**的生成器**并行**：

1. **Skeleton-based**（自顶向下）：先做组件分析 → 生成骨架 → 填槽（slot-filling），一次 LLM 调用内完成。
2. **ICL-based**（类比 case-based reasoning）：按 DAIL-SQL 的方式检索**schema 掩码**的相似样例，让模型先找共性模式、再套到目标题上。
3. **Divide-and-Conquer**（分治）：拆子问题 → 子问题分别解 → 合成一条 SQL。

关键区别（作者特意强调）：**这不是 self-consistency 式的同一生成器多次采样**，而是**推理过程本质不同**的三条路，所以多样性是"工程化的多样性"。

### Phase-3 SQL Unit Testing and Revision via Tool-Chain（工具链单测与修复）

动机：**LLM 自纠不可靠**（确认偏误，看不到自己的错）。所以把验证**外置**成一条**确定性检查器链**，每个 checker 就是一个"单测用例"，命中就给 LLM 一条**明确的修复指令** `d_err`，LLM 只负责"照指令改"，不负责"找错"。

检查器链（**固定顺序**，从语法到语义）：

| Checker | 抓什么错 | 例子 |
|---|---|---|
| Syntax | 语法 / 执行错误 | `SELECT * FORM table`、`WHERE col =` 残缺 |
| JOIN | 非标准 JOIN 条件 | `ON a OR b`、`ON col IN (...)` |
| ORDER-BY | 非法 ORDER BY + LIMIT | `ORDER BY MAX(...) LIMIT 1` |
| Time | 时间函数 / 格式用错 | `STRFTIME('%Y', date)` 写法、非法日期比较 |
| SELECT | 返回列有歧义 | `SELECT *` → 具体列 |
| MaxMin | 次优的 MAX/MIN 写法 | `WHERE col = (SELECT MAX(...))` → `ORDER BY col DESC LIMIT 1` |
| NULL | ORDER BY 列含 NULL | 补 `WHERE col IS NOT NULL` |
| Result | 空集 / 无意义结果 | 只返回 NULL、零行 |

流程是**单趟**的：候选依次过全部 checker，某步报错就调一次 LLM 修复并替换，然后继续下一个 checker；走完为止。

### Phase-4 Confidence-aware SQL Selection（置信度感知的选择 / 质量门）

先把所有修订后的候选**真的执行**，按**执行结果是否完全一致**聚类，按簇大小排序：

- 候选 S_i 的**置信度** `Conf(S_i) = |Cluster_i| / |C_revised|`（即该结果簇占全部候选的比例）。
- **高置信度捷径**：若**第一名**的置信度 > **θ_conf（论文取 0.6）**，直接输出它——省掉昂贵的 LLM 调用。
- **低置信度全审**：否则取 **top-K（论文 K=2）** 候选，做**不平衡成对裁决**：
  1. **认知先验**：明确告诉 LLM "S_i 的执行置信度高于 S_j"，要求**除非有确凿证据否则选高置信度那个**（不搞中立比较）。
  2. **成对裁决**：每对做**多次采样取多数**，得到稳定票 `V(S_i,S_j) ∈ {0,1}`；再算 `WinRate(S_i) = 1/(K-1) · Σ_j V(S_i,S_j)`。
  3. **最终分**：`Score(S_i) = Conf(S_i) × WinRate(S_i)`，取 `argmax`。

论文的底气来自实测：**置信度 vs 是否正确的 Pearson 相关 = 0.954**（置信度高 ⇒ 几乎必然正确；置信度低 ⇒ 多数投票不可信，所以要"再审"）。

### 4.6 三个效率优化

- **Efficient Prompting**：多步推理塞进**一次**带 CoT 指令的 prompt，只输出最终 SQL，省掉多轮往返的 token。
- **Parallel Execution**：多列值检索、三路 linking、三个生成器、各候选的修复，全部并行。
- **Conditional Execution**：只有 checker 报错才调 LLM 修复；只有低置信度才触发成对裁决。

---

## 3. 实验结果

### 主结果（Table 2）

| 方法 | 模型 | 参数 | BIRD-EX | Spider-EX |
|---|---|---|---|---|
| XiYan-SQL（微调） | GPT-4o + Qwen2.5-Coder-32B | >200B | 73.3 | 89.7 |
| CHASE-SQL（微调） | Gemini-1.5-Pro + Flash | >200B | 73.0 | 87.6 |
| Alpha-SQL（免训） | Qwen2.5-Coder-32B | ~32B | 69.7 | – |
| OpenSearch-SQL v2（免训） | GPT-4o | >200B | 69.3 | 87.1 |
| **DeepEye-SQL** | **Qwen3-Coder-30B-A3B** | **~30B** | **73.5** | **89.8** |
| DeepEye-SQL | Gemma3-27B | ~27B | 71.1 | 88.9 |
| DeepEye-SQL | Qwen2.5-Coder-32B | ~32B | 70.9 | 88.7 |

**要点**：靠 ~30B **开源**模型、**零微调**，BIRD-Dev 反超 GPT-4o/Gemini 系的微调方法；同模型下比 CoT 基线 **+11.8 ~ +16.9 个点**（RQ2 证明增益来自框架而非模型）。

### schema linking 消融（Table 4, Qwen3-Coder-30B）

- 完整方案：表 98.1% / 列 **95.4%** 召回，token **5486.2 → 627.4（9×）**。
- Reversed 显著强于 Direct，**列召回 +13.1%**。
- Value-based 单独召回低，但定位是"**补漏的精确机制**"，不是独立 linker。

### 生成器分析（Table 5 / Figure 5, RQ4）

- 单生成器最好 **70.9% EX**；三路合并 **71.7% EX**（仅 +0.8）。
- 但 **上界 UB-EX：78.5% → 81.1%（+2.6）**——说明候选池**确实有真多样性**。
- 正确性重叠：**70.9% 的题三路都对**，另有 **10.2% 的题只有 1~2 路对**（证实不是冗余）。
- 作者结论：N-version 的价值在于**"至少有一条对"**（81.1% 的题存在正确候选）。

### 选择机制（Table 6 / Figure 6、7, RQ5/RQ6）

- 置信度 vs 正确率相关 **0.954**。
- 他们的方法**在所有模型、两个数据集上都优于传统 self-consistency 投票**（例：Gemma3-27B 上 BIRD 从 70.1 → 71.1，+1.0）。
- θ_conf 敏感性：从 0.0 到 1.0 变化，准确率**始终 > 73.0**，**0.6 时峰值 73.5**，说明不敏感、稳健。

### 消融（Table 7, RQ7）

逐组件移除，**每个组件都是正贡献**：

- **ICL 生成最大 −2.5%**；
- **语义值检索 −2.1%**；
- **单测工具链 −2.1%**；
- 生成模块与选择机制也都是显著正贡献。

### 效率（Table 8, RQ8）

- 输入 **23.21K tokens/题**；对比 Alpha-SQL **138.03K（≈6×）**、CHESS **327.02K（≈14×）**，且准确率更低。
- 开销最大的是**鲁棒 schema linking** 与 **N-version 生成**；语义值检索与置信度选择**很轻**。

---

## 4. 对我们自己项目（bird-bench 提交）的启示

我们的处境和它**部分重叠、部分不同**，逐条对比：

| 维度 | DeepEye-SQL | 我们（现状） |
|---|---|---|
| 模型 | 本地 vLLM 跑 ~30B 开源模型，可采 8 次 / T=0.7 | deepseek-flash，**T=0、单次确定性采样** |
| 接地 | embedding 值检索 + Chroma 索引 | **精确匹配侦察（recon）**，无 embedding 端点 |
| schema | 三路 linking + 闭包，砍到 627 tokens | 全 schema 给上下文；γ 实测剪样本仅省 **7.8%** |
| 生成 | 三套方法论（Skeleton/ICL/D&C） | 我们已实现 **direct vs D&C（β）** 两臂 |
| 验证 | **8 个确定性 checker 链 + 定向修复** | 我们只有"流程合规闸门"，**没有语义 checker** |
| 选择 | 执行结果聚类置信度 + 成对裁决 | P1.5 试过简化版（聚类 + 先验回退），**零净增益** |

**已经验证过、可以直接吸收的：**

1. **Reversed schema linking（先写草稿 SQL 再反解列）在它那里列召回高 13.1 个点** —— 这和我们 β 的 D&C 思路不完全一样，但"先产出 SQL 再回看 schema"是个**便宜的、纯 prompt 的改进**，值得单独做一次 ablation（无 API 成本可先离线估计候选覆盖）。
2. **确定性 checker 链（Phase-3）** 是它相对我们**最大的空白**，而且**大部分 checker（Syntax/JOIN/ORDER-BY/SELECT 形态）可以离线用 SQLite + 纯正则实现、零 API 成本**；只有触发修复时才需要一次 LLM 调用。这比我们现在的"提示词规则"更硬：**规则是给模型的建议，checker 是给系统的断言**。
3. **它把"候选池覆盖率"当成独立指标报告（UB-EX 81.1% vs EX 71.7%，差 9.4 个点）** —— 这正是我们 P0 做的事（四臂并集 79.95% vs 单臂 74.48%）。**两边的结论一致：空间是有的，问题在"选"。**

**必须打折扣的地方：**

1. **置信度 0.954 依赖"同一分布多次采样"**（T=0.7、8 次）。我们 T=0 单次采样，结果簇天然只有 1 个，**它的 Conf 机制在我们这里根本退化了** —— 这就是 P1.5 零增益的根本原因，而**不是"N-version 无用"**。要复现它，第一步是先把温度放开。
2. **它报的是老版 BIRD-Dev（`dev_20240627`）**，我们跑的是 2025-11-06 新版，**两边分数不可直接比**。
3. **它的 value-based linking 靠 embedding 端点**（Qwen3-Embedding-0.6B + Chroma）。我们**没有 embedding 端点**，只能做精确匹配近似 —— 要完整复现 α 就得先解决嵌入服务。

---

## 5. 一句话结论

这篇论文真正的贡献**不是某个黑科技模块，而是"流水线化的可靠性工程"**：
**多路生成拓候选 → 确定性 checker 保证可验证 → 置信度门控决定要不要花大代价审**。
其中对我们最有迁移价值的是 **Phase-3 的确定性 checker 链**（结构性、可离线、零 API 成本）和 **Reversed schema linking**；
而 **Phase-4 的置信度机制我们可以照抄设计、但不能照抄结论** —— 前提（多次采样）我们还没满足。
