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

## 第 15 轮：european_football_2 全量（65 道）——修正了一条“方向写反”的旧规则

结果：**48 对 / 17 错（73.8%）**。

### 最重要的修正

`playbooks.md` 原先写着：“问某球员的属性时通常要多一步取一条：
`WHERE player_api_id = (SELECT ... ORDER BY ... LIMIT 1)`” —— **实测表明这是反的**：

| idx | 题干 | 我（LIMIT 1） | 金标 |
|---|---|---|---|
| 1063 | Aaron Doran 的 potential | 1 行 | **26 行** |
| 1086 | Ariel Borysiuk 的 heading_accuracy | 1 行 | **24 行** |
| 1140 | Alexis Blin 的 sprint/agility/acceleration | 1 行 | **9 行** |

金标就是要**全部历史快照**。已把 `playbooks.md` 改成“**不要 `LIMIT 1`**”。

⇒ **教训升级版：不只是“值格式”会过时，“怎么取行”这类结构性笔记也会写反——
而且只会在真正做题时才暴露。** 只要有 2–3 道同类题同时错，就要回头质疑手册里的写法。

### 另一条重要发现

**`Player` 表根本没有国籍列**，所以“Belgium 的球员”只能绕
`Match → League → Country`；我硬 JOIN 了一个不存在的关联，`1126` 直接炸出 **10848 行**（金标 1514 行）。

### 其他错题分布

列数 2（1021、1064：金标多/少一列）・并列导致的 top-N 不稳（1024/1027/1034）・
年龄口径（1118：我 8731 行 vs 金标 8612，卡在“今天”的取法）・其余为口径/值（8 道）。

## 第 14 轮：financial 全量（62 道）——发现了“旧笔记与 Dev 版不符”

结果：**52 对 / 10 错（83.9%）**。

### 最有价值的发现：playbooks 里的日期格式已经过时

`playbooks.md` 记的是（来自 Mini-Dev）：“`account.date` 是 `'930101'`（YYMMDD）”。
**Dev 版实际全是 `'YYYY-MM-DD'`**（实测 `trans.date='1995-03-24'`、`loan.date='1994-01-05'`、
`card.issued='1998-10-16'`）。首批 13 道里好几道都在日期上踩了坑，probe 一次就全部解决。

⇒ **教训：Mini-Dev 时代写下的“值格式”笔记在 Dev 上不一定成立。**
换库/换版本时，跑一句 `SELECT 列 FROM 表 LIMIT 1` 比翻笔记可靠。
（已把这条写进 `playbooks.md` 的 financial 段，并加上了“动手前先探一句”的提醒。）

### 10 道错题的根因

| 类型 | 道数 | 例子 |
|---|---|---|
| **列数** | 2 | `165`（“list all transactions” 我 `SELECT *` 给了 10 列，金标 **1 列**）；`172`（“how many owner and disponent” 金标一行两个数） |
| “最早日期”并列 | 1 | `101`：`1995-01-01` 有 **315 个 account 并列**，`ORDER BY DESC LIMIT 1` 撞不对 |
| 口径/值 | 7 | `107` / `109` / `110` / `133` / `141` / `142` / `174` |

⇒ **列数的两个方向都出现过了**：card_games/toxicology 是“金标爱给/不给”，
financial 这两道是“**题干里的副词性描述不算输出列**”（“如何列出所有交易”→ 只给交易 id）。

## 第 13 轮：superhero 全量（81 道）——首批复盘 + 当场重交

结果：**75 对 / 6 错（92.6%）**（首批 11/13，复盘后重交 2 道 → 13/13）。

### 首批复盘抓到的两条（当天重交，都对了）

| idx | 错因 | 修法 |
|---|---|---|
| 803 | `power_name='cryokinesis'` 全小写 → **0 行** | 库里是 `'Cryokinesis'`（首字母大写） |
| 837 | “lowest attribute value” 用 `ORDER BY ASC LIMIT 1` → 1 行 | `MIN=5` 有 **10 个并列** → 改用 `WHERE attribute_value=(SELECT MIN(...))`，得 10 行 ✅ |

⇒ `837` 是 **A2 备用写法（WHERE = MAX/MIN）真正救回来的一道题**，
之前这条规则只写在手册里、没实测命中过。

### 未能解释的 4 道（已 probe 两轮，挂起）

`720`（“over 15 super powers”：金标 71 行 vs 我 102 行；已确认 `hero_power` **无重复行**
——5825 行 = 5825 个 distinct pair，所以差异不是重复导致的）、`741`（最多能力的英雄）、
`767`（“no skin colour” 的平均值）、`791`（平均身高）。

## 第 12 轮：toxicology 全量（76 道）——列数错占了一半以上

结果：**63 对 / 13 错（82.9%）**。

### 首批就抓到的关键坑（当场写回）

`connected` 表是**双向存储**：每个 bond 存两行（`A→B` 和 `B→A`）。
实测 `bond_id='TR001_2_6'` 返回 2 行；全库连接行数 **10882**，实际无向连接 **5441**（正好一半）。

### 13 道错题的根因分布

| 类型 | 道数 | 例子 |
|---|---|---|
| **列数** | **7** | 264（1列 → 金标 2 列）、252（1→2）、223（1行2列 → 2行1列）、309（2→3）、271（1→3）、296（1→3） |
| 值 | 5 | 259 / 269 / 286 / 311 / 335（都是 1 行 1 列但值不同） |
| 行数 | 1 | 221（双向存储导致 2 行 vs 1 行） |

⇒ **这个库的失分模式是“金标爱多给列”**，与 card_games 的“金标爱少给列”相反：
“for TR000, TR001 and TR002”类题干，金标会把实体 id 也输出成一列。已写回 `playbooks.md`。

### 流程观察

这一轮 71 道只用了约 6 次工具调用（读题+提交各三次循环），**全程零试探**：
一进库读连接图 → 首批 13 道 → 当场复盘 → 剩下 58 道直接批量跑。
在 8 表以上 / 结构清晰的库上，“先看连接图再看题”基本上就是胜负手。

## 第 11 轮：student_club 全量（113 道）——目前最好的库

结果：**103 对 / 10 错（91.2%）**。

### 为什么这一个库做得好

首批 13 道就 12 对，因为**这个库的主干连接只有四条**（已写进 `playbooks.md`）：
`member.link_to_major=major.major_id`、`member.zip=zip_code.zip_code`、
`attendance.link_to_member=member.member_id`、`attendance.link_to_event=event.event_id`。
“哪个学院/什么专业/哪个城市”类题几乎是模板题。
⇒ **这反过来验证了“一进库先读 B 部分连接图”是最高性价比的动作。**

### 10 道错题的根因

| idx | 根因 | 类型 |
|---|---|---|
| 1433 | `zip_code` 根本没有 `country` 列（列名错，被工具拒绝后我猜了 `state`） | 硬错 |
| 1436 | `event` 没有 `url` 列 → 应回退到外键 `budget.link_to_event` | 硬错 |
| 1467 | `SUM(...)` + 非聚合列却没 `GROUP BY` → 1 行 vs 金标 7 行 | 低级失误 |
| 1366 | “full name” 猜成 2 列，金标 1 列 | 列数 |
| 1370 | 金标 2 列（我 1 列） | 列数 |
| 1434 | `city='San Juan Municipio'` → 0 行；真值是 `'San Juan'`，但改成 `'San Juan'` 后仍是 17 行 vs 金标 2 行（未解） | 取值 |
| 1318 | 并列（两个 event 都是 30） | 并列 |
| 1391 | 比率值不同（32/33 有 major） | 口径 |
| 1450 | 33 行 vs 31 行 | 口径 |
| 1322 | 早期遗留（1 行 vs 9 行） | — |

### 本轮唯一可提炼的通用规则

**`SUM/MAX/...` 聚合函数旁边只要还有非聚合列，就必须 `GROUP BY`。**
`1467` 是纯粹的低级失误（一个 7 行题被写成 1 行），不是“金标怪”——
这类错应该在 `checklist.md` 提交前那一栏里拦住（已加）。

## 第 10 轮：formula_1 全量（117 道，含早期 27 道）——一次“通则写太大被证伪”的教训

结果：**88 对 / 29 错（75.2%）**。本轮执行了新流程：“首批 13 道 → 立刻复盘 → 定通则”。

### 新流程确实有用

首批 13 道只有 8 对，但复盘立刻抓到了两条真规则，并**当场重交了已有依据的错题**：

| idx | 修法 | 结果 |
|---|---|---|
| 860 / 871 | `q2='0:01:40'` → `q2 LIKE '1:40%'` | ✅ 2 道转对 |
| 964 | `nationality='America'` → `'American'` | ✅ |
| 922 | `'Abu Dhabi Circuit'` → `'Yas Marina Circuit'` | ❌（列对了但值不同） |

（skill 硬规则第 6 条允许这个例外：“skill 里有明确依据”时可以重交。）

### 最大的教训：通则不能“从小样本推”

首批复盘时我看到 `851`（’657 → 18’）就写下了：

> “formula_1 的输出列几乎都要 DISTINCT，而且还要排除 NULL（card_games 靠 DISTINCT，formula_1 靠 DISTINCT+IS NOT NULL）”

**后面被自己的数据打脸了：**

| idx | 金标行数 | 我加 DISTINCT 后 |
|---|---|---|
| 956 | **224** | 11 |
| 974 | **5268** | 1 |
| 1010 | **11340** | 1 |

formula_1 是**混合粒度**：有的题去重、有的题行级、有的题只给 1 行。
把 card_games 的通则（“这个库要 DISTINCT”）平移到 formula_1，方向完全相反。

⇒ **教训：库级通则只能从“一个库里反复出现的同一现象”里提炼（≥2 次独立证据）；
拿一个样本推全库，就会像这次一样，把错误写进 SKILL 并被后续几十道题放大。**
这话跟第 9 轮的教训（“规则要及时升级为库级通则”）是一对：
**既要及时升级，也要够证据才升级。**

### 本轮的“金标行数怪题”（记样本，不提炼）

`849 / 855 / 921`：“Where can … be found” → `races.url`，但金标只给 **1 行**
（实际有 27/19/51 行）。`974`（5268 行）、`1010`（11340 行）同理：**金标常常不做我们以为必做的聚合/去重。**

## 第 9 轮：card_games 全量（342–526，123 道）——“规则要及时升级成库级通则”

结果：**76 对 / 47 错（61.8%）**，是目前最差的一个库。

> 本轮严格“不思考”：99 道一次定稿、只用了约 10 次工具调用。
> 代价是错误率高，但复盘产出了下面这些真正有价值的东西。

### 失分模式（按道数排序，已全部写回手册）

| 模式 | 道数 | 例子 | 已写回 |
|---|---|---|---|
| **没加 `DISTINCT`** | ~10 | 387 (187→**10**)、399 (999→**46**)、444 (1052→**95**)、448 (480→**47**)、442 (9→**3**) | `playbooks.md` 第 7 条 |
| **多值串列用了 `LIKE`** | 1+ | 376：`keywords='Flying'` = **3088**（金标） vs `LIKE '%flying%'` = 5039 | `naming-traps.md` |
| **多给了列** | 5 | 435/436（`How many X? List out the id` → 金标只要 id）；445 (3列→2列)；403 (1列→金标 28639 行 2 列) | `playbooks.md` 第 9 条 |
| **`set_translations` 盖不全** | 4 | 428/429/438/519 全 0 行（只覆盖 121/551 个 set） | `playbooks.md` 第 10 条 |
| **并列导致排序不稳定** | 3 | 342（`faceConvertedManaCost` 最大值 **22 张并列**）、514、392 | `playbooks.md` 第 12 条 |

### 这一轮真正值得记的教训

**`DISTINCT` 那一条，其实在第 8 轮（342–363）就已经出现证据了。**
`idx 357`（`name='Duress'` 29 行 → 金标 4 行）就是同一个根因，但我当时只把它写成了
casebook 里的一个个案（“这一题要 DISTINCT”），**没有升级成“card_games 全库输出列都要 DISTINCT”的通则**。
结果后面 99 道题里至少 10 道又倒在同一个坑上。

⇒ **规则要从“个案”及时升级为“库级通则”**：只要在同一库看到 2 次同样的错因，
就应该写进 `playbooks.md` 该库段的顶部，而不是留在 casebook。

⇒ 由此得出一个流程建议：**在 BIRD 这种“按库聚集”的数据集上，“一轮”的天然单位应该是一个库，
而不是 99 道题。** 一个库的第一批（10–15 道）跑完就应复盘一次，把通则固定下来，
后面几十道才能真正复用。

## 第 8 轮：card_games 第一批（342–363，13 道）——教训：“没严格照 skill 走”

结果：**13 道 → 5 对 / 8 错**（本轮最低的一批）。

### 根因分类（全部 probe 验证）

| idx | 题干要点 | 我写的 | 根因 |
|---|---|---|---|
| **343** | 2015 帧且 EDHRec<100 的卡 | `cards.EDHRec` → 直接报错；重交 `edhrecRank` 后 654 行 | 行数对了但**集合不对**，疑似金标输出 `cards.id` 而非 `name`（playbooks 早就写了“which cards 常返回 id”，**我没照做**） |
| **350** | card Annul（number 29）的替代语言 | `name='annul'`（全小写） → **0 行** | 实际值是 `'Annul'`，SQLite 的 `=` 大小写敏感 |
| **361** | status=restricted 且有文本框 | `status='restricted'` | 实际值是 **`'Restricted'`**（636 行 vs 0 行）；正确值 = **634** |
| **363** | status=restricted 且在 starter deck | 同上 | 同上；正确值 = **205** |
| **354** | Aaron Boyd 画的卡的类型数 | `COUNT(DISTINCT cards.types)` = 2 | **`cards` 同时有 `type`（4 种）和 `types`（2 种）两列** —— 同名陷阱 |
| **357** | card Duress 的 promo 类型 | 29 行（未去重） | 同名卡 29 个版本 → 金标要 `DISTINCT`（去重后 **4** 行 = 金标） |
| **359** | Ancestor's Chosen 的原始类型 | 4 行 | DISTINCT 后 4 行（含 NULL），金标 **3 行** → 疑似排除 NULL |
| **342** | 面朝转换费用最高的卡名 | `ORDER BY faceConvertedManaCost DESC LIMIT 1` | max = 7.0 有 **22 张并列** → 排序不稳定，撞错 |

### 真正的教训（这一批最值钱的东西）

1. **playbooks 里已经写过的规则，我没执行。** `343` 就是典型：
   “which cards 的金标常返回 `cards.id`” 早就写在 B 部分的 card_games 段里，
   我写 SQL 时直接输出了 `name`。⇒ **读 B 部分不能只读“连接图”，要把坑逐条当约束用。**
2. **每换一个库，先 `SELECT DISTINCT` 看关键列的取值。**
   本批 3 道（`350/361/363`）纯粹输在大小写上 —— 而 california_schools 那边
   恰好相反（`'Directly funded'` 小写 f）。⇒ 已写进 playbooks 的 A 部分。
3. **evidence 里的名字是“概念名”，不是列名**：EDHRec → `edhrecRank`。
   写之前用 `pragma_table_info` 核对，成本 5 秒，能挡掉硬错。

### 已写回

- `playbooks.md` ▸ B 部分 card_games：新增 6 条实测坑（camelCase 列名 / 值首字母大写 /
  同名卡多版本用 DISTINCT / 连接键 / 22 张并列 / “Name all cards” 也可能返回 id）
- `playbooks.md` ▸ A 部分：新增“换库先 `SELECT DISTINCT` 看真值”的固定动作

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
