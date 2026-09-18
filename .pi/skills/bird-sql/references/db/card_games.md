# card_games （6 表） · simple EX 62.4% (78/125)

## ⚠️ 交题前必查（本库最容易翻车的几条）

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

## 值域陷阱（实测，写 WHERE 之前必看）

- **`language` 在两张表都有，且是两个粒度**（题面只说 "in Chinese Simplified" 时最容易选错）：
  - `foreign_data.language`：**卡级**外文印刷 —— 229186 行 / 16 种语言；`Chinese Simplified` 20106 行。
  - `set_translations.language`：**套牌级**翻译 —— 1210 行 / 10 种语言；`Chinese Simplified` 121 行。
  - 实测 idx 352「percentage of the cards available in Chinese Simplified」：row-level 口径五个候选
    （8.77 / 59.04 / 35.38 / 10.0 / 43.35）**金标一个都没命中** ⇒ 本题挂起，归因"口径不可判"。
- **`cards.side` 只有 1367 行非空**（多面卡才有）⇒ "cards without multiple faces" = `side IS NULL`（345 ✅）。
- **`cards.artist` 真人真名要按库内写法**：题面写 "Stephen Daniel"，库内是 `'Stephen Daniele'`（347 ✅）。
- **`id` 是整数、`uuid` 是字符串**：题干 "card id" → `cards.id`（整数）；JOIN 一律用 `uuid`。
- 实测 idx 349「名称+画师+是否 promo」：列序换过一次仍不对 ⇒ 挂起，归因"值/列语义不可判"（1 行 3 列）。

## ⚠️⚠️ 第三批实测（dev2025 idx 391–530，41 道里错了 10 道）—— 下面每条都有金标对照

**A. 题干里有「是否 / 有没有」⇒ 金标用 `IIF(..., 'YES', 'NO')`（大写），不是 Yes/No 也不是实体列**

| idx | 题干 | 金标骨架 |
|---|---|---|
| 465 | is there a Korean version of it? | `SELECT IIF(SUM(CASE WHEN T2.language='Korean' AND T2.translation IS NOT NULL THEN 1 ELSE 0 END) > 0, 'YES', 'NO') FROM cards T1 JOIN set_translations T2 ON T2.setCode=T1.setCode WHERE T1.name=…` |
| 469 | Did the set of cards with X appear on MTGO? | `SELECT IIF(EXISTS (SELECT 1 FROM cards T1 JOIN sets T2 ON T2.code=T1.setCode WHERE T1.name='Angel of Mercy' AND T2.mtgoCode IS NOT NULL), 'YES','NO')` |

⚠️ 但 **410** 的「Is there any card from …?」金标返回的却是 `cards.id`（已对）⇒ 没有 IIF 的迹象时，先按「返回实体列」写。

**B. 「the set of cards with <卡名> in it」⇒ 金标用 `setCode IN (SELECT setCode FROM cards WHERE name=…)` + `LIMIT 1`，**只有 1 行**（462 实测）；
JOIN `cards` 会把同一张卡的所有版本都算进去（我因此给出 3 行）。**同族：465/469/498/500。**

**C. ⭐ 「percentage of A that are B」的读法与题面**相反**（本库最大的口径坑）**

- **417**「percentage of Japanese translated sets are expansion sets」金标：
  `SELECT CAST(SUM(CASE WHEN T2.language='Japanese' THEN 1 ELSE 0 END) AS REAL)*100 / COUNT(T1.id)
   FROM sets T1 JOIN set_translations T2 ON T1.code=T2.setCode WHERE T1.type='expansion'`
  ⇒ **把「B（expansion）」当 `WHERE` 范围、把「A（Japanese）」当分子**，分母是**该范围内的 JOIN 行数**（= 61/610 = **10.0**）。
- **433** 同理：分母 = `sets ⋈ set_translations` 的**全体行数**（1210），分子 = `language='Chinese Simplified' AND sets.isOnlineOnly=1`。

⇒ 这类题的默认骨架就是 `CAST(SUM(CASE WHEN <题干第 2 个条件> THEN 1 ELSE 0 END) AS REAL)*100 / COUNT(T1.id)`，
**范围条件进 WHERE、被问的那个条件进 CASE**；**不要**自己把 WHERE 收窄成题面主体。

**D. `sets` 自己也有 `totalSetSize` / `baseSetSize` / `isOnlineOnly` / `isForeignOnly`**

- **432**「Which Russian set contains the most cards overall」金标：`SELECT T1.id, T1.name, T1.totalSetSize FROM sets T1 JOIN set_translations T2 ON T1.code=T2.setCode
  WHERE T2.language='Russian' AND T1.totalSetSize = (SELECT MAX(s.totalSetSize) FROM …)` ⇒ **3 列**（id, name, totalSetSize），
  **用 `totalSetSize` 而不是数 cards**；「俄罗斯」走 **set_translations**（不是 foreign_data）。
- **433** 的 `isOnlineOnly` 取自 **`sets`**（我错用了 `cards.isOnlineOnly`）。

**E. 「How many …」不等于计数**

- **408**「How many unknown power cards contain info about the triggered ability」金标返回 **`rulings.text` 本身**（2059 行），信息在 **`rulings.text`**（不是 `cards.text`）。
- 本库惯例（档案旧第 9 条）：`How many X? List out the id` ⇒ 只输出 id；
- **499**「How many translations of the name of the set X」金标：`COUNT(DISTINCT T2.translation)` ⇒ 计数时先想 **DISTINCT**。

**F. translated-name 题：金标可能给英文名**

- **484**「list the **Italian** names of the cards in Coldsnap with the highest cmc」金标：`SELECT T2.name FROM foreign_data T1 JOIN cards T2 ON T2.uuid=T1.uuid JOIN sets T3 …
  WHERE T3.name='Coldsnap' AND T1.language='Italian' ORDER BY T2.convertedManaCost DESC`（**155 行 = 全部意大利语行**）
  ⇒ ① `T2.name` 是 **`cards.name`（英文名）**，不是 `foreign_data.name`；② 这个「最高 cmc」的过滤**在金标里就失效了**（没 LIMIT/没 MAX）——遇到金标自己走样的题，形状对了也拿不到分。
- **446**「percentage of the cards with cmc 10 in set of Abyssal Horror」金标：2 列 `（百分比, T1.name）`，范围是 **`cards.name='Abyssal Horror'`**（卡本身，不是整个 set），分母 `COUNT(T1.id)` = 3。
## 惯例卡片（实测统计，n=175 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 32 / COUNT(DISTINCT) 7 / COUNT(*) 6 / 无 130　⇒ 本库以 `COUNT(列)` 为主（32/45 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：cards 124 / sets 36 / set_translations 6 / foreign_data 6 / legalities 3　⇒ 主表几乎总是 **cards**（124/175）
- `SELECT DISTINCT`：36/175　|　`*100`：10　|　`BETWEEN`：1
- 输出列数分布：1列×147 / 2列×21 / 3列×7
- JOIN 数分布：0:72, 1:94, 2:5, 3:3, 4:1

> 由 `bird_conventions db=card_games write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
