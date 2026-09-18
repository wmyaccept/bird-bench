# superhero （10 表） · simple EX 92.6% (75/81)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. **`full_name` 的 NULL 和 `'-'` 都表示「没有全名」**。问"full name"时要留意。
2. **`superpower.power_name` 首字母大写**（`'Cryokinesis'`，写小写=0 行）；
   连接链：`superhero.id=hero_power.hero_id`、`hero_power.power_id=superpower.id`。
3. **取 MIN/MAX 前先查并列**：837「lowest attribute value」`MIN=5` 有 **10 个英雄并列**，
   `ORDER BY ASC LIMIT 1` 只给 1 行 → 要用 `WHERE attribute_value=(SELECT MIN(...))`。

## 连接图与坑

```
superhero ──id── hero_power ──power_id── superpower
          ──*_id── colour / gender / race / publisher / alignment
          ──id── hero_attribute ──attribute_id── attribute（attribute_value）
```
- `superhero.full_name`：**NULL 和字符串 `'-'` 都表示"没有全名"**（122 / 125 行）。
- "superpower" → `superpower.power_name`；"attribute value" → `hero_attribute.attribute_value`。
- ⚠️ **`superpower.power_name` 首字母大写**（`idx 803` 实测：evidence 写 `'cryokinesis'`，
  库里是 `'Cryokinesis'`，小写直接 0 行）。
- ⚠️ **取最小/最大属性值时先查并列**：`idx 837`（“lowest attribute value”）用
  `ORDER BY … ASC LIMIT 1` 得 1 行，金标是 **10 行** —— `MIN(attribute_value)=5` 有 10 个英雄并列。
  ⇒ 按 A2 的备用写法：`WHERE attribute_value = (SELECT MIN(attribute_value) FROM hero_attribute)`。
- 实测全量：**81 道 75 对 / 6 错（92.6%）**。未解的四道都是口径类：
  `720`（“over 15 powers”：金标 71 行 vs 我 102 行，已确认 `hero_power` 无重复行 —— 仍未解释）、
  `741`/`767`/`791`（极值/均值口径）。

## 惯例卡片（实测统计，n=81 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 21 / COUNT(*) 3 / 无 57　⇒ 本库以 `COUNT(列)` 为主（21/24 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：superhero 68 / hero_power 7 / hero_attribute 4 / publisher 1 / superpower 1　⇒ 主表几乎总是 **superhero**（68/81）
- `SELECT DISTINCT`：4/81　|　`*100`：0　|　`BETWEEN`：1
- 输出列数分布：1列×76 / 2列×5
- JOIN 数分布：0:13, 1:50, 2:16, 3:2

> 由 `bird_conventions db=superhero write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
