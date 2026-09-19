# student_club （8 表） · simple EX 91.1% (92/101)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. **四条主干连接，背下来就不会错**：
   `member.link_to_major=major.major_id`（学院/专业）、`member.zip=zip_code.zip_code`（城市/县/州）、
   `attendance.link_to_member=member.member_id`、`attendance.link_to_event=event.event_id`。
2. **`budget` 的列叫 `event_status`**（不是 `status`）；`zip_code` **没有 `country` 列**（用 `state`）；
   `event` **没有 `url` 列**（用外键 `budget.link_to_event`）。
3. **`SUM(...)` 旁还有非聚合列就必须 `GROUP BY`**（1467 忘了一次 → 1 行 vs 金标 7 行）；
   "highest attendance" 类要查并列（1318：Registration/Yearly Kickoff 都是 30）。

## 连接图与坑

```
member ──member_id──┐ attendance ──link_to_event── event
        └──link_to_major── major
event ──event_id── budget ──budget_id── expense ──link_to_member── member
income ──link_to_member── member
zip_code ──zip── member.zip
```
- `budget` 里既有 `status`（事件状态）也有 `spent` / `amount` / `category`。
  ⚠️ 实测列名是 **`budget.event_status`**（不是 `status`；`status` 只在 `event` 表上）。
- `expense.expense_date` 是 `'YYYY-MM-DD'`；`event.event_date` 是 `'YYYY-MM-DDTHH:MM:SS'`。
- "T-shirt size" = `member.t_shirt_size`；"full name" = `first_name, last_name`（两列）。

**主力连接（首批 13 道 12 对，全靠这四条）**：
```sql
member.link_to_major = major.major_id      -- 学院 / 专业 / department
member.zip           = zip_code.zip_code   -- 城市 / 县 / 州（“grew up in …”）
attendance.link_to_member = member.member_id   -- 某人参加过的活动
event.event_id            = attendance.link_to_event
```
“哪个学院 / 什么专业 / 哪个城市”类题 = `member` + `major` / `zip_code` 两表 JOIN，几乎不会错。

⚠️ **“最高出勤 / 最多 X”类题先查并列**（`dev idx 1318` 实测）：
`Registration` 与 `Yearly Kickoff` **都是 30 人并列第一**，金标取的是后者，
而 `ORDER BY COUNT(*) DESC LIMIT 1` 在我这里返回前者 → 形状对、值不对。
这种并列只能靠运气，**不要在同一题上反复换写法**。

**实测全量：113 道 103 对 / 10 错（91.2%，目前最好的库）**。补充实测坑：
- **`zip_code` 没有 `country` 列**（只有 `zip_code, type, city, county, state, short_state`）——
  `1433` 问“which countries”我写了 `country` 直接报错；该库“国家”概念实际落在 `state` 上。
- **`event` 没有 `url` 列**（只有 `event_id, event_name, event_date, type, notes, location, status`）——
  “links to events”类要回到外键 `budget.link_to_event`（`1436` 实测）。
- ⚠️ **`SUM(...)` 旁边带非聚合列时必须 `GROUP BY`**：`1467`（“total amount spent on
  speaker gifts **and list the event name**”）我写成了全表聚合 → 1 行，金标 **7 行**。
- **“full name” 没 evidence 时可能是 1 列**：`1366`“List all the members”金标 1 列（我给了
  `first_name, last_name` 两列）；而 `1414` 的 evidence 明写“full name refers to first_name, last_name”（两列）。
  ⇒ **evidence 写了就按 evidence，没写就两种都可能。**

⚠️ **`budget` 的列名**（实测 `1450`）：`budget_id, category, spent, remaining, amount, event_status, link_to_event`。
题干说 “budget more than forty” → 用 `budget.amount > 40`（**不是** `spent`，也不是 `planned_amount`）。
`expense.cost` 才是“花了多少钱”（`incurred less than 50USD` → `expense.cost < 50`）。

## 惯例卡片（实测统计，n=158 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 32 / COUNT(DISTINCT) 4 / COUNT(*) 1 / 无 121　⇒ 本库以 `COUNT(列)` 为主（32/37 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：member 63 / event 42 / budget 17 / expense 15 / major 11 / zip_code 5 / income 3 / attendance 2　⇒ 主表以 **member** 为主但**不固定**（63/158）⇒ 按题干主语选
- `SELECT DISTINCT`：15/158　|　`*100`：9　|　`BETWEEN`：5
- 输出列数分布：1列×119 / 2列×27 / 3列×12
- JOIN 数分布：0:32, 1:99, 2:22, 3:4, 5:1

> 由 `bird_conventions db=student_club write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ moderate 全组实测（36 道，29 对 = 80.6%）—— 本库 89.2% 仍是最强库

本批新答：1316/1317/1321/1324/1327/1332/1335/1360/1382/1388/1395/1399/1400/1401/1403/1404/1405/
1421/1426/1427/1428/1430/1431/1432/1435/1439/1440/1441/1449/1452/1453/1454/1455/1456/1458/1469。

### ❌ 实测错（7 道）—— 本库的坑几乎全在**口径**，不在列

1. **「less than average <某类> cost」返回空集 ⇒ 一定是"平均"的算法不同**（1453：金标 **3 行**，我 0 行）。
   我把平均算在 `expense.cost` 上（Parking 3 行的 `SUM/COUNT` = 6.0，于是"小于 6"没人满足）；
   金标能返回**全部 3 行** ⇒ 它的阈值 > 最大单笔 ⇒ 平均的分子分母里至少有一个**不是 expense** ——
   **优先怀疑金标用的是 `budget.amount` / `budget.spent`（钱有两套列：预算 vs 报销）**。
2. **「percentage of the cost for <某类> events」= 该类成本 ÷ 全部成本 ×100**（1454 我按 evidence 的
   `DIVIDE(SUM(cost), COUNT(event_id)) * 100` 算成 6686.3125 ✗；正确的读法是 1069.81/2086.05×100）。
   ⚠️ **本题 evidence 的公式是误导的**：本库 money 题的 `DIVIDE(SUM(cost), COUNT(event_id))` 不能照抄。
3. **「difference in the percentage」要 ×100**（1458：我 4/33-0/33 = 0.1212 ✗；金标要 12.1212）。
   ⇒ 本库**题面说 percentage 就 ×100**，evidence 里没写 *100 也不能省。
4. **「SUM(标志位)/COUNT(member_id)」的分母是 member 全表、不是 JOIN 后的行数**（1421：我 1/32×100 ✗；
   金标 = **1/33×100**）⇒ 别用 JOIN 后的 `COUNT(*)`（JOIN 会掉掉没有 major 的那 1 个成员）。
5. **evidence 说「'X' is the major name」就照字面用 `major_name = 'X'`**（1441：我用
   `LIKE '%Education%' AND college = …` 得 3 ✗；金标照字面 `= 'Education'` ⇒ **0**）。
   ⚠️ 即使这个取值在表里**不存在**（本库 `major_name` 里根本没有 "Education"）也要照字面 —— **答案可以是 0**。
6. **「State his/her full name along with the income source」= 3 列**（1388 金标 1 行 3 列，我的列数对、
   值不对 ⇒ 分组粒度问题：金标很可能是**按 (成员, source) 分组**取最大，而不是按成员 `SUM(amount)`）。
7. **「What are the budget category of the events …」= 2 列**（1427 金标 **4 行 2 列**；我只给 `category` 1 列）。
   ⇒ 本库并列两个名词（"the budget category **of the events**"）时，**事件名要一起给**。

### ✅ 对得稳的（可直接照用）

- **「List the full name …」= 2 列 `first_name, last_name`**（1327 20 行 ✓）；**没写 "full name" 的 "who/which member" ⇒ 2 列**（1382 ✓）；
  而 **「List the last name …」= 1 列**（1431 12 行 ✓、1426 是 last+department+college = 3 列 ✓）。
- **数钱题**：`SUM(budget.spent)`（1332 = 101.94 ✓ / 1335 = 54.25 ✓）、`SUM(expense.cost)`（1401 = 67.81 ✓）、
  `SUM(budget.amount)` 算预算（1405 4 行 ✓）；**百分比 = 部分 ÷ 全部 ×100**（1360 = 3.846 ✓、1400 = 10.0 ✓）。
- **`strftime('%Y', event_date)`**（本库 SQLite **没有 `YEAR()`**）；`event_date BETWEEN '2019-03-15' AND '2020-03-20'`
  这种**字符串区间**够用（1435 3 行 ✓）。
- **「Did …?」是否题 ⇒ `IIF(COUNT(*) > 0, 'YES', 'NO')`**（1399 本轮 ✓，全大写）。
- **`attendance` 计数用 `COUNT(DISTINCT link_to_member)`**（1395 = 17 ✓、1317 = 7 ✓）。
- ⚠️ **`bird_query` 的表格渲染偶尔会把长单元格显示乱**（我把 `100.0` 看成过 `1000`、把
  `32|1|3.125` 看成过 `100`）⇒ **拿不准就换成分列 SELECT 再跑一次**，别在错数字上做判断。

## ⚠️⚠️ challenging 实测（9 道，5 对 = 56%）—— **金标爱给外键 id，不爱给姓名**

- **1437**「Which members who were approved from …? identify the member … and the link to their event」金标：
  `SELECT DISTINCT T1.link_to_member, T3.link_to_event` ⇒ **2 列、全是 id**（46 行）
  —— 我给 472 行 × 3 列（`first_name, last_name, link_to_event`）✗
- **1451**「Among the members who incurred expenses in more than one event, who paid the most amount?」金标：
  `SELECT T2.member_id … GROUP BY member_id HAVING … ORDER BY … LIMIT 1` ⇒ **1 列 = member_id** ✗
  ⇒ 口诀：**本库 "which member/who" 且没有明说 "full name" 时，先按"给 `member_id` / 外键"写**；
  只有题干写 "full name"/"last name" 时才是姓名列。
- 对得稳的：1339（`AVG(cost)` + `substr(expense_date,6,2) IN ('09','10')`）、1359（两会议 Advertisement 金额之比）、
  1429（`event.location = '900 E. Washington St.'` + `position='Vice President'` + `type='Social'`）、
  1448（Pizza 50<c<100 → 4 行 2 列）、1457（3 行 3 列）、1460、1464（`income.date_received`）。
