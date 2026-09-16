# california_schools （3 表） · simple EX 94.4% (51/54)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

1. ⭐ **概念→列**（moderate 高频，猜错就是 0 分）：
   `schools.DOC`（**52**=Elementary School District / **54**=Unified）、`SOC`（**11**=Youth Authority/CEA）、
   `EILCode`（**'HS'**=高中）、`EdOpsCode`（**'SSS'**=State Special School / **'SPECON'**=Special Education Consortia）、
   `NCESDist`（NCES 区号）、`Latitude`/`Longitude`、`StatusType='Closed'`、
   管理员 = `AdmFName1/2/3` + `AdmLName1/2/3` + `AdmEmail1/2/3`；
   `frpm."School Type"`（`'Continuation Schools'`）、`frpm."NSLP Provision Status"`
   （`'Lunch Provision 2'` / `'Breakfast Provision 2'` / `'CEP'` / `'Provision 1/2/3'` / `'Multiple Provision Types'`）。
2. ⭐ **`JOIN` 选谁**：`列学校 + SAT 分数` 类用 **`LEFT JOIN satscores`**（实测 `27`：金标 8574 行 = 纯 `schools` 行数）；
   CDS 前导 0 → **先 naive `ss.cds=s.CDSCode`**，空集/可疑再改 `CAST(s.CDSCode AS INTEGER)=ss.cds`。
3. ⭐ **县 vs 市**：题干 “schools in X”（X 是县名）→ 用 **`County`**，不是 `City`
   （实测 `26`：`City='Monterey'` → **0 行**；`County='Monterey'` → 6 行）；`County` 值**不带 'County'**。
   “free or reduced-priced meals”→ `Free Meal Count (...)`（`FRPM Count` 是另一列）。

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
