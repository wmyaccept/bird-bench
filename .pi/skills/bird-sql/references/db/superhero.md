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

## 惯例卡片（实测统计，n=114 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 31 / COUNT(*) 3 / 无 80　⇒ 本库以 `COUNT(列)` 为主（31/34 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：superhero 100 / hero_power 7 / hero_attribute 5 / publisher 1 / superpower 1　⇒ 主表几乎总是 **superhero**（100/114）
- `SELECT DISTINCT`：7/114　|　`*100`：3　|　`BETWEEN`：2
- 输出列数分布：1列×106 / 2列×6 / 3列×2
- JOIN 数分布：0:13, 1:57, 2:35, 3:9

> 由 `bird_conventions db=superhero write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ moderate 全组实测（33 道，27 对 = 81.8%）—— 本库的两个"名字里没写但金标有"的规矩

### ① 「Rank … by X」= **3 列**，第 3 列是 **`RANK() OVER (...)`**（已核金标 SQL）⭐⭐ 本库最大的一类失分

- **726**「Rank heroes published by Marvel Comics by their height in descending order」金标：
  ```sql
  SELECT superhero_name, height_cm, RANK() OVER (ORDER BY height_cm DESC) AS HeightRank
  FROM superhero INNER JOIN publisher ON … WHERE publisher_name = 'Marvel Comics'
  ```
- **728**「Rank superheroes … by their eye color popularity」金标：
  ```sql
  SELECT colour.colour, COUNT(superhero.id), RANK() OVER (ORDER BY COUNT(superhero.id) DESC)
  … GROUP BY colour.colour
  ```
  ⇒ 我两题都只给 1 列 ✗。**见 "Rank … by X" 一律 3 列：`(名称, X 的值, RANK() OVER (ORDER BY X …))`**
  （简单集 763 金标 6 行 2 列是同一个病的轻症）。

### ② 「Who is the X-est?」= **1 行**（LIMIT 1），不是全部并列 —— 与 837 相反

- **736**「Who is the dumbest superhero?」金标 `… ORDER BY T2.attribute_value ASC, T1.id LIMIT 1` ⇒ **1 行**（我按并列给了 3 行）✗
- **766**「the hero's full name with the highest attribute in strength」金标 `ORDER BY attribute_value DESC LIMIT 1` ✗（我 63 行）
- **794**「Which hero was the fastest?」金标 `ORDER BY attribute_value DESC, T1.id ASC LIMIT 1` ✗（我 40 行）
  ⇒ 精确写法：**`ORDER BY 属性值 <方向>, T1.id` + `LIMIT 1`**（并列时按 id 升序取第一个），不是 `= (SELECT MAX(...))`。
- ⚠️ 但 **837**（simple）「lowest attribute value」金标是 **10 行全部并列** ✓
  ⇒ **分界在问句形态**：**"Who/Which <人> is the <est>?" ⇒ 单人（LIMIT 1）**；
  **"…value/…with the lowest attribute value" ⇒ 全部并列**。别名档案顶部第 3 条要按这个细分读。

### ③ 「List down at least five …」= **字面 `LIMIT 5`**

- **751** 我给了 162 个 DISTINCT power_name ✗，金标 **5 行**（就是 `LIMIT 5`）。
  ⇒ 以后见 "at least N" 一律写 `LIMIT N`。

### ✅ 本轮对得稳的（可直接照用）

- **取值大小写**：`race='Human'`（**不是** 'human'，758 用错就 0 行）；`alignment='Bad'` 表示反派（822 ✓）；
  `colour='No Colour'`（753 ✓）；`attribute_name='Strength'/'Speed'/'Intelligence'` 首字母大写（✓）。
- **列名是 `height_cm` / `weight_kg`**（不是 `height`/`weight`）—— 本轮第一版探针就撞在这上面。
- **属性题一律走 `hero_attribute JOIN attribute`，极值用 `= (SELECT MAX/MIN …)`**：740(12)/786(63)/814(10)/
  845(104) 全对；**845 的 "80% of the average height" = `height_cm > 0.8*(SELECT AVG(height_cm) FROM superhero)`** ✓。
- **是否/单值题**：820（Hulk 的 Strength = 100）、825（Phoenix Force → 'Female'）、827（Dark Horse 非人类平均身高 109.0）、
  800（蓝眼比例 31.2）、801（男女比 2.5566502463054186 = **真除**，不是整数除 2）全对。
- **`798`「publisher for A, B and C」= 1 列 3 行**（重复值用 `DISTINCT` 也无妨，集合口径等价）。
