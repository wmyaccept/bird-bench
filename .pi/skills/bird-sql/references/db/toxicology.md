# toxicology （4 表） · simple EX 82.9% (63/76, 旧 dev 2024-06)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. ⚠️ **`connected` 是双向存储**：每个 bond 存两行（`A→B` 与 `B→A`）。
   全库 10882 行 = 5441 个连接（**正好一倍**）。`WHERE bond_id=X` 会返回 **2 行**。
2. **金标偏「多给列」**：题干列了多个实体（"for TR000, TR001 and TR002"）时，金标会把
   实体 id 也输出一列；问一个 bond 的两端原子时金标是 **2 行 1 列**，不是 1 行 2 列。
3. `atom_id` 形如 `'TR001_1'`；`label` 是 `'+'`(致癌)/`'-'`；`bond_type` 是 `'-'`/`'='`/`'#'`；
   `element` 是小写（`'cl'`/`'c'`/`'na'`）。

## 连接图与坑

```
molecule ──molecule_id── atom / bond / connected
```
- `atom.atom_id` 是 TEXT，形如 `'TR001_1'`（分子_序号）。
- `bond.bond_type`：`'-'` 单键 / `'='` 双键 / `'#'` 三键。
- `molecule.label`：`'+'` 致癌 / `'-'` 不致癌。
- 问“atom 19”这类，金标可能按 `atom_id LIKE '%_19'` 处理（`minidev idx 420`）。

**⚠️ 首批 13 道（11 对）实测到的关键坑：**
- ⚠️⚠️ **`connected` 表是双向存储的：每个 bond 存两行（`A→B` 和 `B→A`）**
  - `WHERE bond_id='TR001_2_6'` 实测返回 **2 行**（`TR001_2|TR001_6` 与 `TR001_6|TR001_2`）
  - 全库连接行数 = **10882**，而实际无向连接只有 **5441**（正好一半）
  - `idx 221`（“TR001 里 bond_id=TR001_2_6 的原子”）金标 **1 行**，我给了 2 行
  ⇒ 凡是数“连接/键”的题，**行数先除以 2 看看合不合理**；输出原子对时先想“金标是不是只要一侧”。
- **`idx 211` 实测**（“非致癌分子里连接的原子”）：金标是
  `SELECT DISTINCT connected.atom_id` —— **1 列、5399 行**（我给了 `atom_id, atom_id2` 两列 10882 行）。
  ⇒ 卡方（1 列 vs 2 列）在这里是常见失分点，“connected atoms”不一定给两个 atom_id。

**⚠️ 全量实测（旧 dev 2024-06，76 道 → 63 对 / 13 错，82.9%）：13 道错题里 7 道是“列数”错**

这个库的列数倾向跟别的库相反 —— **金标爱多给列**：

| idx | 题干 | 我给的 | 金标 |
|---|---|---|---|
| 264 | “What are the labels for TR000, TR001 and TR002?” | 1 列（label） | **2 列**（molecule_id + label） |
| 252 | “What are the atoms that can bond with … lead?” | 1 列（atom_id2） | **2 列** |
| 223 | “What are the atom IDs of the bond TR000_2_5?” | 1 行 2 列 | **2 行 1 列** |
| 309 | TR346 的 atom id + 可建 bond 类型数 | 8 行 2 列 | 5 行 **3 列** |

⇒ **两条经验**：
1. 题干里列了好几个具体实体（“for TR000, TR001 and TR002”、“atom X and atom Y”）时，
   金标通常把**实体 id 也输出一列**（跟 `naming-traps.md`“list 不一定返回名字”同源）。
2. 问“一个 bond 的两端原子”时，金标可能是 **2 行 × 1 列**（顺着 `connected` 的行结构），
   而不是 1 行 × 2 列 —— **不要自作主张加 `LIMIT 1`**（`223` 就是因此错的）。

---

## 惯例卡片（实测统计，n=145 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(列) 35 / COUNT(DISTINCT) 34 / COUNT(*) 3 / 无 73　⇒ 本库以 `COUNT(列)` 为主（35/72 计数题）⇒ 计数写 `COUNT(主表.主键列)`
- 主表（FROM 第一张）：atom 72 / bond 39 / molecule 25 / connected 9　⇒ 主表以 **atom** 为主但**不固定**（72/145）⇒ 按题干主语选
- `SELECT DISTINCT`：39/145　|　`*100`：17　|　`BETWEEN`：6
- 输出列数分布：1列×110 / 2列×23 / 3列×8 / 4列×2 / 7列×1 / 11列×1
- JOIN 数分布：0:36, 1:77, 2:17, 3:2, 5:1, 6:1, 7:1, 8:5, 9:4, 15:1

> 由 `bird_conventions db=toxicology write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
## ⚠️⚠️ moderate 全组实测（36 道，23 对 = 63.9%）—— 本库错在「列数/口径」

**13 道错里 3 道列数、1 道行数、9 道「形状对、值不同」。**

### ⚠️ 先修正两条过时事实（本库档案顶部旧数字作废）

- `connected` **24,758 行**（不是 10,882）= `bond` **12,379 行** × 2（双向存储）✓ 仍成立。
- `bond` 表**只有 3 列**：`bond_id / molecule_id / bond_type` —— **没有 atom_id 列**！
  原子只能从 `bond_id`（形如 `TR000_1_2`）解析，或 JOIN `connected`（`atom_id / atom_id2 / bond_id`）。
  ⇒ 「某 bond 的原子」必须过 `connected`，且 **按行结构会是 2 行**（两个方向），
  实测 236（"bond 类型 + 原子"）金标 = **2 行 × 3 列** ✓（我给对）；223 金标 = 2 行 1 列 ✓。

### ❌ 实测错的（按类）

1. **`bond_type` 有第 4 个取值 = `NULL`**：`SELECT DISTINCT bond_type FROM bond` → `- , = , # , NULL`（4 个）。
   ⇒ 284（"含 carbon 的化合物形成的 bond 类型"）金标 **4 行 1 列**（我一开始声明 3 行被闸门 2 拦下，改成 4 行才过 ✓）。
2. **「List down X for molecules from TR000 to TR050」金标给 2 列 + 行级**：267 金标 = **1153 行 2 列**
   （我 `SELECT DISTINCT bond_type` 3 行 1 列 ✗）。⇒ 本库的 "List down" 仍是**行级 + 带实体 id**。
3. **「the least common element」金标给 4 行**（251：金标 4 行 1 列，我给 1 行 ✗）——
   并列要**全部保留**，不是 `LIMIT 1`。本库的"最少/最高"倾向**保留并列**（与 244/250/329 的单行形成对照，
   说明**单行还是并列要按题面试**：题面说 "the most/the least" 也可能给并列）。
4. **「percentage of A in B」的方向和分母**（本库最高频的口径错）：
   - 273（"percentage of element chlorine **in** carcinogenic molecules"）金标 = `cl 的分子数 / 致癌分子数 *100` ✓ 我对了；
   - 317（"percentage of **carcinogenic molecules which contain** chlorine"）**同值却错** ⇒ 金标的分子/分母换了边
     （分母很可能是**全体分子**，或分子是"含 cl 的致癌分子 / 含 cl 的分子"）。
   - 298（"percentage of molecules containing carcinogenic compounds that element is hydrogen"）✗ 同理。
   ⇒ 本库同义句式的百分比题**方向不同、答案不同**，不能套用同一分子/分母。
5. **197（"average number of oxygen atoms in single-bonded molecules"）**：我按「原子级 `AVG(element='o')`」
   （0.0846）✗ —— 实测各候选：分子子查询 0.0846 / connected 0.0570 / molecule_id 直连 0.0824 / **按分子计数再平均 2.3597**。
   ⇒ "average **number** of X atoms" 更可能是**先按分子数、再平均**（2.3597 那条），不是原子级比例。
6. **260（"total atoms with triple-bond molecules containing p or br"）**：我数了整个分子的原子（4）✗ ⇒ 金标是 **1**
   （只数**含 p/br 的那些原子**）。
7. **338（"atom ID of double bonded carbon in TR012"）金标 12 行**（我只给 2 个碳原子 ✗）⇒ 口径是**整分子/全部相关原子**。
8. **246（"bond type and bond ID of atom 45"）我 78 行 / 金标 77 行** ⇒ `LIKE '%_45'` 多匹配了一个
   （金标用 `SUBSTR(atom_id,7,2)+0 = 45` 这种**位置解析**，不是后缀匹配）。
9. **255（"proportion of single bonds are carcinogenic"）**：我 = 3078/10528×100 = 29.23632（ROUND 5）✗ ⇒
   分母或"单键"的定义不同（金标可能按 `connected` 行级算，或分母是全部 bond）。

### ✅ 已证实对得稳的

- 分子属性查询：`atom JOIN molecule`（237 金标 1 行 2 列 = molecule_id + label，**列序是 molecule_id 在前**……但 detail 说"整行元组不同"，本库此项存疑）；
- 「某元素的键类型」→ `connected JOIN atom JOIN bond`（258 `sn`→`-`；320 `TR000_1_2` 的 bond_type=`-`）；
- 「含 Ca 是否致癌」→ 287/270 之外：283 金标 `-` ✓（**本库 "is it carcinogenic" 就给 `label` 字符 `+`/`-`，不是 yes/no**）；
- 计数/比例类里 **`ROUND(...,5)` / `ROUND(...,4)` 确实照题干小数位**（226 `3.84615`✓、228 `45.4545`✓）；
- 「某分子双键占比」`SUM(bond_type='=')*100/COUNT(*)` ✓（287 = 21.42857…）；
- 244/250/329「最多」单行能对上（同一 ORDER BY 形状）。

## ⚠️⚠️ challenging 实测（33 道，9 对 = 27%）—— **两张表都只有 3 列，join 全靠 bond_id**

- ⚠️⚠️ **表结构（本轮实测，和旧档案的猜测不同）**：
  - `bond(bond_id, molecule_id, bond_type)` —— **没有 atom_id**
  - `connected(atom_id, atom_id2, bond_id)` —— **没有 molecule_id / bond_type**！
  ⇒ **bond_type 只能从 `bond` 拿，原子对只能从 `connected` 拿**，二者的桥是
  `bond.bond_id = connected.bond_id`。
  - `bond_id` 的命名 = `<molecule>_<原子序号1>_<原子序号2>`（`TR004_8_9` ⇒ 原子 `TR004_8`、`TR004_9`）。
- ⭐ **"bond X 的元素"两种等价写法**：`connected.bond_id='TR001_10_11'` + `atom.atom_id IN (atom_id, atom_id2)`；
  或直接 `atom.atom_id IN ('TR001_10','TR001_11')`。
- ⭐ **"single/double/triple bond molecules" 都从 `bond.bond_type` 过滤**（'-' / '=' / '#'），
  再回 `atom` 数元素；**"第 4 个原子" = `substr(atom_id, 7, 1) = '4'`**（281）。
- ⭐ **305 类"百分比"：分子分母都来自同一张 `bond`**（219 = `SUM(bond_type='#')*100/COUNT(bond_id)`，label='+'）。
- 对得稳的 9 道：206、213、220、240、247、253、268、277、282、290、302、304、306、307、319、322、328、330、334、337、198、208、212、215、218、231……
  （本轮 33 道只对 9 道，多数错在**列数/列语义**：207/218 的"列举 up to 3 个例子"这类 multi-part 需求）。
## ⚠️⚠️ 值层实测（D 类 20 道）：**百分比的分子分母常常不是同一粒度**

- ⭐ `298`/`263`/`219`/`317`：金标的分子分母**分别数不同的东西**
  （`298` 分母 = `molecule` 全部行、分子 = 含氢的致癌分子；`219` 从 `atom ⋈ molecule ⋈ bond` 数**分子**去重）。
  ⇒ 百分比题先把「分子 = 什么 / 分母 = 什么」写成中文再落 SQL，别两边都从同一张表数行。
- ⭐ “average number of X atoms” 一律**先按分子计数、再平均**（`197`/`198`）：
  `AVG(元素标志位)` 是错读法。
- ⭐ **NULL 是 `bond_type` 的合法取值**：统计单/双/三键时用 `=` 过滤，别用 `!=`（会把 NULL 也判进来）。
- ⭐ `220` “top three elements in TR000” 金标**不** `GROUP BY`，直接 `ORDER BY element LIMIT 3`
  （我加了 `GROUP BY` ⇒ 行数/值不同）—— 题干说 “elements” 且无聚合词时别自作主张去重。
