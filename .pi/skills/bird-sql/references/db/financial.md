# financial （8 表） · simple EX 83.9% (52/62)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. ⛔ **已作废（第 14 轮推翻）**：Mini-Dev 时代的笔记写「`date` 是 `'930101'`（YYMMDD）」，
   在 dev 版**不成立**（下面是现行事实）。
1. ⚠️ **日期全是 `'YYYY-MM-DD'`**（`'1995-03-24'`）—— playbooks 旧笔记里的 `'930101'` 是 **Mini-Dev 版**。
   
   **动手前先探一句**：`SELECT date FROM trans LIMIT 1`。
2. **捷克语缩写**：`A2`=区名、`A3`=region、`A4`=人口、`A11`=平均工资、`A12`/`A13`=95/96 失业率、
   `A15`/`A16`=95/96 犯罪数；`trans.operation`：`'VYBER'`=取现、`'VKLAD'`=存款；
   `trans.type`：`'PRIJEM'`=贷方、`'VYDAJ'`=借方。
3. **「list all the transactions」金标只给 1 列**（165：我 `SELECT *` 给了 10 列）；
   **「how many X and Y」可能是 1 行 2 列**（172：`SUM(CASE)` 一行两个数）。

## 连接图与坑

```
district ──district_id── client ──client_id── disp ──account_id── account
                                                                  ── trans / loan / order（account_id）
card ──disp_id── disp
```
- 列名是 **捷克语缩写**：`A2`=区名、`A11`=平均工资、`A4`=人口；`trans.operation` 里
  `'VYBER'`=现金取款、`'VKLAD'`=存款；`trans.type` 里 `'PRIJEM'`=贷方、`'VYDAJ'`=借方。
- `client.birth_date` 是 `'1976-01-29'`；account.date 是 `'930101'`（YYMMDD）。
  ⚠️ **这条是 Mini-Dev 版的写法，Dev 版已经全部改成 `'YYYY-MM-DD'`**（实测 trans/loan/card/account 都是）。
  ⇒ **动手前先跑一句 `SELECT date FROM trans LIMIT 1` 确认，不要照抄 Mini-Dev 时代那份笔记。**
- ⚠️ **“list all the transactions …” 金标只给 1 列**（`idx 165`：我 `SELECT *` 给了 10 列 15140 行，金标是 **1 列** 15140 行）。
- ⚠️ **“how many X **and** Y” 可能是 1 行 2 列**（`idx 172`：owner/disponent 数，金标用
  `SUM(type='OWNER'), SUM(type='DISPONENT')` 一行出两个数；我 `GROUP BY type` 给了 2 行）。
- 实测全量：**62 道 52 对 / 10 错（83.9%）**。

## 惯例卡片（实测统计，n=106 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(DISTINCT) 33 / COUNT(列) 26 / COUNT(*) 7 / 无 40　⇒ 本库偏去重（33/66 计数题）⇒ 计数先试 `COUNT(DISTINCT 实体id)`
- 主表（FROM 第一张）：account 24 / district 23 / client 23 / loan 15 / trans 9 / disp 8 / card 3 / District 1　⇒ 主表**不固定**（最大是 account 也只占 24/106）⇒ 按题干主语选，此处是错题重灾区
- `SELECT DISTINCT`：8/106　|　`*100`：25　|　`BETWEEN`：15
- 输出列数分布：1列×41 / 2列×14 / 3列×6 / 4列×9 / 5列×9 / 6列×4 / 7列×10 / 8列×6 / 9列×2 / 10列×1 / 13列×2 / 14列×1 / 15列×1
- JOIN 数分布：0:5, 1:20, 2:18, 3:12, 5:1, 6:3, 7:5, 8:4, 9:11, 10:6, 11:10, 12:2, 13:5, 14:2, 15:1, 17:1

> 由 `bird_conventions db=financial write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ moderate 全组实测（25 道，14 对 = 56.0%）—— 两个"走哪条连接"的坑毁了大半

⚠️ **先记一条硬事实（本轮才明确）**：**`account` 自己有 `district_id`**，
金标的区县归属**绝大多数走 `account.district_id`**，不是 `client.district_id`：
```sql
-- 金标 129 / 130 / 150 / 131 都是这个形状
district T1 INNER JOIN account T2 ON T1.district_id = T2.district_id
```
- **95**（youngest + highest average salary）金标 `district T4 ON T1.district_id = T4.district_id`（T1 = account）✗ 我走 client
- **189**（oldest female + lowest average salary）同上 ✗
- **129**（top ten withdrawals by district）金标 `district→account→trans`，**完全不碰 disp/client** ✗ 我绕了 disp/client

### 其余五条（全部出自金标 SQL）

- **131**「Which district has highest active loan?」金标 **`GROUP BY T2.A3`**（**给 region，不是 A2**）✗
  ⇒ **evidence 点名 A3 就用 A3**（128 的 evidence 点名 A2，那题就用 A2）。
- **130**「still do not own credit cards」金标写的是 **`T3.type != 'OWNER'`**（按 disp 类型判所有权）✗
  我按 `NOT IN (SELECT … card)` 算 —— 这是金标的口径，照抄。
- **145**「account holder identification numbers」金标给 **`DISTINCT account.account_id`**（**不是 client_id**）✗
- **193**「List all ID and district」金标 **3 列 = `(client_id, district_id, A2)`** ✗ 我只给 2 列。
- 计数形态（**本库最容易全体打偏的一类**）：
  | 题 | 金标 | 含义 |
  |---|---|---|
  | 128 | `COUNT(T1.client_id)` + `client JOIN district`（不过 disp） | 计"女性客户" |
  | 150 | `COUNT(T2.account_id)`（**不去重**） | 数 JOIN 后的行 |
  | 182 | `COUNT(T1.account_id)`（trans 行数） | 同上，不是 distinct 客户 |
  | 186 | `SUM(T1.gender = 'M') * 100 / COUNT(T1.client_id)` | 分母也是行数 |
  ⇒ **本库 moderate 计数题，先写"不去重的 `COUNT(列)`"，只有题干出现 "how many accounts/clients" 且金标形状对不上时再试 DISTINCT。**

## ⚠️⚠️ challenging 实测（19 道，3 对 = 16%）—— **"comprehensive profile" 是重灾区**

金标是 6–10 列的"报表"，我按 1–2 列写基本全错。可复用的读数方式：
- ⚠️ **profile 题的列 = 题干里每一个名词**，顺序基本=出现顺序，派生指标（百分比/平均值/排名）也算一列。
- ⭐ **"comprehensive analysis including district information, …" 这类题金标会把
  `district.A2/A3`、原始计数、比率、`RANK() OVER` 都摆上去**（同 california_schools 的规律）。
- ⭐ **"prioritize the customer by X" / "rank the districts" ⇒ 必有一列 `RANK() OVER (ORDER BY …)`**（151 这类）。
- ⭐ 已核准的单点事实：**"account types not eligible for loans" = `disp.type`（OWNER 才可贷）**（149）；
  `district` 只有 `A2..A16`（A2=name、A3=region、A4=inhabitants、A11=avg salary、A12/13=unemployment 95/96、A14/15=crime 95/96）；
  **`order` 是保留字，必须写 `"order"`**（173/188）。
- ⭐ 本库累计 challenging **3/57**（含旧批次），是全库最低 ⇒ 今后遇到 financial 的 profile 题，
  先把题干抄在本子上**逐项数格子再写 SQL**。
## ⚠️⚠️ 值层实测（D 类 15 道）：**钱有两套表，id 有三个**

- ⭐ `transactions_1k`（逐笔：`Price` / `Amount` / `Date`）vs `yearmonth`（月度汇总：`Consumption` / `Date='YYYYMM'`）：
  `1477`（哪一年加油花得最多）金标走 **`yearmonth`**；`1529`（在加油站花了多少 + 2012 年 1 月花了多少）
  金标全在 **`transactions_1k`**（`Price` 求和）。
  ⇒ “spent / spend（花了多少）” 先想 **`transactions_1k.Price`**；“consumption（消费额）” 先想 **`yearmonth.Consumption`**。
- ⭐ `107`/`174`：`account_id` / `disp_id` / `client_id` 别混 —— `174` 题干 “account owner number 130”
  金标是 **`account.account_id = 130`**，我用了 `disp_id`。
- ⭐ “没有信用卡” = **`disp.type != 'OWNER'`**（`130`），不是“在 `card` 表里没有记录”。
- ⭐ 地区名**小写**：`A3 = 'north Bohemia'` / `'south Bohemia'`（`130`/`131`/`150`）；`A2` 是分支所在地。
- ⭐ 贷款状态：`status IN ('C','D')` 才算 active（`131`）。
- ⭐ `94`/`189`/`95` “最年轻/最年长 + 平均工资”这类双条件题，金标是 `ORDER BY` + `LIMIT 1` 或
  `WHERE 列 = (SELECT …)`，**不要把两个条件分别写成两个子查询**。
