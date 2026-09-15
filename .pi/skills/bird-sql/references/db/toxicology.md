# toxicology （4 表） · simple EX 82.9% (63/76)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

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

**⚠️ 全量实测（76 道 → 63 对 / 13 错，82.9%）：13 道错题里 7 道是“列数”错**

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
