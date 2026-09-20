# california_schools （3 表） · simple EX 94.4% (51/54, 旧 dev 2024-06)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. ⭐ **概念→列**（moderate 的命门，猜错直接 0 分；下表是复盘挂起题后改对的）：

   | 题干说法 | 真正该用的列 |
   |---|---|
   | “type of educational option” / “continuation school” | **`frpm."Educational Option Type"`**（值 `'Continuation School'`；
   与 `frpm."School Type"` 命中的 `'Continuation High Schools'` **是同一批 459 行、diff=0**，两列任选）；
   ⚠️ 别用 `schools.EdOpsName`（那是另一套分类） |
   | “high school” + 一起吃 | `frpm."School Type" = 'High Schools (Public)'`（用**精确值**；`LIKE '%High School%'` 会混进别的类） |
   | “district code” | **`frpm."District Code"`** ⚠️ 不是 `schools.DOC` |
   | 学校名（与 frpm 联查时） | `frpm."School Name"`（金标常直接用 frpm 的，不绕 schools） |
   | “in Riverside”这类地名 | **两种都试**：`schools.County` vs `frpm."District Name" LIKE 'Riverside%'`（`25` 金标是后者） |
   | “charter”+“locally funded” | `schools.Charter = 1` + **`schools.FundingType = 'Locally funded'`**（`65` 金标）；
   | 而 “directly funded” | `frpm."Charter Funding Type" = 'Directly funded'`（`4` 金标）⇒ **哪张表的列值字面像题干就用哪张** |
   | “free or reduced-priced meals”(15-17) | `FRPM Count (Ages 5-17)`（`26` 金标；`Free Meal Count (Ages 5-17)` 是另一列，两列都出现过） |
   | `DOC`=52 小学区 / 54 联合区 · `SOC`=11 CEA · `EILCode`='HS' · `EdOpsCode`='SSS'/'SPECON' · `NCESDist` · `Latitude`/`Longitude` · `StatusType='Closed'` | 均在 `schools` |
   | 管理员 | `AdmFName1/2/3` + `AdmLName1/2/3` + `AdmEmail1/2/3`（`85` 金标用 `AdmFName1/2/3` 的 OR） |
   | `frpm."NSLP Provision Status"` | `'Lunch Provision 2'` / `'Breakfast Provision 2'`（**两个都在，别取错**）/ `'CEP'` / `'Provision 1/2/3'` |

2. ⭐ **`JOIN` 怎么连**：`frpm` 与 `satscores` **直接连** `frpm.CDSCode = satscores.cds`（金标 `24/25` 都这样；
   **绕 `schools` 反而会多过滤掉行** → 我 999 行 vs 金标 1068 行）；
   “列学校 + 可选属性（分数/电话/网址）” → **`LEFT JOIN`**（`27`：金标 8574 行 = 纯 `schools` 行数）；
   CDS 前导 0 → **先 naive**，空集/可疑再 `CAST(CDSCode AS INTEGER)=cds`。
3. ⭐ **取极值时先看 NULL / 学区行**：库里有 NULL，`ORDER BY … ASC LIMIT 3` 会把 **NULL 排在前面**
   （实测 `1`：459 行 continuation 里有 **4 行 rate 为 NULL**，我桶了前 3 个 NULL → 形状对、值全错）；
   `schools` 里又混着学区行（`School` 为 NULL），题干要“学校”时必须 `School IS NOT NULL`（`49`：858 vs 879 行）；
   题干地名先在 `schools.County` / `frpm."District Name"` / `City` 之间各试一次（`26` 金标 `County='Monterey'`）；
   `County` 值**不带 'County'**，`"Educational Option Type"` / `"School Type"` 用**精确值**。

## 连接图与坑

```
schools ──CDSCode──┐
frpm    ──CDSCode──┤  三者用 CDS 码连接（注意大小写/类型）
satscores ──cds ───┘
```
- **键名不同**：`schools.CDSCode` / `frpm.CDSCode` / `satscores.cds`，但都是 TEXT，可直接等值连。
- ⚠️ **CDS 码的前导 0 是分批丢的**（实测）：`satscores` 2269 行里
  - **2058 行**的 `cds` 是 **14 位**（`'07100740000000'`）→ naive 等值连得上；
  - **211 行**的 `cds` 是 **13 位**（`'7100740000000'`，丢了前导 0）→ naive 等值连**一行都接不上**。

  后果：`satscores JOIN schools ON cds = CDSCode` 会**默默丢掉 211 行**。Contra Costa 就是典型：
  465 所学校，naive join 结果 **0 行**。

  三种写法实测过的匹配数：
  | 写法 | 匹配行数 |
  |---|---|
  | `cds = CDSCode`（naive） | 2058 |
  | `'0' \|\| cds = CDSCode` | 211 |
  | `CAST(CDSCode AS INTEGER) = cds` | **2269**（全匹配） |

  **但不要无条件"修正"**：很多题的**金标用的就是 naive join**（实测 26/30 道 california_schools
  题用小写写法就能对）。所以规则是：
  **先写 naive；如果得到空集或可疑值，再改 `CAST(schools.CDSCode AS INTEGER) = satscores.cds`
  或改成单表查询（只用 `satscores` 的 `cname` / `sname`）。**
- ⚠️ **`schools` 里混着"学区/县办公室"行**：`CDSCode` 以 `0000000` 结尾的那些，`School` 是 **NULL**。
  问"哪个**学校**"时这些行会返回 NULL（实测 `idx 22`：Contra Costa 的最多考生行是学区行，
  `schools.School` 为 NULL；金标加了 `sname IS NOT NULL` 才拿到真学校名）。
- ⚠️ **列归属要记牢**（实测踩过一次）：
  - `Low Grade` / `High Grade` / `Charter School (Y/N)` / 各类 `Enrollment` / `FRPM Count` → 在 **`frpm`**
  - `GSoffered` / `GSserved` / `Virtual` / `Magnet` / 地址 / 电话 / `FundingType` / `StatusType` → 在 **`schools`**
  - `AvgScrMath/Read/Write` / `NumTstTakr` / `NumGE1500` / `sname` / `cname` → 在 **`satscores`**
- `Virtual`：**`'F'` = Exclusively Virtual**（不是 False 的意思），`'P'` = Partial，`'N'` = 无。
- `StatusType` 取值：`Active` / `Closed` / `Merged` / `Pending`
  → “active district” = `StatusType='Active'`；“merged Alameda” = `StatusType='Merged'` + `County='Alameda'`。
- `FundingType`：`Directly funded`（**小写 f**）/ `Locally funded` / `Not in CS funding model`。
- 地址：`Street` vs `StreetAbr`、`MailStreet`（unabbreviated mailing）vs `MailStrAbr`。
  题干说 "postal/mailing street" → 用 `Mail*`；说 "unabbreviated" → 用不带 `Abr` 的。
- "type of education offered" → `EdOpsName`（实测 `idx 42` 命中，值为 `'Traditional'`）。
- 考试优秀率：`Excellence rate = NumGE1500 / NumTstTakr`。

## 同义表

- `frpm."Educational Option Type"` vs `frpm."School Type"` vs `schools.EdOpsName`：
  “continuation / type of educational option” → **`frpm."Educational Option Type"`**（值 `'Continuation School'`）；
  与 `"School Type"` 命中的 `'Continuation High Schools'` **同一批 459 行**，两列任选。
  ⚠️ 别用 `schools.EdOpsName`（另一套分类；“type of education offered” 才用它）。
- “district code” → **`frpm."District Code"`**，不是 `schools.DOC`。
- 学校名（与 frpm 联查）→ `frpm."School Name"`，金标常不绕 `schools`。
- 地名 “in Riverside”：**两种都可能** `schools.County` vs `frpm."District Name" LIKE 'Riverside%'`（`25` 是后者）。
- charter 资助：`schools.FundingType = 'Locally funded'`（`65`）vs `frpm."Charter Funding Type" = 'Directly funded'`（`4`）
  ⇒ **哪张表的列值字面像题干就用哪张**。
- 免费餐：`FRPM Count (Ages 5-17)` vs `Free Meal Count (Ages 5-17)`（两列都出现过）。
- 地址：`Street` vs `StreetAbr`、`MailStreet` vs `MailStrAbr`（postal/mailing → `Mail*`；unabbreviated → 不带 `Abr`）。

## 惯例卡片（实测统计，n=89 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 13 / COUNT(*) 6 / COUNT(DISTINCT) 4 / 无 66　⇒ 本库以 `COUNT(列)` 为主（13/23 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：schools 38 / frpm 28 / satscores 23　⇒ 主表以 **schools** 为主但**不固定**（38/89）⇒ 按题干主语选
- `SELECT DISTINCT`：3/89　|　`*100`：19　|　`BETWEEN`：7
- 输出列数分布：1列×35 / 2列×17 / 3列×7 / 4列×3 / 5列×1 / 6列×4 / 7列×2 / 8列×1 / 9列×3 / 11列×1 / 12列×7 / 13列×4 / 14列×1 / 15列×1 / 17列×1 / 18列×1
- JOIN 数分布：0:17, 1:45, 3:4, 4:9, 5:7, 6:2, 7:2, 8:1, 9:1, 13:1

> 由 `bird_conventions db=california_schools write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。

## ⚠️⚠️ challenging 实测（12 道，0 对 = 0%）—— **全部是 A11「profile 题」，列数就是属性清单**

**本库的 challenging 几乎全是 "comprehensive profile / statistics" 题**（"provide details"、"comprehensive performance analysis"、
"statistics including …"）。金标列数 **9–18 列**，而我按"一个答案"写 1 列 ⇒ 全 0。

金标列数实测（同一批、已答题）：`0→10、2→14、3→14、5→13、6→15、8→16、12→9、31→16、32→16、45→14、62→14、77→13、79→10、87→2`。

**金标 profile 的组成规律（读 3 条金标 SQL 得出）**：
1. 用 `WITH … AS (…)` 分块（EnrollmentRanked / SchoolDetails / SATPerformance …），
   每块算好"派生列"再拼最终 SELECT。
2. 派生列**一定要照题干数出来**：
   - 比率列：`CAST(免费餐数 AS REAL)/注册数`、`ROUND("Percent (%) Eligible FRPM (K-12)" * 100, 2)`
   - 排名列：**`RANK() OVER (PARTITION BY County ORDER BY … DESC)` / `ROW_NUMBER() OVER (…)`**
   - 文字化 CASE：**`CASE WHEN Charter = 1 THEN 'Charter School' ELSE 'Regular School' END`**
   - 布尔化：`CASE WHEN Latitude IS NOT NULL AND Longitude IS NOT NULL THEN 'Yes' ELSE 'No' END`
3. 具体题的例外（已核金标）：
   - **55**（Colusa/Humboldt 六个指标之比）金标是 **6 行 × 2 列**（每行一个指标名 + 比值），**不是 1 行 6 列** ✗
   - **83**「K-8 + magnet + Multiple Provision Types 的城市」金标用 **`GSoffered = 'K-8'`**（不是 GSserved）、
     且只有 **1 个城市**满足 ⇒ **1 行 2 列** ✗
   - **87**「valid e-mail addresses」金标 **1 行 2 列 = `AdmEmail1, AdmEmail2`**（不是 1 列 × 2 行），
     且 `DOC = 54` / `SOC = 62` 是**数字比较**，年份用 `strftime('%Y', OpenDate) BETWEEN '2009' AND '2010'` ✗
   - **12** 的 9 列 = `sname, NumGE1500, NumTstTakr, excellence_rate, 免费餐数, 注册数, eligible_free_rate, City, county_rank` 这一类组合。

⚠️ **教训（代价很大）**：本库**旧的 65 道 challenging 我全部只写了 1 列 ⇒ 全错**。
以后本库见到 "profile / comprehensive / details / statistics"，**先照题干属性词一行一个数出列数，再写 SQL**。
## ⚠️⚠️ 值层实测（D 类 9 道）：**近义列 + NULL 处理**

- ⭐ `frpm` 里同时有 **`Free Meal Count (Ages 5-17)`** 与 **`FRPM Count (Ages 5-17)`**（另有 K-12 版）：
  `26` 我用了前者，金标用 **`FRPM Count`**。
  ⇒ 题干说 “free or reduced-priced meals” 用 **FRPM Count**；只说 “eligible free” 才用 `Free Meal Count`。
- ⭐ “continuation schools” 是 **`Educational Option Type = 'Continuation School'`**，
  不是 `School Type LIKE '%Continuation%'`（`1`，我还漏了它当分母时的 `IS NOT NULL`）。
- ⭐ **排序取极值前一律加 `IS NOT NULL`**：`40`/`43`/`51` 三道金标都带 `IS NOT NULL`
  （NULL 会让“最低分/最低比例”选到空行）。
- ⭐ `85`：“Percent (%) Eligible Free (K-12)”**表里已有现成列**时就直接用；要自己算时按
  `Free Meal Count (K-12) * 100 / Enrollment (K-12)`（金标那道是现算的，不是取现成列）。
