# european_football_2 （7 表） · simple EX 73.8% (48/65)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. ⚠️ **「某球员的某属性」不要 `LIMIT 1`！** 金标给**全部历史快照**：
   1063=26 行、1086=24 行、1140=9 行（我都只给了 1 行）。
2. **「前 N 名球员」反而要去重**：`Player_Attributes` 一人多行，`crossing=95` 有 7 行、
   球员 30612 独占 4 行 → 先 `DISTINCT player_api_id`。
3. **`Player` 表没有国籍列**：「某国的球员」只能绕 `Match→League→Country`；硬 JOIN 会炸成上万行。
   另：`Player`/`Player_Attributes` 用 `player_api_id` 连，不是 `id`。

## 连接图与坑

```
Player ──player_api_id── Player_Attributes（一个球员多条历史记录！）
Team   ──team_api_id─── Team_Attributes
                            Match ──league_id── League
```
- **两套 ID**：`Player.id`（内部）vs `Player.player_api_id`（FIFA API）。
  `Player_Attributes.id` 又是属性表自己的主键。金标常用 `player_api_id` 连。
- ⛔ **已作废（第 15 轮推翻）**：曾按旧笔记写「问某球员的属性要 `ORDER BY date DESC LIMIT 1` 取一条」——
  **那条是错的**（`1063` 金标 26 行 = 全部历史快照）。
- 问“某球员的属性”时：⚠️ **不要 `ORDER BY date DESC LIMIT 1`**，也不要去重（见下）。
- `Player.birthday` 是 TEXT；`height/weight` 是 INTEGER；⚠️ **`Player` 表没有国籍/国家列**
  （“哪个国家的球员”只能绕 `Match` → `League` → `Country`，别硬 JOIN `Country`）。

**⚠️⚠️ 已验证的修正（全量 65 道：48 对 / 17 错，73.8%）**

1. ⚠️ **“某球员的某属性”——金标给的是全部历史记录，不是最新一条！**

   | idx | 题干 | 我写的 | 金标行数 |
   |---|---|---|---|
   | 1063 | Aaron Doran 的 potential | `ORDER BY date DESC LIMIT 1` → 1 行 | **26 行** |
   | 1086 | Ariel Borysiuk 的 heading_accuracy | 同上 → 1 行 | **24 行** |
   | 1140 | Alexis Blin 的三项分数 | 同上 → 1 行 | **9 行** |

   ⇒ **去掉 `LIMIT 1`，也别加 `DISTINCT`**，先把全部快照行交上去。
2. “前 N 名球员”仍然要去重（见上面 `1024`/`1027`）。
   **两条合起来的意思：这个库的粒度就是“球员×日期”，金标大多数时候不去重。**

**⚠️ 首批 13 道（8 对）实测：本库最大的坑就是“一个球员多行”**

`Player_Attributes` 里每个球员有 **N 条历史快照**（按 `date`），所以任何“top N 球员”的题：

| idx | 题干 | 我写的 | 问题 |
|---|---|---|---|
| 1024 | crossing 最好的前 5 球员 | `ORDER BY crossing DESC LIMIT 5` | 实测 `crossing=95` 有 **7 行**，其中球员 `30612` 独占 **4 行** → 名额被同一人占满 |
| 1027 | penalties 最多的前 10 全名 | 同上 | 同理，同一球员重复占位 |

⇒ **“排名 / 前 N”类题：先 `SELECT DISTINCT player_api_id`（或按球员取最新一条）再排名。**
另：“2010 年最高分”实测有 **两个球员并列**（90 分），金标却只回 1 行 —— 这类并列同样不可控。
（`1051` “highest potential 的所有球员”金标 6 行，说明**并不是所有题都去重**，还是得看题干用词。）

## ⚠️⚠️ moderate 全组实测（50 道，37 对 = 74%）—— 本库的口径坑清单

### ✅ 已证实、可直接照用的（都对了）

| 题型 | 做法 |
|---|---|
| 「某球员/某球队 on 某日期 的某属性」 | 1 行 1 列，`WHERE player_name=… AND date='YYYY-MM-DD 00:00:00'`（**1103–1113 九道全对**） |
| 「list/which players·teams …」 | **`SELECT DISTINCT` 名字**（1053 92 ✓ / 1062 409 ✓ / 1067 16 ✓ / 1088 1105 ✓ / 1124 3339 ✓ / 1130 43 ✓） |
| 平均类 | `AVG(列)` 直接写；证据里写作 `DIVIDE(SUM(x), COUNT(id))` 通常就是 `AVG`（1057 的 1.5041666666666667 ✓、1068/1093 除外） |
| 「第 1 名/最少/最多」 | **`ORDER BY … LIMIT 1`，并列也只回 1 行**（1026：3 队并列 0 负 → 金标 **1 行**） |

### ❌ 实测错的，以及由此得到的规则

1. **「List the top 5 leagues …」→ 2 列**（name + 指标），不是 1 列（1038：金标 **5 行 2 列**）。
2. **「which of these players performs best …」→ 2 列**（名字 + 那个指标）（1085：金标 **1 行 2 列**）。
3. **证据写 `MAX(列)` ⇒ 是「单行最大值」，不是合计**（1146：我 `SUM(away_team_goal)` 分组取最大 → `FC Barcelona`；金标应是 `WHERE away_team_goal = (SELECT MAX(away_team_goal) FROM Match)` 那支球队）。
4. **「top N 的某属性值」→ 给原始行、不要去重**（1029：我 `DISTINCT buildUpPlaySpeed` 4 个值 → ✗）。
5. ⚠️ **计数是本库最大的运气源（两种都真实存在）**：
   - `COUNT(*)` 对：1023（`overall_rating BETWEEN 60 AND 65 AND defensive_work_rate='low'` → **3594** ✓，同题 distinct 只有 733）；
   - `COUNT(*)` 错、应为去重：1052（weight<130 且 preferred_foot='left'：我 93 → 金标 **9** = distinct player）、1080（left + attacking_work_rate='low'：我 1569 ✗）；
   - ⇒ **题干主语是「players」时优先 `COUNT(DISTINCT player_api_id)`**；「how many matches / teams」才用 `COUNT(*)`。
6. **「top 5 … 的 ID」金标可能给 `player_fifa_api_id`**（1135：我给了 5 个 `player_api_id` → ✗）。
7. **仍未解开（都已看金标明细，不重交，仅记线索）**：1032（`name, COUNT(*)`=`Spain LIGA BBVA, 3040` 与 max 一致，差在列序或第二列定义）、
   1068 / 1093（AVG 的几种 JOIN/写法变体都不等于金标）、1073（`Germany 1. Bundesliga` 我 2448 ≠ 金标）、1107（`MIN(date)`=2013-02-15 ≠ 金标）。

**做题提示**：本库 50 道 moderate 里 13 道错，其中 **7 道是「计数去不去重」和「列数 1 还是 2」** —— 这两类占总错的 54%。

## 惯例卡片（实测统计，n=115 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 25 / COUNT(DISTINCT) 3 / COUNT(*) 1 / 无 86　⇒ 本库以 `COUNT(列)` 为主（25/29 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：Player 57 / Team 18 / Player_Attributes 14 / League 9 / Country 9 / Match 4 / Team_Attributes 3 / TEAM 1　⇒ 主表以 **Player** 为主但**不固定**（57/115）⇒ 按题干主语选
- `SELECT DISTINCT`：21/115　|　`*100`：2　|　`BETWEEN`：4
- 输出列数分布：1列×107 / 2列×6 / 3列×2
- JOIN 数分布：0:27, 1:82, 2:5, 3:1

> 由 `bird_conventions db=european_football_2 write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
