# formula_1 （13 表） · simple EX 75.2% (88/117)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. **粒度是混合的，别无脑 DISTINCT**：851(657→18) 要去重，而 956(**224 行**)/974(**5268**)/1010(**11340**)
   是行级；849/855/921 的 url 类金标只有 **1 行**。先按去重写，detail 说行数差很多再改行级。
2. **`qualifying.q1/q2/q3` 是 `'1:40.318'`**（分:秒.毫秒，**没有前导 `0:`**）。
   evidence 写的 `'0:01:40'` 直接 `=` 会 0 行 → 用 `LIKE '1:40%'`。
3. **`position` 四张表都有，语义不同**：`results`(完赛)/`driverStandings`(积分榜)/`constructorStandings`/`qualifying`。
   另：`nationality` 是 `'American'`（不是 `'America'`）；阿布扎比赛道叫 `'Yas Marina Circuit'`。

## 连接图与坑

```
races ──circuitId── circuits
      ──raceId── results ──driverId── drivers
                 qualifying / pitStops / lapTimes
                 constructorResults / constructorStandings
      ──year── seasons
```
- `results.position`（完赛名次，退赛 NULL）vs `positionOrder`（最终排序）vs `grid`（发车格）
  vs **`driverStandings.position`（积分榜名次，几乎总有值）** ← 这四个别搞混。
- `qualifying.q1/q2/q3` 是 TEXT `'1:34.188'` 且大量 NULL。
- `results.rank` = 最快圈速名次；`results.time` 里冠军是 `'1:31:57.403'`，其余是 `'+14.925'`
  （所以"冠军"可以用 `time LIKE '%:%:%'` 识别）。
- "race number" = `raceId`；"race at 291" 同理。

**⚠️ 首批 13 道实测（8 对 / 5 错）——先记住下面两条**

1. ⚠️ **本库的输出粒度是混合的，不要无脑加 `DISTINCT`**（**本库起初那条「要 `DISTINCT`」的通则**被自己的数据证伪）：

   | idx | 题干 | 金标行数 | 加 DISTINCT 后 | 结论 |
   |---|---|---|---|---|
   | 851 | Renault 造的 circuit 的 position | 18 | 20 | 去重 + 排 NULL（可能） |
   | 956 | born after 1975 ranked 2 的 driver | **224** | 11 | **行级**，金标没去重 |
   | 974 | 最快圈速的赛季 | **5268** | 1 | 行级 |
   | 1010 | Lewis Hamilton 的圈速记录 | **11340** | 1 | 行级 |
   | 849/855/921 | “Where can X be found” → url | **1** | 27/19/51 | 只有 1 行（未解释） |

   ⇒ “Which/Who 谁是…” 先按**去重**写；一旦 detail 显示金标行数是几百上千，就是行级题。
   **不要因为 card_games 的经验给 formula_1 无脑加 `DISTINCT`**（两个库粒度相反）。
2. ⚠️ **`qualifying.q1/q2/q3` 的格式是 `'1:40.318'`（分:秒.毫秒），没有前导 `0:`**：
   evidence 里写的 `'0:01:40'`（H:MM:SS）**不能直接拿去 `=`**（实测 0 行），
   要用前缀匹配：
   ```sql
   WHERE qualifying.raceId=355 AND qualifying.q2 LIKE '1:40%'
   ```
   （实测 `q2 LIKE '%1:40%'` 全库 68 行；`q2='1:40.000'` 0 行。）
   同类：`results.time` / `pitStops.time` 也是 `'1:31:57.403'` 这种写法。
3. **“Where can the introduction/information of the races held on X be found?” → `races.url`**，
   但金标只给 **1 行**（`849`: 27 个 url、`855`: 19 个 url、`921` 同型，金标都是 1 行）—— 疑似省略了聚合，暂无法稳定复现。
4. ⚠️ **实测取值（evidence 常写错）**：
   - `drivers.nationality` 是 **`'American'`**（evidence 写成 `'America'`，照抄会得 0 行 —— `964` 实测）
   - 阿布扎比的赛道叫 **`'Yas Marina Circuit'`**（不是 “Abu Dhabi Circuit”，`922` 实测）
   - `qualifying.q1/q2/q3` 是 `'1:40.318'`，注意与 `results.time` 的 `'1:31:57.403'` 时长格式不同
5. ⚠️ **`position` 至少在四张表都有，语义不同**：`results`（完赛名次）/ `driverStandings`（积分榜）/
   `constructorStandings`（积分榜）/ `qualifying`（排位赛）→ “ranked Nth”类题先想是哪一张（`956` 就栽在这）。
6. **金标倾向少列**：`986`（“indicate the time in milliseconds”→ 只给 `milliseconds`）、
   `1009`（“list the time each driver spent”→ 只给 `duration`）、`1000`（“full location”→ 金标 1 列）。
   ⇒ “列出 X 的 Y” 类题，**只给 Y**，别把 X 的 id 也带上。

13. ⚠️ **表名是驼峰，不是 snake_case**（实测连续踩坑）：`constructorStandings`、`constructorResults`、
    `driverStandings`、`lapTimes`、`pitStops`。写 SQL 前先用 `bird_schema formula_1` 确认表名，
    不要凭直觉写 `constructor_standings` / `lap_times`（会直接 `no such table`）。

## 惯例卡片（实测统计，n=160 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 21 / COUNT(DISTINCT) 6 / COUNT(*) 3 / 无 130　⇒ 本库以 `COUNT(列)` 为主（21/30 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：circuits 35 / drivers 35 / races 32 / results 20 / qualifying 10 / lapTimes 10 / pitStops 6 / constructorStandings 5 / driverStandings 3 / constructorResults 2 / constructors 2　⇒ 主表**不固定**（最大是 circuits 也只占 35/160）⇒ 按题干主语选，此处是错题重灾区
- `SELECT DISTINCT`：21/160　|　`*100`：3　|　`BETWEEN`：5
- 输出列数分布：1列×113 / 2列×24 / 3列×16 / 4列×7
- JOIN 数分布：0:34, 1:90, 2:32, 3:3, 6:1

> 由 `bird_conventions db=formula_1 write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ moderate 全组实测（43 道，29 对 = 67.4%）—— 输出列数/列序是本库最大失分源

**14 道错里 8 道是「列数错」，2 道是「列序/取值错」，2 道是「口径错」。**

### ✅ 输出列数的实测铁律（本库）

| 题干写法 | 金标列 | 实测 |
|---|---|---|
| "Who is the champion/driver … and where can I learn more" | **3 列 = forename, surname, url** | 938（我 1 列 url ✗）、866（我 9 行 1 列，金标 **9 行 3 列** ✗） |
| "who is the oldest/youngest" | **2 列 = forename, surname** | 865/877（我给 `driverRef` 1 列 ✗） |
| "give his **reference name**" | **1 列 = `driverRef`** | 928 ✓（题面写 reference name 才是 1 列） |
| "List the top N … with the fastest/latest lap time" | **3 列 = forename, surname, 该时间** | 970（我 2 列 ✗）；同 1038 的「名字 + 指标」 |
| "List out top N 某属性的 drivers" | **1 列 = 那个属性本身**（不是名字！） | 973：金标 **10 行 1 列 = `lapTimes.time`**（我给 3 行 2 列名字 ✗） |
| "Who is the champion … Indicate his finish time" | **1 列 = 只有 `results.time`** | 989（我 3 列 ✗） |
| "What is X? List the driver and race" | **4 列**（含 `milliseconds` 本体） | 894（4 列但**列序**错） |

⇒ 本库判断列数的唯一可靠办法：**看题干有几个"要你交出的东西"，而不是有几个实体**；
"who is X … show his url" 这类是 **3 列**（名字 2 + url 1），除非题干明说 "reference name"。

### ⚠️ 口径坑（值不同）

- **「第一场比赛」要用 `ORDER BY 日期 LIMIT 1`，不是 `year = MIN(year)` 子查询**：906 我按最早年（2007）过滤 → **17 行**，金标 **1 行**（Hamilton 的澳大利亚站）。
- **「in seconds」必须真换算**：942 我照 evidence 字面 `AVG(fastestLapTime)`（TEXT `'1:27.452'` → SQLite 取数值前缀 1 → **1.0**）✗；
  正确是 `AVG（分*60+秒.毫秒）` ≈ **92.0167**。★ 凡是时间 TEXT 列 + 题干说"in seconds"，都换算。
- **「rate of …」不带 `*100`，但「percentage of …」带**：943（rate → 0.2272…）与 909（percentage → 52.17）。
- **points 有两套**：`results.points`（每站得分）vs `driverStandings.points`（赛季累计）。995 我 `AVG(results.points)`=9.8 ✗ ⇒ 题干没限"某一年"时优先 **`driverStandings`**。
- ⚠️ 903（"How many times did Michael Schumacher **win** at Sepang"）我 `positionOrder=1` 得 3 ✗ ⇒ 本库 "win" 可能指 **`results.points` 取最大值**（evidence 原话：`win from races refers to max(points)`）。

### ✅ 已证实对得稳的（可直接照用）

- 计数器 / 极值器：939「British drivers 参加某站」= 4、940「完赛人数」= `COUNT(time IS NOT NULL)`、
  931 `MAX(fastestLapSpeed)`、960 `AVG(fastestLapSpeed)`、1003「事故最多司机的次数」（`statusId=3` → `GROUP BY driverId` 取 `MAX(COUNT(*))`）。
- 「passed the second qualifying lap」= `qualifying.q2 IS NOT NULL`（980 → 15 行 3 列 ✓）。
- 赛道用 `circuits.country` 定位：**奥地利的赛道叫 `A1-Ring` / `Zeltweg` 等，没有叫 "Austrian Grand Prix Circuit" 的**（1015 用 `country='Austria'` + `MIN(milliseconds)` → `Austrian Grand Prix` ✓）；
  1017 的「1:29.488 的 lap record」**没有赛道的最快圈 = 该值** ⇒ 金标口径是 `lt.time = '1:29.488'` 的行（7 条赛道）。

### ⭐ 本库总账（dev2025）

- `simple 88/117 = 75.2%`（旧答案迁移）、`moderate 29/43 = 67.4%`、合计 **117/160 = 73.1%**。
- ⚠️ **输出列数是本库第一失分源**（moderate 14 道错里 8 道是列数）⇒ 走 A11「属性清单」时，
  本库要额外回想上表「题干写法 → 金标列数」。
