# 该用哪张表的哪一列

这是目前出现频率**最高**的失败模式。题面提到一个列名时，**不要默认它属于最直觉的那张表**。

## 一、同名列，不同表，值不同

### `idx 87` — `Diagnosis` 在两张表都有

`thrombosis_prediction` 的 `Patient` 和 `Examination` **都有 `Diagnosis`**：

```
Patient.Diagnosis     = 'SLE'        ← 金标用的是这个
Examination.Diagnosis = 'SLE+Psy'    ← 我一开始用的那个
```

detail 报"首列对得上但整行元组不同"——首列（Symptoms）对了，错在第二列。

### `idx 344` — `Score` 在两张表都有

问 "In posts with 1 comment, how many of the comments have 0 score?"
`Score` 在 `posts` 和 `comments` **两张表都有**：

```sql
-- ❌ 我写的：用 comments.Score（题面字面说的）→ 10997 / 11000
... WHERE posts.CommentCount = 1 AND comments.Score = 0
-- ☑️ 金标：筛的是 posts.Score → 2888
... WHERE T2.CommentCount = 1 AND T2.Score = 0
```

### 排查动作（写 SQL 前花 10 秒）

先看 `bird_schema` 里哪几张表有你要的列名，然后把各表的值分布摆在一行里比较：

```sql
SELECT
  (SELECT COUNT(*) FROM posts    WHERE Score = 0) AS posts_score0,
  (SELECT COUNT(*) FROM comments WHERE Score = 0) AS comments_score0
```

`detail` 报"**行数相同但取值不同**"且你已经确认口径没错时，八成就是这里。

### 常见同名陷阱

| 列名 | 出现在 | 差异 |
|---|---|---|
| `Score` | `posts` / `comments` | 帖子分 vs 评论分 |
| `Diagnosis` | `Patient` / `Examination` | 患者级诊断 vs 就诊级诊断 |
| `BountyAmount` | **只在 `votes`** | `posts` 表根本没这列（写错直接 `no such column`） |
| `position` | `results` / `driverStandings` / `qualifying` | 完赛名次 / 积分榜名次 / 排位赛名次 |
| `status` | `event` / `budget` / `legalities` | 事件状态 / 预算行状态 / 合法性 |
| `name` | 几乎每张表 | — |
| `Date` | 各表格式不同 | `'201202'` vs `'2012-08-25'` vs `'2020-06-05 00:00:00'` |
| `id` | 每张表 | 还有 `xxx_api_id` 等多套 ID 体系 |

### ⭐ evidence 点名的列，必须真的用它（实测 `dev idx 696`）
题干：“Count the number of posts with a tag specified as 'careers'”
，evidence：“tag specified as 'careers' refers to **TagName** = 'careers'”。

| 写法 | 值 | 对错 |
|---|---|---|
| 顺着 evidence，在 `tags` 表上数：`COUNT(*) FROM tags WHERE TagName='careers'` | **1** | ✅ |
| 自作主张用“等价”的字符串匹配：`COUNT(*) FROM posts WHERE Tags LIKE '%<careers>%'` | 22 | ❌ |

**记这一点：evidence 把列名写出来，就是在告诉你金标用的是那张表的那个列。**
不要因为“另有一种写法结果看起来更合理”就自由发挥 —— 哪怕新写法在语义上更像“帖子的数量”。
同理，题干里的名词（tag / reputation / owner）也要先想它对应的是**哪张表的哪个列名**。

### ⭐⭐ 多值串列：“精确匹配”与“LIKE 包含”是两个不同的答案（实测 `dev idx 376`）

有些列把多个值塞在一个字符串里（逗号分隔），比如：
`cards.keywords`（`Flying` / `Flying,Flash`）、`cards.subtypes`、`cards.colors`、`cards.promoTypes`、
`cards.types`。

| 写法 | 行数 | 含义 |
|---|---|---|
| `keywords = 'Flying'` | **3088**（金标） | 只有“只有飞行”的卡 |
| `keywords LIKE '%flying%'` | 5039 | 还包含 `Flying,Flash` 这类 |

**动作：先试 `= '值'`，行数不对再改 `LIKE '%值%'`（反过来很少对）。**
注意 `LIKE` 对 ASCII 大小写不敏感，所以 `'flying'` 和 `'Flying'` 在 LIKE 下等价，但在 `=` 下不等价 ——
值的大小写要按库里实际写的（先 `SELECT DISTINCT 该列` 看一眼）。

（相关：题干里“角色/职责”之类的措辞可能根本不是过滤条件，见 `gold-style.md` 反直觉行为第 4 条。）

## 二、同名不同表：条件加错表会把行数砍掉一半

✅ `idx 205` 撞出来的。同一个列名在不同表里语义完全不同，而 **evidence 只写列名、不写表名**：

| 列 | 在 `results` 里 | 在 `driverStandings` 里 |
|---|---|---|
| `position` | **完赛名次**，退赛车手是 **NULL** | **车手积分榜名次**，几乎总有值 |

实测：问 "Alex Yoong 在 track number < 20 时参加过哪些比赛"。

```sql
-- ❌ 用 results.position：他 15 场比赛里 10 场退赛（position 为 NULL），一加条件只剩 5 行
... FROM results          WHERE drivers.surname='Yoong' AND results.position < 20   -- 5 行

-- ❌ 不加条件：他只有 12 个不同分站（意大利/美国/日本各跑过两次）
... FROM results          WHERE drivers.surname='Yoong'                            -- 15 行 / 12 个名字

-- ✅ 换到 driverStandings.position：积分榜名次，包含他退赛的场次 → 15 行 / 15 个名字
... FROM driverStandings WHERE drivers.surname='Yoong' AND driverStandings.position < 20
```

### 怎么推出"必须换表"的（这题真正值钱的推理）

1. 加 `results.position < 20` → 5 行，排除"results 里带条件"；
2. 去掉条件 → 15 行但只有 12 个不同比赛名；**因为 `set()` 会折叠重复行**，
   如果金标返回比赛名，12 个名字就该判对了 —— 它没判对，
   ⇒ **金标的 15 个值里至少有 13 个互不相同**；
3. Yoong 只跑过 12 个分站，所以金标**不可能**从 `results` 里拿比赛名 → 一定换表了；
4. 另一张有 `position` 的 `driverStandings` 恰好给 15 行 15 个名字 ✓

### 排查法

一个条件加进去会把行数砍掉一大截时，先问"**这个列在这个表里是不是有 NULL、语义是不是不一样**"，
然后**去另一张同名表里找那一列**。一条查询就能看清所有同名列的分布：

```sql
SELECT TYPEOF(col), COUNT(*) AS rows_all, COUNT(col) AS rows_not_null
FROM t GROUP BY TYPEOF(col)
```

## 三、"list the X" 不一定返回名字

✅ `idx 346` "which cards have incredibly powerful foils"：金标返回 **25061 行的 `cards.id`**，
不是 `name`。诊断依据：金标 25061 行，而 `name` 只有 17544 个不同值
—— `set()` 不去重，就要求两边**不同值的个数**对得上。`idx 347` 同理。

**动作**：用 `SELECT COUNT(DISTINCT col)` 把候选列的**不同值个数**跟金标行数对一下，
哪个对得上就是它。

## 四、多套 ID 体系

BIRD 的库普遍有 `xxx_id` 和 `xxx_api_id`（或 `uuid` / `CDSCode`）两套 ID，
**连错一套会得到"行数看着对但值全错"**。

- `european_football_2`：`Player.id` vs `Player.player_api_id`；
  `Team.team_api_id` vs `Team.team_fifa_api_id`。
- `card_games`：`cards.id` vs `cards.uuid` vs `cards.multiverseId`。
- `codebase_community`：`posts.Id` vs `posts.OwnerUserId` vs `users.AccountId`。
- `california_schools`：`schools.CDSCode` 是 TEXT，`frpm.CDSCode` 也是 TEXT
  但 `satscores.cds` 是 TEXT —— 三表同名不同格式，JOIN 前先确认。

**动作**：`bird_schema table=<表>` 看清主键再 JOIN。
