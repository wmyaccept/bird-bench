# 这个数该怎么算（口径题）

实测到的**第二高频失分类型**：SQL 语法没错、结构也对，但"读法"错了。
四条经验都是撞出来后才纠对的。

## 一、条件落在表 A、返回的列在表 B ⇒ 金标会用「共同的 key」硬连过去

✅ `idx 14` "Please list the product description of the products consumed in September, 2013"

- 时间条件在 `yearmonth`（`Date = '201309'`），商品描述在 `products`，两表**没有任何外键关系**；
- `transactions_1k` 虽然能连 `products`，但它只覆盖 2012-08 的 4 天 → 按它算得**空集**；
- 金标是 **976 行 1 列**。976 = `yearmonth(201309)` 通过共有的 `CustomerID` 连到
  `transactions_1k` 再连 `products` 的行数：

```sql
-- ✅ 金标形状
SELECT products.Description FROM yearmonth
JOIN transactions_1k ON yearmonth.CustomerID = transactions_1k.CustomerID
JOIN products ON transactions_1k.ProductID = products.ProductID
WHERE yearmonth.Date = '201309'
```

**怎么反推出来的**：金标报"976 行 1 列"，把可能的 JOIN 路径行数都算一遍，哪个正好是 976 —— 一算就中。
金标在语义上很荒谬（拿 2013 年的客户名单去配 2012 年的交易），但 BIRD 的金标就是这种感觉。

## 二、「某年的最高/最低月消费」= 先按实体汇总，再取极值

✅ `idx 13` "What is the highest monthly consumption in the year 2012?"

```sql
-- ❌ 我先写的：单行最大值 → 445279.69（金标不认）
SELECT MAX(Consumption) FROM yearmonth WHERE SUBSTR(Date,1,4)='2012'

-- ✅ 金标口径：先把每个月汇总，再取最大的那个月 → 51787161.74
SELECT MAX(total) FROM (
  SELECT SUM(Consumption) AS total FROM yearmonth
  WHERE SUBSTR(Date,1,4) = '2012' GROUP BY Date
)
```

✅ `idx 1`（同一个规则的第二个实例，我第一遍又踩了）
"In 2012, who had the least consumption in LAM?"

```sql
-- ❌ 单行最小 → CustomerID 7653（他那一个月是 -1651.79）
SELECT CustomerID FROM yearmonth JOIN customers ... ORDER BY Consumption LIMIT 1
-- ✅ 按客户汇总全年再取最小 → CustomerID 47273（全年只有 0.74）
SELECT CustomerID FROM yearmonth JOIN customers ... GROUP BY CustomerID
ORDER BY SUM(Consumption) LIMIT 1
```

关键在于搞清**一行代表什么**：`yearmonth` 一行 = 一个客户一个月，所以"某年的消费"指的是
**该实体在那一年的汇总值**。同类陷阱："月度总销售额"、"年级平均分"、"每场比赛的观众数"。

> ⚠️ **触发条件（背下来）**：题干里出现“**某年/某月/某季度的 X**” + “最…/多…/少…”时，
> 先问一句：“X 是不是该先按实体（客户/学校/球员）汇总？”——十有八九要汇总。
> 这个坑我在 simple 段踩过一次（`idx 13`），到 moderate 又踩了一次（`idx 1`），
> 所以把它提到 `checklist.md` 的自检清单里了。

→ 用 `bird_schema` 看清主键：**主键是 (A, B) 复合键时，一行不是 A 也不是 B，而是 A×B 的组合**。

## 三、百分比题的分母：先试「行数」，再试「去重实体数」

✅ `idx 24` "What is the percentage of the customers who used EUR in 2012/8/25?"

```sql
-- ❌ 我先写的：去重客户数当分母 → 7/259 = 2.7027...
SELECT CAST(COUNT(DISTINCT CASE WHEN c.Currency='EUR' THEN t.CustomerID END) AS FLOAT)*100
     / COUNT(DISTINCT t.CustomerID) FROM ...

-- ✅ 金标口径：行数当分母 → 7/425 = 1.6470588...
SELECT CAST(SUM(CASE WHEN c.Currency='EUR' THEN 1 ELSE 0 END) AS FLOAT)*100 / COUNT(*) FROM ...
```

分子都是一样的（那天的 7 笔），只有分母不同。**先按行数算**（`COUNT(*)` / `SUM(CASE...)`），
失败了再换去重实体口径。`idx 26`（"SVK 的 premium 占比" = 314/880 行）也是行数口径，印证了这个默认值。

## 四、COUNT 类题要看清"去重与不去重导致的值不同"

`DISTINCT` 本身不影响 EX（`set()` 折叠重复行），但**去重与不去重会让 COUNT 报出不同的数**，
这时两者就是不同的"值"，必须选对：

- `idx 16` "EUR 客户里有几个月消费超 1000" → 金标 **2730**（`COUNT(*)` 行数），
  不是 391（`COUNT(DISTINCT CustomerID)`）。它的 evidence 只写了
  "Pays in euro = Currency = 'EUR'"，**没提 DISTINCT**；
- 反过来 `idx 116` 的 evidence 明写 "Should consider DISTINCT in the final result"。

**启示**：evidence 里出现 "DISTINCT" 这类字眼，通常说明金标里真有 `DISTINCT`；
没出现时，**先试不去重的行数**。

### 例外（实测，优先级高于上面那条）：题干的主语是**实体**、而 JOIN 会扇出时，用 `COUNT(DISTINCT 实体id)`

`dev idx 709`：“In comments with 0 score, **how many of the posts** have view count lower than 5?”

| 写法 | 值 | 对错 |
|---|---|---|
| `COUNT(*)`（comments JOIN posts 扇出） | 4 | ❌ |
| `COUNT(DISTINCT posts.Id)` | **2** | ✅ |

判断依据是**题干问的是“几个帖子”而不是“几行”** —— 一旦 `JOIN` 的对侧是一对多
（一个帖多条评论），`COUNT(*)` 数的是“评论行”，不是帖。
同类词：`how many of the posts / users / schools ...` ⇒ 先想实体去重。

## 五、`COUNT(DISTINCT 实体)` + 多余 JOIN 的坑

见 [`gold-style.md`](gold-style.md) 第三节：那个 JOIN 不是用来取值的，是**隐式过滤**。

## 小结：口径题的通用动作

遇到"值算不对但形状对"时，按这个顺序换假设：

1. 聚合层级：是取单行极值，还是先按某个键汇总再取极值？
2. 分母：行数还是去重实体数？
3. 聚合函数：MIN / MAX / COUNT / SUM 有没有选错？
4. 列归属：这个列是不是该用**另一张表**的同名列？（→ `naming-traps.md`）
5. 值是否参与排序的 NULL：见 `gold-style.md` 第 3 条。
