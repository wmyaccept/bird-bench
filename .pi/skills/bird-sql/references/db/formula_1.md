# formula_1 （13 表） · simple EX 75.2% (88/117)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

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

1. ⚠️ **本库的输出粒度是混合的，不要无脑加 `DISTINCT`**（这条通则本轮被自己的数据证伪）：

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
