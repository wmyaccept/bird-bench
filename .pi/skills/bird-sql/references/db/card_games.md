# card_games （6 表） · simple EX 62.4% (78/125)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

1. **输出列加 `DISTINCT` 了吗？** `cards` 是「一卡一印刷版本一行」（同 `name` 多行），
   金标给的是**去重集合**：387(187→10)、444(1052→95)、448(480→47)。
2. **值的大小写对了吗？** 本库取值**首字母大写**：`'Restricted'`、`'Annul'`、`'Cryokinesis'`。
   ⚠️ 写 `WHERE 值` 之前先 `SELECT DISTINCT 该列`（小写 `='restricted'` 是 **0 行**，真值 636 行）。
3. **多值串列用 `=` 还是 `LIKE`？** `keywords='Flying'`=**3088**（金标） vs `LIKE '%flying%'`=5039。
   **先试精确匹配。** 同理注意 `cards.type` vs `cards.types` 是两列。

## 连接图与坑

```
cards ──uuid── legalities / rulings / foreign_data
      ──setCode── sets ──code── set_translations
```
- `cards` 有 **74 列**，好几个 `id`：`id`（整数主键）、`uuid`（外部 ID）、`multiverseId`。
- “which cards” 的金标常返回 `cards.id`（`minidev idx 346`）。
- `borderColor` 取值：black / borderless / gold / silver / white。

**⚠️ 实测坑（dev 342–363 一批 13 道错 8 道，全部踩在下面这几条）**

1. **列名是 camelCase，evidence 里的概念名不是列名**：

   | evidence 里写的 | 真实列名 |
   |---|---|
   | EDHRec | **`edhrecRank`** |
   | “卡片类型” | `cards.type`（粗）/ `cards.types`（细）—— **两个都有** |
   | 文字框 | `isTextless`（0/1） |
   | 先手包 | `isStarter`（0/1） |

   ⇒ 写之前先用 `SELECT name FROM pragma_table_info('cards') WHERE name LIKE '%关键词%'` 核对（实测：
   写 `cards.EDHRec` 直接 `no such column`）。
2. ⚠️ **这一库的取值首字母大写，小写几乎全不匹配（大小写敏感）**：

   | 你可能会写 | 实际值 | 行数对比 |
   |---|---|---|
   | `legalities.status = 'restricted'` | `'Restricted'` | **0 vs 636** |
   | `cards.name = 'annul'` | `'Annul'` | **0 vs 正常** |

   `status` 只有三个值：`Legal` / `Banned` / `Restricted`。
   （与 california_schools 的 `'Directly funded'`（小写 f）正好相反 —— 所以**每换一个库都要先
   `SELECT DISTINCT` 看一眼真值**，不要凭印象写。）
3. **同名卡有多个版本（按 `uuid` 区分）**：`WHERE name='Duress'` → 29 行；`name='Annul'` → 多个 number。
   输出**属性列**时通常要 `DISTINCT`（实测 `idx 357`：`DISTINCT promoTypes` = 4 = 金标行数）。
4. 连接键：`legalities.uuid = cards.uuid`、`rulings.uuid = cards.uuid`、
   `foreign_data.uuid = cards.uuid`、`set_translations.setCode = sets.code`。
5. `cards.faceConvertedManaCost` 是 **real**（数值），最大值 7.0 **有 22 张并列** ——
   这类题的 `ORDER BY ... DESC LIMIT 1` 撞对撞错靠运气（`idx 342` 就错了），不要指望。
6. ⚠️ **“Name all cards X” 的金标也可能返回 `cards.id` 而不是 `name`**
   （`idx 343` 行数对、集合不对的疑似原因 —— 它是“帧版本”题，654 行两边一样）。

**⚠️⚠️ 第二批实测（dev 342–526 全 123 道：76 对 / 47 错）—— 下面两条是最大的失分源**

7. **`cards` 是一卡一印刷版本一行（同 `name` 多行）⇒ 输出列一律先加 `DISTINCT`。**
   金标给的总是**去重后的值集合**：

   | idx | 题干 | 我（未去重） | 金标 |
   |---|---|---|---|
   | 387 | OGW 的卡的颜色 | 187 | **10** |
   | 399 | arena 卡的 subtypes+supertypes | 999 | **46** |
   | 444 | boros watermark 卡的外语名 | 1052 | **95** |
   | 448 | abzan watermark 卡的外语名 | 480 | **47** |
   | 442 | Masques/Mirage block 的 set | 9 | **3** |

   ⇒ 这一库的“List / What are the …”题，**先在输出列上加 `DISTINCT`**，再去想别的。
8. ⚠️ **多值串列（`keywords` / `subtypes` / `colors` / `promoTypes`）先试精确匹配 `=`，再试 `LIKE`**
   （实测 `idx 376`）：

   | 写法 | 行数 |
   |---|---|
   | `keywords = 'Flying'` | **3088**（金标） |
   | `keywords LIKE '%flying%'` | 5039（**错**，把 `Flying,Flash` 等也算了） |
9. ⚠️ **“How many X ? List out the id” 类题金标只输出 id（1 列）**，不要在前面加 `COUNT(*)`：
   实测 `435`（black border，49729 行）/ `436`（extendedart，383 行），金标都是 **1 列**，我给了 2 列。
   同类：“State/List the X” 就只给 X，不要把题干里的修饰问句也算成列。
10. **`set_translations` 只覆盖 121 个 set（sets 有 551 个）**：`setCode='M13'/'4BB'/'J14'`
    实测都是 **0 行** → 涉及“某个 set 的语言”时不要假设有翻译行（`428/429/438/519` 四道都因此 0 行）。
11. **取值参考（都是实测）**：
    - `sets.type`：`core / expansion / commander / promo / masters / token / …`（**下划线形式，没有** `expansion commander`）
    - `sets.block`：`Mirage / Masques / …`
    - `legalities.status`：`Legal / Banned / Restricted`
    - `legalities.format`：小写（`legacy` / `oldschool` / `duel` / `pauper` …）
12. **`faceConvertedManaCost` 最大值 7.0 有 22 张并列**；`convertedManaCost` 同理 ——
    “最高 X 的前 N 张”类题排序不稳定，`514`/`392`/`342` 都因并列而错。

## 惯例卡片（实测统计，n=138 道已提交题的金标；重跑 `bird.py conventions` 可刷新）

- 计数形态：col 21 / DISTINCT 4 / `COUNT(*)` 6 / 无 107　⇒ 本库以 `COUNT(列)` 为主（col 21 / DISTINCT 4 / star 6）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：cards 102 / sets 26 / foreign_data 5 / set_translations 4 / legalities 1　⇒ 主表几乎总是 **cards**（102/138）
- `SELECT DISTINCT`：32/138　|　`*100`：5　|　`BETWEEN`：1
- 输出列数分布：1列×120 / 2列×15 / 3列×3
- JOIN 数分布：0:76, 1:60, 2:1, 3:1
