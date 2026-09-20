# superhero （10 表） · simple EX 92.6% (75/81, 旧 dev 2024-06)

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
- 实测全量（旧 dev 2024-06）：**81 道 75 对 / 6 错（92.6%）**。未解的四道都是口径类：
  `720`（“over 15 powers”：金标 71 行 vs 我 102 行，已确认 `hero_power` 无重复行 —— 仍未解释）、
  `741`/`767`/`791`（极值/均值口径）。

## 惯例卡片（实测统计，n=129 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 37 / COUNT(*) 4 / 无 88　⇒ 本库以 `COUNT(列)` 为主（37/41 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：superhero 115 / hero_power 7 / hero_attribute 5 / publisher 1 / superpower 1　⇒ 主表几乎总是 **superhero**（115/129）
- `SELECT DISTINCT`：7/129　|　`*100`：10　|　`BETWEEN`：3
- 输出列数分布：1列×118 / 2列×8 / 3列×3
- JOIN 数分布：0:13, 1:62, 2:42, 3:12

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

## ⚠️⚠️ challenging 实测（15 道，8 对 = 53%）—— **"给 id 还是给名字"是本库最大的坑**

逐条对照金标 SQL 得到的硬事实（**都是"要不要 JOIN 去翻译"的问题**）：

| 题 | 题干 | 金标给的是 | 我给的 |
|---|---|---|---|
| **772** | "List the eyes, hair and skin colour" | **`eye_colour_id, hair_colour_id, skin_colour_id`（数字 id！）** | JOIN `colour` 翻译成 'Blue' 等 ✗ |
| **744 / 829** | "which publisher has published more? Find the difference" | **只有 1 列 = 差值本身**（744 = Marvel−DC，829 = DC−Marvel） | 我给 2 列 (名称, 差值) ✗ |
| **1437 式** | （见 student_club）"which members …" | 给 **`link_to_member`** 外键，不给姓名 | 姓名 ✗ |

- **分母必须用"没被 INNER JOIN 缩小"的行数**：
  - **743** 金标 `COUNT(*) * 100 / (SELECT COUNT(*) FROM superhero)`（分母 = 全表 1518，不是 JOIN 后的行数）✗
  - **835** 金标 **`LEFT JOIN alignment`**（`Good` 的占比要把 alignment 为 NULL 的也算进分母）✗
  - **788** 金标 `COUNT(CASE WHEN publisher='Marvel Comics' THEN 1 END) * 100 / COUNT(T1.id)` 且 **WHERE gender='Female'**
    ⇒ 分母 = **女性英雄数**，分子 = 其中 Marvel 的（不是我写的"Marvel 里女性占比"——**两个方向别搞反**）✗
- 对得稳的：724（蓝眼金发名单）、730、760（150–180cm 里 Marvel 占比）、769（Dark Horse 最耐久，配 `ORDER BY value DESC, id LIMIT 1`）、
  773（同色）、775、818、819、834。
## ⚠️⚠️ 值层实测（D 类 7 道）

- ⭐ `812` “full names of superheroes” 金标给 **`superhero_name`**（本表还有一列 `full_name`，别选错）。
- ⭐ `772` “eyes / hair / skin colour” 金标给 **`eye_colour_id` / `hair_colour_id` / `skin_colour_id`（id）**，
  不是 JOIN `colour` 翻译出来的 'Blue'。
- ⭐ 百分比的分母是**全体**（`788`：金标 `COUNT(superhero.id)` 全表、只有分子限 Marvel）
  —— 优先“没被 `WHERE` 收窄的那一侧”。
- ⭐ `741` “most powers” 金标 `GROUP BY superhero_name` + `ORDER BY COUNT(T2.hero_id)`
  （`GROUP BY` 的列和 `COUNT` 的列都要对）。
