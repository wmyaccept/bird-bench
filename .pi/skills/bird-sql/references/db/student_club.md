# student_club （8 表） · simple EX 91.1% (92/101)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

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
