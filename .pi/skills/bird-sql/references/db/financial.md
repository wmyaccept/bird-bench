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

## 惯例卡片（实测统计，n=62 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(DISTINCT) 23 / COUNT(列) 13 / COUNT(*) 6 / 无 20　⇒ 本库偏去重（23/42 计数题）⇒ 计数先试 `COUNT(DISTINCT 实体id)`
- 主表（FROM 第一张）：client 16 / account 14 / district 9 / disp 7 / loan 7 / trans 6 / card 3　⇒ 主表**不固定**（最大是 client 也只占 16/62）⇒ 按题干主语选，此处是错题重灾区
- `SELECT DISTINCT`：3/62　|　`*100`：15　|　`BETWEEN`：7
- 输出列数分布：1列×19 / 2列×6 / 3列×3 / 4列×7 / 5列×7 / 6列×2 / 7列×7 / 8列×5 / 9列×2 / 13列×2 / 14列×1 / 15列×1
- JOIN 数分布：0:3, 1:9, 2:6, 3:7, 6:1, 7:3, 8:2, 9:8, 10:6, 11:8, 12:1, 13:5, 14:2, 15:1

> 由 `bird_conventions db=financial write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
