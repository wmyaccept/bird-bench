# california_schools （3 表） · simple EX 94.4% (51/54)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

1. ⭐ **概念→列**（moderate 的命门，猜错直接 0 分；下表是复盘挂起题后改对的）：

   | 题干说法 | 真正该用的列 |
   |---|---|
   | “type of educational option” / “continuation school” | **`frpm."Educational Option Type"`**（值 `'Continuation School'`）⚠️ 不是 `schools.EdOpsName`，也不是 `frpm."School Type"` |
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
3. ⭐ **行数差一点时先查“学区行”和地名口径**：`schools` 里混着学区行（`School`/`School Name` 为 NULL），
   题干要“学校”时必须 `School IS NOT NULL`（`49`：金标 858 行、我 879 行）；
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
