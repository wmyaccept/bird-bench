# financial （8 表） · simple EX 83.9% (52/62)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

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
  ⇒ **动手前先跑一句 `SELECT date FROM trans LIMIT 1` 确认，不要照抄旧笔记。**
- ⚠️ **“list all the transactions …” 金标只给 1 列**（`idx 165`：我 `SELECT *` 给了 10 列 15140 行，金标是 **1 列** 15140 行）。
- ⚠️ **“how many X **and** Y” 可能是 1 行 2 列**（`idx 172`：owner/disponent 数，金标用
  `SUM(type='OWNER'), SUM(type='DISPONENT')` 一行出两个数；我 `GROUP BY type` 给了 2 行）。
- 实测全量：**62 道 52 对 / 10 错（83.9%）**。
