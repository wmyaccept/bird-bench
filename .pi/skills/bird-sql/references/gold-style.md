# 金标为什么这么怪（实测总结）

<!-- push step=1 -->
## ⚡ 决策速查（读题时就要预判形状）
- 金标的**结果集不会是 NULL/空集** ⇒ 两个写法形状一致、一个给空集一个给真值 ⇒ **选给真值的那个**。
- 题干里的抽象名词（category / type / kind / name / status / position）**优先用同名列**。
- "最多/最高"并列时金标常常返回**全部并列项**，不是 `LIMIT 1`。
- `ORDER BY col ASC LIMIT 1` 会把 **NULL 排第一** ⇒ 取最小/最早前先 `WHERE col IS NOT NULL`。
- **多出来的一列优先猜主键 id**；题干出现 "Rank … by …" ⇒ 金标可能真有一个 `RANK()` 输出列。
- 「for all the X who …, give their Y」⇒ **行级输出**：不去重、不带 id。
<!-- /push -->

BIRD 的金标是人工写的，不是"标准答案生成器"，它会做很多你认为不该做的事。
**遇到怪结果先怀疑金标风格，而不是怀疑自己 SQL 写错了。**

## 一、7 个反直觉行为

0. **金标的结果集不会是 NULL** —— 这条可以拿来做二选一。
   BIRD 论文 §3.4 的 Examination 环节明确写：每条 gold SQL 都要能返回有效结果，
   *"If the executed result set is 'NULL', experts will make slight changes to the conditions
   of the questions until the associated SQLs can provide a valid result set"*。

   ⇒ 两个候选写法**形状一致、但一个给 NULL（或空集）、另一个给真值**时，**选给真值的那个**。
   实测 `idx 22`：naive JOIN → 空集；单表查 `sname` → NULL；加 `sname IS NOT NULL` → 真学校名
   —— 金标就是最后那个。

1. **同名列优先。** 题干里的抽象名词（category / type / kind / name / status / position）
   如果在某个表里**真有一列叫这个名字**，金标大概率用那一列，哪怕语义上另一个列更贴切。
   → 先 `SELECT DISTINCT` 把候选列都看一眼再决定。（实测 `idx 70`）

2. **"最多/最高/最快"并列时，金标常常返回全部并列项，而不是 `LIMIT 1`。**
   实测 `idx 152`：问 "the league had the most matches in 2008/2009"，4 个联赛并列 380 场，
   金标返回 **4 行**。但也实测过相反的例子（`idx 57`："最低成本的事件"三方并列，金标只返回 **1 行**）。
   → 两种都可能。**先算出并列项有几个**：
   - 并列项少且题目问单个实体 → 先试 `ORDER BY ... LIMIT 1`
   - "按某个聚合值取极值"的题 → 先试 `HAVING 聚合 = (SELECT MAX(聚合) ...)`（返回全部并列）
   - 同一题只选一种：并列个数由 `run` 给出，不要等 `bird_score`。

3. **SQLite 里 `NULL` 比任何值都小，`ORDER BY col ASC LIMIT 1` 会把 NULL 行排第一位。**
   实测 `idx 180`：问"第 19 站第二节排位赛最好圈速的车手姓氏"，真正最快的是 Räikkönen，
   但金标答案是 **Fisichella** —— 因为金标写的是 `ORDER BY q2 LIMIT 1`，而 Fisichella 的 q2
   是 `NULL`，NULL 排最前。

   **默认排除 NULL 行**（`WHERE col IS NOT NULL` 或 `col = (SELECT MIN(col) ...)`，MIN 忽略 NULL）。反例 `idx 211`："最老的车手来自哪个国家"，
   全库有 1 个车手 `dob` 是 NULL（Ray Reed）：

   ```sql
   -- ❌ 返回 NULL 行的国籍 → 'South African'（金标不认）
   SELECT nationality FROM drivers ORDER BY dob ASC LIMIT 1
   -- ☑️ 金标用的是 MIN()，MIN 忽略 NULL → 'French'
   SELECT nationality FROM drivers WHERE dob = (SELECT MIN(dob) FROM drivers)
   ```

   → 做"最好/最早/最小"类题时：**先查这一列有没有 NULL**
   （`SELECT COUNT(*) FROM t WHERE col IS NULL`）。有 NULL 就在 SQL 里加
   `WHERE col IS NOT NULL`（默认排除 NULL 行）；不要等 score 再改。

4. **金标可能"忘了"实施题干里的某个限定条件。** 见 `idx 205`。题干里的限定词越绕
   （"when he was in track number less than 20"），金标越可能根本没写进 SQL。

   **第二种情形：限定词靠语义推断、没有对应列时，金标几乎肯定不用它。**

   ✅ `idx 56` "Which student has been **entrusted to manage the budget** for the Yearly Kickoff?"
   —— 我理解成“管事的人”于是加了 `member.position = 'Treasurer'`（2 行），
   **金标 4 行**：它只把该活动所有产生过支出的成员列了出来，那个限定词根本没写进 SQL。
   （`idx 33` 的 "not fundraisers" 同理，金标也是直接省了。）

   → 限定词找不到对应列时，默认**不写进 SQL**（用 `run` 看候选行数是否离谱）；不要等 score 再改。

5. **`question_id` 和下标完全无关。** 500 题里没有一个 `question_id` 等于它的下标。
   所有工具都用 `idx`，这是唯一可靠的定位方式。

6. **判定层**：加不加 `DISTINCT` 不影响 EX（见 `scoring.md`）。**生成层**：输出集合要不要去重看 `db/<库>.md`，别用判定层当借口漏写。
   反过来，少了任何一个不同的值就算错。（详见 `scoring.md`）

7. **「for all the X who …, give their Y」⇒ 行级输出，不要去重、不要带 id。**

   ✅ `idx 29` "For all the people who paid more than 29.00 per unit of product id No.5.
   Give their **consumption status** in the August of 2012."

   ```sql
   -- ❌ 我写的：带上了 CustomerID，并且 DISTINCT 去重 → 9 行 2 列
   SELECT DISTINCT yearmonth.CustomerID, yearmonth.Consumption FROM ...
   -- ☑️ 金标：只输出 Consumption，**不去重** → 10 行 1 列
   SELECT yearmonth.Consumption FROM transactions_1k
   JOIN yearmonth ON transactions_1k.CustomerID = yearmonth.CustomerID
   WHERE ... AND yearmonth.Date = '201208'
   ```

   差在两点：① 多选了 `CustomerID`；② `DISTINCT` 把一个人两笔交易合并成一行（10 → 9）。

   > `DISTINCT` 本身不影响 EX，但**行数不一致时**就会暴露——金标 10 行而我 9 行。
   > “give their Y”就只给 Y，别顺手带上 X 的标识列。

## 二、3 条"机械写法"（不靠数据就能预判结果）

> **收录标准**：只收「能写出更接近金标的 SQL」的写法。
> 如果一条规则只是让你去复现一个写错了的 bug（比如 `idx 222` 把 `HAVING COUNT(x)=2` 和
> `SELECT COUNT(x)` 写成同一个表达式，输出恒为 2），那就**不收**——它不迁移，
> 只会把错误也学进去。那类只记进 `casebook.md` 当缺陷样本。

### ① 多出来的那一列，优先猜「主键 id」

两个独立例子：

- `idx 346`（card_games）：问 "which cards have powerful foils"，金标返回 **`cards.id`**，不是 `name`。
- `idx 174`（european_football_2）：问"最重球员的 finishing 和 curve"（题面只提到 2 个概念），
  金标却是 **3 列**，多出来的那一列是**属性行的主键**，不是球员名、也不是 weight：

  ```sql
  SELECT id, finishing, curve FROM Player_Attributes
  WHERE player_api_id = (SELECT player_api_id FROM Player ORDER BY weight DESC LIMIT 1)
  LIMIT 1
  ```

  这题顺带展示了两个常用写法：

  - **"最 X 的那一个"用子查询 `(SELECT ... ORDER BY ... LIMIT 1)` 定位**，
    而不是拿 `MAX(...)` 去 JOIN —— 在 `weight = 243` 这类**并列**情况下，
    子查询只返回一行，直接就把并列取掉了。
  - 外层再加 `LIMIT 1`，因为同一球员在属性表里有多条历史记录。

> 启发：`european_football_2` / `card_games` 这类库有好几套 ID
> （`id` / `player_api_id` / `uuid` / `CDSCode`），金标习惯把某一行的主键一起选出来。
> **列数比题面概念多 1 时，先试"再加一列 id"**，别死盯着名字和数值。

### ② 题面出现 "Rank … by …" ⇒ 金标可能真有一个 `RANK()` 输出列

✅ `idx 441` "Rank schools by their average score in Writing … showing their charter numbers"

```sql
SELECT CharterNum, AvgScrWrite, RANK() OVER (ORDER BY AvgScrWrite DESC) AS WritingScoreRank
FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds
WHERE T2.AvgScrWrite > 499 AND CharterNum is not null
```

两个反直觉点：

- **`RANK()` 是第 3 列的输出，不只是 `ORDER BY`**；
- **输出里根本没有学校名字**（虽然 "Rank schools" 听起来该带名字）。
  我当时在 `sname` / `School` 上纠结了三次，而它们压根不在 `SELECT` 里。

> 启发：列数比题面概念多时，除了主键 id，**还可能是窗口函数算出来的名次/序号列**。

### ③ `COUNT(DISTINCT 实体)` 外加 JOIN ⇒ 那个 JOIN 是「隐式过滤」，不是取值

✅ `idx 116` "How many patients with an Ig G higher than normal?"（答案 9，我算 136）

```sql
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1
INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID
INNER JOIN Examination  AS T3 ON T3.ID = T2.ID   -- 多余的这一张
WHERE T2.IGG >= 2000
```

第三次 JOIN 只用了 `T3.ID = T2.ID`（不取值），作用是：**该患者必须也在 Examination 里有记录**。
同时有化验和就诊记录的患者很少 ⇒ 136 掉到 **9**。

**我当时想反了**：以为多一张表会把行数乘大，但 `COUNT(DISTINCT)` 会折叠扇出，
多余 JOIN 的实际效果是**把实体集缩成交集**。

> 最强的一条线索：**evidence 里写 "Should consider DISTINCT in the final result"**。
> `COUNT` 本来就不可能返回重复行，为什么还要提醒去重？因为它真正想说的是：
> **金标里有一个会产生重复行的 JOIN**。看到这句话就去数"库里哪张表还能再 JOIN 进来"。
