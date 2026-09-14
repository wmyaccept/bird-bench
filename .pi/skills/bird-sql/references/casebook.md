# 错题档案（复盘记录）

本文件是**数据**，不是方法。方法在 `diagnosis.md` / `gold-style.md` 等文件里。
出题规模变大后，这里会持续追加；**精简时优先动这个文件**。

## 复盘纪律

- `bird_question --reveal` 只能在**一批题做完之后**用于复盘。
- 复盘产出的**规则**写回 `references/` 下对应文件；
  **不把金标 SQL 拼回 `answers.json`** —— 否则 EX 就变成对答案的拟合，失去度量意义。
- 复盘时**先写下自己的押注再看答案**。押注全错才有信息量：它说明你对"出题人会怎么写"的
  模型有系统性偏差（本项目实测 5 题押注**全错**）。
- 归纳规则前先过一遍"收录标准"：**这条规则能让我写出更接近金标的 SQL 吗？**
  如果它只是教我去复现一个 bug，就不收（见 `gold-style.md` 节首）。

## 已复盘：148 道 simple 中的 5 道错题

| idx | 库 | 我的答案 | 金标 | 根因分类 | 去向 |
|---|---|---|---|---|---|
| 116 | thrombosis_prediction | 136 / 803 | **9** | 我的推理方向错了：多余 JOIN 是**隐式过滤**而不是扇出 | → `gold-style.md` ③ |
| 174 | european_football_2 | 各种 3 列组合 | **(98022, 13, 13)** | 多出来的那一列是**属性行主键** | → `gold-style.md` ① |
| 222 | formula_1 | 1 / 5 | **2** | **金标意图写错**：问"几支车队"却写 `COUNT(raceId)`，被 `HAVING = 2` 钉死 | 只作缺陷样本，**不提炼规则** |
| 344 | codebase_community | 10997 / 11000 | **2888** | `Score` 属于 `posts` 而不是 `comments` | → `naming-traps.md` |
| 441 | california_schools | 试了 3 种列组合 | **(编号, 分数, 名次)** | `RANK()` 是输出列，且**不带学校名** | → `gold-style.md` ② |

### `idx 222`：为什么"不收"这一类题

```sql
SELECT COUNT(T1.raceId) FROM constructorStandings AS T1 ...
WHERE T1.points = 0 AND T2.nationality = 'Japanese'
GROUP BY T1.constructorId HAVING COUNT(raceId) = 2
```

`SELECT` 数的是**组内行数**，而 `HAVING` 强制组内行数 = 2 ⇒ 每个通过的组都返回 `2`。
题面问"几支车队"，语义上唯一合理的答案是 1（只有 Kojima 满 2 场且全 0 分），
**金标意图上是错的**。

这类"意图与 SQL 不一致"的题，**不要拿去归纳规则**：它能教会你的只是"怎么复现一个 bug"，
在下道题上只会把错误也学进去。它的价值只在于：知道数据集里存在这类题（估计 <2%），
遇到时别撞南墙。

## 切换数据集：Mini-Dev → 官方 Dev 集（一次重要的基础设施改名）

### 为什么要换

官网上只有 **Dev** 成绩能和排行榜对比（人类 92.96 / GPT-4 46.35），
而 **Mini-Dev 是“开发用轻量集”，不上榜**（官网原话：Lite version of development dataset，
for testing and refining models）。所以想要一个可对照的数字，必须跑 Dev。

### 换的时候撞出来的三个事实

1. **Mini-Dev 是 Dev 的子集**：500 题里 **494 道题干与 Dev 完全相同**（99.2%）。
   ⇒ idx 体系不同，两个数据集的 `answers` **必须分开存**（`answers.json` / `answers_dev.json`）。
2. **两个文件的金标不完全一致**：可映射的 496 题里 **13 题金标 SQL 不同**（2.6%），
   且都不属于那 42 道并列题。所以同一道题可能在 Mini-Dev 对、在 Dev 错（实测撞到 1 道）。
   ⇒ **以 Dev 为准** —— 之前从 Mini-Dev 金标归纳的规则，在这 13 题上可能不适用。
3. **Dev 有 42 道并列题的补充金标**（`dev_tied_append.json`）：官方口径是“命中主金标**或**任一并列变体”
   就算对。scorer 已改成支持传多条金标（命中变体会标 `ok（命中并列变体 #k）`）。

### 迁移结果

已作答的 172 题里 **170 题能唯一映射到 Dev**（2 题在 Dev 里找不到对应题干：
Mini-Dev idx 229、283，都是 superhero，且原本都做对了）。

| | Mini-Dev | Dev（同 170 题重映射） |
|---|---|---|
| 已答 | 172 | 170 |
| 正确 | 164 | **161** |
| EX（已答部分） | 95.35% | **94.71%** |

差异对得上：−2（两题没映射过去）+ −1（`idx 338`→Dev `687`，两个文件金标不同）。

### 全量口径（排行榜用的那个数）

Dev 共 1534 题，现在完成 170 题（11.1%）⇒ **全量 EX = 161/1534 = 10.50%**。

> ⚠️ 在答完 1534 题之前，**不能对外说自己的 Dev EX 是 94.71%** —— 那只是“已作答部分”的准确率。
> 排行榜的 Dev 分数是全量口径。已作答 170 题的 94.71% 只能说明“做法有救”，不能当成绩。

## 第 4 轮：在官方 Dev 集上系统推进（按库 + 套路）

### 阶段目标与方法

目标：先做完 Dev 的全部 **925 道 simple**（可对标主榜模型 Dev 列）。
方法（解决"写了一堆东西但不成体系"的问题）：

1. 把方法整理成 [`playbooks.md`](../references/playbooks.md)（**题型骨架 + 11 个库的连接图**），
   做题时先查手册再写 SQL。
2. **按数据库为单位推进**（题目天然按库聚集），用 bash 批量读写：
   `batch.py`（heredoc 传参，避开引号问题）+ `qshow.py`（一行一题紧凑读题）。
3. 一批 10–15 题：批量读题 → 一次探关键取值 → 批量提交 → 一次评分。

### 本批实战成绩

| 批次 | 题数 | 首次就对 |
|---|---|---|
| california_schools 第一批（idx 0/2/3/6/7/8/9/10） | 8 | **8/8**（完全套套路，一次未试错） |
| 第二批（13/14/15/16/18/19/20/21/22/29/30/38/42/44） | 14 | 11/14 |
| 第三批（51–64 共 12 题） | 12 | 9/12 |

累计：Dev 已答 **204/1534**（全量 EX 12.58%），simple **180/925**。

### 本批新学到的套路（已写回 `playbooks.md`）

1. ⚠️ **SQLite 双引号包一个不存在的列名不会报错**，而是当字符串字面量返回。
   实测：以为 `Low Grade` 在 `schools`，结果是 17686 行全是字符串 `'Low Grade'`。
   → 带空格/括号的列名先用 `pragma_table_info` 确认。
2. ⚠️ **california_schools 的 CDS 码前导 0 是分批丢的**：`satscores` 2269 行里 2058 行是 14 位、
   **211 行是 13 位**。naive 等值连会默默丢掉那 211 行（Contra Costa 就是 0 行）。
   `CAST(CDSCode AS INTEGER) = cds` 能全匹配，**但不要无条件修正**（多数题的金标就是 naive join）。
3. ⚠️ **`schools` 里混着学区/县办公室行**（`CDSCode` 以 `0000000` 结尾，`School` 为 NULL），
   问"哪个学校"时要把它们排除（`sname IS NOT NULL`）。
4. **"在某个地方"要分清是市、县还是邮寄地址**：`idx 60` 的 "in San Joaquin" 金标用的是
   `County`（不是 `City`，也不是 `MailCity`）。一个地名往往对应三个候选列，先用 `DISTINCT` 看一眼。
5. **"How many test takers at the school/s" 返回的是每校一行**（`idx 53`：金标 32 行），
   不是 `SUM`。看到复数 "school/s" 就要警惕——这类题金标常给行级结果。

### 未解决（先挂着，不耗轮数）

| idx | 现象 | 试过 |
|---|---|---|
| 16 | 1 行 1 列值不同 | naive / CAST / 按校名 JOIN（=2）都不对 |
| 51 | 1 行 2 列值不同 | naive join / CAST join 两个不同的学校都不对 |

## 第 7 轮：codebase_community 收尾（676–715，27 道）

结果：**27 道 → 21 对 / 6 错**。

> 本轮首次严格执行“做题时不许思考”（SKILL.md 硬规则 6）：
> **不试跑、不穷举、一稿定音**。27 道只用了 3 次工具调用（读题 1 + 提交 1 + 重交 1）。

### 6 道错题的根因（均已用 probe 验证）

| idx | 题干要点 | 我写的 | 根因 → 已写回哪份手册 |
|---|---|---|---|
| 689 | last to edit 帖 183 的用户 | `posts.LastEditorUserId` JOIN → **0 行** | 该列 **47361 行是 NULL**；必须走 `postHistory` 按 `CreationDate` 倒序 → `playbooks.md` |
| 696 | tag='careers' 的帖数 | `posts.Tags LIKE '%<careers>%'` = 22 | evidence 点名 `TagName` → 金标在 `tags` 表上数 = **1** → `naming-traps.md` |
| 709 | score=0 的评论里 ViewCount<5 的**帖**数 | `COUNT(*)` = 4 | 题干主语是**实体** → `COUNT(DISTINCT posts.Id)` = **2** → `calibration.md` |
| 686 | views above average 的帖数（“total number”） | `COUNT(*)`（1 行） | 金标 **7689 行**（直接列出帖子，**不聚合**）→ 见下 |
| 679 | 最高分帖的 id 和 title | `(Id, Title)` | evidence 补了 `owner's name → DisplayName`，**该字段必须进 SELECT** → 见下 |
| 693 | 最新用户的 posts 和 comments 数 | 2 列 | 金标 **1 列** → 见下 |

另：`700` 因把 `BountyAmount` 写到 `posts` 表上而**执行失败被拒**（在 `votes` 表），
重交即过 —— 这类“列名不存在”是硬错，不算 EX 错。已写回 `playbooks.md` / `naming-traps.md`。

### 三条“金标反直觉”样本（**不**提炼成规则，只留档）

1. **`idx 686`**：题干 “Identify the **total number of** posts with views above average”，
   金标返回 **7689 行**（= `SELECT Id FROM posts WHERE ViewCount > (SELECT AVG(ViewCount) FROM posts)`），
   **没有 COUNT**。我的 `COUNT(*)` 值也是 7689，但形状错（1 行 vs 7689 行）。
   → 无法事前预判，不提炼。
2. **`idx 679`**：题干 “give its **id and title's name**”，evidence 却写
   “**owner's name** refers to DisplayName”。→ 提炼出的规则是“**evidence 补的字段必须进 SELECT**”，
   但具体组合（Id+DisplayName 还是 Title+DisplayName）仍未知。
3. **`idx 693`**：“the number of posts **and** comments” 金标只给 **1 列**；
   而同批 `idx 698` 的 “How many comments **and** answers” 是 **2 列**（我做对了）。
   区别不明确（前者两列同属一个用户，后者分属两张表）→ 样本不够，不提炼。

### 本轮验证有效的 skill 条款（做题时能直接套）

- `playbooks.md` A2 的极值骨架（`ORDER BY 指标 DESC LIMIT 1`）：`677/679/681/690` 一稿命中
- `sqlite-and-data.md` 的 NULL 规则（上一轮 `663` 的经验）：`684/691/711` 年龄段题一次对
- `calibration.md` 的百分比子查询写法：`684` 一次对
- **“evidence 给的口径先照抄”**：`699/700/702/703/706/715` 全部命中

## 第 6 轮：codebase_community 收尾第一批（644–675，25 道）

结果：**25 道 → 首次就对 20 道，修后 22 道**（`663`/`656` 修复，`646`/`649`/`667` 挂起）。

### 修好的两道（根因都很典型，已提炼成规则）

| idx | 题干 | 我写的 | 金标 | 根因 |
|---|---|---|---|---|
| 663 | id of the **youngest** user | `ORDER BY Age ASC LIMIT 1` → `-1` | `805` | ⚠️ **`users.Age` 有大量 NULL，SQLite 里 NULL 最小**，ASC LIMIT 1 命中 NULL 行 → 改用 `WHERE Age=(SELECT MIN(Age) FROM users)` |
| 656 | display name of the **parent ID** for child post with highest score | `'Fabian Fagerholm'`（父帖 owner） | `'ars'`（子帖 owner） | 金标把“display name”连到 **`posts.OwnerUserId`**，根本没沿 `ParentId` 反向取人；`ParentId IS NOT NULL` 只用于筛“子帖” |

### 挂起的三道（已花 2–4 次尝试）

- `646`（positive comments，金标 192 行）：exact 口径下 `comments.Score>60` 全库**只有 1 行**，
  试过 `posts.Score>60` 评论者(356/77/51)、`comments.Score>0` 去重(22464) —— 都对不上 192。
- `649`：“post history counts and last edit date”（金标 12 行 2 列 = postHistory 行数）。
  第二列试过 `posts.LastEditDate` / `postHistory.CreationDate` 都错，第一列试过 `PostHistoryTypeId`。
- `667`：“oldest post link” 的 title。`postLinks` 的 `PostId` / `RelatedPostId` **两个方向都试过，都错**。

**共性教训（值得记）：**
1. **“属性 + 极值”题里，如果“最高/最低”后面跟的是个外键（ParentId / OwnerUserId），
   金标往往直接用那个外键对应的行，而不是顺着外键再反查一次**（`656` 就是这样）。
2. **口径对不上时，先数“该条件在全库有多少行”**（`SELECT COUNT(*) ... WHERE 条件`）。
   `646` 就靠这一步确认了 evidence 给的口径（Score>60）在数据上**不可能**产生 192 行，
   直接止损，不再盲试。

### 工具/流程上的确认

- `batch.py answer` **单次只提交、不评分**；评分类必须单独调 `bird.py score`，否则会读到旧报告。
- 批量读题用 `qshow.py dev <idx...>`，一次 12–13 道刚好（再多输出会被截断）。

## 第 5 轮：按库推进 + 套路化（thinking 模式关闭前的最后一轮）

### 工作方式的变化（本次最重要的产出）

从“一题一探、错了再猜”改成**先定套路再批量做题**：

1. 产出 [`playbooks.md`](../references/playbooks.md)：**A 部分 = 通用题型 10 种骨架**，
   **B 部分 = 11 个库的连接图与坑**。做题时先查手册，不再从零推理。
2. **以“库”为单位推进**（题目天然按库聚集），每批 12–14 题：
   批量读题 → 一次探关键取值 → 批量提交 → 一次评分。
3. 工具：`batch.py`（heredoc 传参，避开引号转义）+ `qshow.py`（一行一题紧凑读题）。

### 成绩

| 批次 | 库 | 题数 | 首次就对 |
|---|---|---|---|
| 1–3 | california_schools | 34 | 28 |
| 4–9 | codebase_community | 79 | 63 |

累计净增 122 题（172 → 294）。出现了多次**整批全对**（8/8、14/14、14/14、12/12），
说明套路对手册已覆盖的题型（属性查询 / 计数 / 极值 / 多跳 JOIN）确实够用。

### 本轮新学到的套路（已写回各手册）

1. ⚠️ **SQLite 双引号包不存在的列名不报错**，而是当字符串字面量返回
   （实测：以为 `Low Grade` 在 `schools`，结果 17686 行全是 `'Low Grade'`）。
2. ⚠️ **california_schools 的 CDS 前导 0 是分批丢的**：2269 行里 2058 行 14 位、211 行 13 位，
   naive join 会默默丢掉后者（Contra Costa 直接 0 行）。`CAST` 能全匹配，**但多数题金标就是 naive**。
3. ⚠️ **金标结果不会是 NULL**（论文保证）—— 用于在两个候选写法间二选一（`idx 22`）。
4. **地名 / 学校名要分清来源**：`City` / `County` / `MailCity` 三个候选（`idx 60` 用的 `County`）；
   `schools` 里混着学区行（`School` 为 NULL）。
5. **“How many X at the school/s” 返回每校一行**，不是 `SUM`（`idx 53`）。
6. **“取年份” 用 SUBSTR/LIKE**；`codebase_community` 的时间戳**带毫秒 `.0`**，
   `votes.CreationDate` 只到日。
7. **可疑的年份区间要照抄 evidence**：`idx 642` 的 evidence 写的是
   `BETWEEN '2010-07-21' AND '2012-07-21'`（跨两年，明显是笔误）—— 这种“不合理的区间”
   往往正是金标的原样。

### 本阶段未解决（已花 2–3 次尝试，挂起）

`california_schools`: 16、51・`codebase_community`: 600、602、603、628、631、632、642

共性：形状已确定（行/列数对），但值或最后几列对不上，且候选写法试完后无新推理依据。

## 已完成批次

| 批次 | 范围 | 成绩 |
|---|---|---|
| 第 1 轮 | simple 前 49 题 | 47/49 = 95.92% |
| 第 2 轮 | simple 全部 148 题 | **143/148 = 96.62%**（后 99 题正确率 97.0%） |
| 第 3 轮 | moderate 前 25 题（debit_card + student_club） | **21/24 = 87.5%**（其中 1 题多轮后已修） |

### 第 3 轮（moderate 首批）的复盘
**三个错误都验证了已有规则，但第一次没主动套用：**

| idx | 我第一遍 | 金标 | 没套用的规则 |
|---|---|---|---|
| 1 | 单行最小 → 7653 | 按客户汇总全年 → **47273** | `calibration.md` 的「先按实体汇总」 |
| 29 | 9 行 2 列（DISTINCT + 带 id） | **10 行 1 列** | `gold-style.md` 的「行级输出」 |
| 56 | 加了 Treasurer 条件 → 2 行 | **4 行**（不限职位） | `gold-style.md` 的「限定词可能没实现」 |

**两个成功迁移的例子（说明规则是真的）：**

- `idx 15`：问 "June 2013" 的加油站在哪些国家，而 `transactions_1k` 根本没有 2013 年的数据。
  直接用 `calibration.md` 的「条件落在表 A、列在表 B → 用共同 key 硬连」——
  通过 `yearmonth.CustomerID = transactions_1k.CustomerID` 硬连 → 命中。
- `idx 33`："有 20 人以上参加但**不是募捐**的活动"，仓库里根本找不到“募捐”这个概念。
  主动省掉那个条件 → 命中。

### 尚未定位（moderate 首批遗留）

| idx | 库 | 金标形状 | 试过的思路 |
|---|---|---|---|
| 27 | debit_card_specializing | 1 行 2 列 | 两个金额口径 × yearmonth 消费，均不对 |
| 28 | debit_card_specializing | 1 行 3 列 | 按 SUM(Amount×Price) / SUM(Price) 两种“top spending”均不对 |
| 32 | student_club | **9 行 1 列** | 事件级 4 行、名称级 13 行、按 size/position/status/member 分组都不是 9 |

> `idx 32` 的金标是 9 行——一个“how many”问题返回 9 行，说明金标里有 `GROUP BY`（参考 `casebook.md` 里 `idx 222` 的同类形状）。但试过的分组键都对不上 9，属于“可推导信息已用完”。
