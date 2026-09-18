# thrombosis_prediction （3 表） · simple EX 60.0% (30/50)

## ⚠️ 交题前必查（本库最容易翻车的几条）

1. **`Examination.ID` 与 `Patient.ID` 是两套编号** —— 806 行里**只有 70 行**能 JOIN 上 Patient。
   涉及诊断/症状的题**先用 `Examination` 单表**，不要顺手 JOIN Patient（会得到 0 行或极少行）。
2. ⭐ **列归属**：`RVVT`、`aCL IgA/IgG/IgM`、`KCT`、`LAC`、`ANA`、`Symptoms`、`Thrombosis` 在 **`Examination`**，
   `Laboratory` 里**没有**（我写了 `Laboratory.RVVT` → `no such column`）。
   ⚠️ “anti-Cardiolipin antibody concentration status” 要给 **3 列 `aCL IgA, aCL IgG, aCL IgM`**（实测 1179，我只给了 IgM）。
3. **诊断值是首字母大写**：`'Aortitis'`、`'SLE'`、`'RA'`（evidence 写全大写时要核对），
   且金标常用**精确匹配**（`Diagnosis = 'Behcet'`，用 `LIKE '%Behcet%'` → 32 行 vs 金标 **5 行**，1186）。
   ⭐ **本库金标的输出约定**（实测 20 道里 16 对，全是这几条）：
   - “is X within normal range?” → `CASE WHEN <异常条件> THEN true ELSE false END`（小写 `true/false`，1205）；
     问“Is his/her X within normal range?” → `ID, CASE WHEN … THEN 'normal' ELSE 'abNormal' END`（1213）；
     问“state if …” → `CASE WHEN … THEN 'normal' ELSE 'abnormal' END`（1217）——**三道的写法各不相同，按题干句式挑**。
   - “were they treated as inpatient or outpatient” → **只给 `T1.Admission` 一列**（1212）；
     “list all patients with their sex and date of birth” → **`SEX, Birthday` 两列，不给 ID**（1207）；
     “list each patient's ID and GLU” → `ID, GLU`（1233）。
   - “exam / 就诊”的日期条件优先用 **`Examination."Examination Date"`**（1186 金标；`Patient.Description` 是另一回事）。
   - 百分比题用 `traps.md` ④ 的模板；本库百分比题很多。
   正常范围见 `database_description`：GOT<60、GPT<60、TP 6~8.5、ALB 3.5~5.5、WBC 3.5~9.0、IGG 900~2000。
   ⭐ **本库百分比/比例题特别多 → 必须用 `traps.md` ④ 的固定模板**（实测四道全是口径错：`*100` 的位置、过滤条件要放 WHERE）。

## 连接图与坑

```
Patient ──ID── Examination（就诊：Diagnosis / Symptoms / Thrombosis）
        ──ID── Laboratory（化验：44 个指标列，一人多行）
```
- **`Diagnosis` 在 `Patient` 和 `Examination` 都有，值不同**（`minidev idx 87`
  实测金标用 `Patient.Diagnosis`）。
- `Laboratory` 只覆盖 302 个患者（`Patient` 有 1238 个），大量列有 NULL。
- 化验指标的正常范围在 `database_description` 里（如 `LDH < 500`、`IGG 900~2000`）。

**⚠️⚠️ 全量实测（50 道：30 对 / 20 错，60%）——本库的最大坑是“三张表的 ID 并不真通”**

| 表 | 行数 | 不同 ID | 能 JOIN 上 `Patient` 的行数 |
|---|---|---|---|
| `Laboratory` | 13908 | 302 | **13908（全通）** |
| `Examination` | 806 | 763 | **只有 70**（!!） |

⇒ **`Examination.ID` 与 `Patient.ID` 基本是两套编号**。
涉及诊断/症状/血栓的题 **先用 `Examination` 单表把结果拿出来**，
不要顺手 `JOIN Patient`（一 JOIN 就只剩 70 行，`1221` 直接 0 行）。

⚠️ **本库错误率 40%，其中 17 道都是“形状对、值不同”** —— 说明存在系统性口径偏差
（计数用 `COUNT(*)` 还是 `COUNT(DISTINCT ID)`、要不要 JOIN `Examination`）。
⇒ 这种库不适合“逐题猜”，应该先做一次**专项口径实验**（把几种计数/JOIN 组合成一行摆出来对比）。

⚠️ **数值列可能带 `<` / `>` 前缀**（evidence 会提醒：“excluding any '<' or '>' prefix if present”）：
比较前要 `CAST(REPLACE(REPLACE(CAST(col AS TEXT),'<',''),'>','') AS REAL)`，
否则 `'<5'` 会被 CAST 成 0，把不该命中的行算进来。
另：**“latest record of each patient” 要 `Date=(SELECT MAX(Date) FROM Laboratory WHERE ID=...)`**。

---

## 补充（第 24 轮实测 40 道 moderate）

- ⭐ **`U-PRO`（尿蛋白）比较必须 `CAST(... AS REAL)`**：原值带 `<`/`>` 前缀，直接 `> 0 AND < 30` → 24 行；
  金标 `CAST("U-PRO" AS REAL) > 0 AND CAST(...) < 30` → 19 行（1250）。
- ⭐ **“data first recorded in YYYY” = `Patient."First Date"`**（不是 `Description`；1233 金标）。
  而 “exam / 就诊检查的日期” = `Examination."Examination Date"`（1186）。**`Description` 不是日期列的正解。**
- ⭐ **“how many patients” → `COUNT(T1.ID)`**（Patient JOIN Laboratory，患者数 ≠ 实验行数；1245/1252）。
- 区间默认**闭区间**（1252 IGG `BETWEEN 900 AND 2000`；1248 FG `<=150 OR >=450`），1211 LDH 是开区间例外。
- 年份比较一律用**字符串**（`>= '1990'`），写整数会因类型序恒真（1254）。
- 计数题的金标结构几乎都是三表：`Patient T1 INNER JOIN Laboratory T2 ON T1.ID=T2.ID [INNER JOIN Examination T3 ON T3.ID=T2.ID]`。

### ⭐ 抗体列（aCL/RVVT/KCT/LAC/ANA/RNP/SM/SC170/SSA/SSB/CENTROMEA/DNA）的读写约定

- **真实取值只有 `'negative'` 和 `'0'` 两种“正常”写法**（外加 NULL 与数字字符串）——实测：
  `RNP: NULL,'0','1','256','negative','16','64'`、`CENTROMEA: NULL,'0','negative'`。
- 所以：**normal → `X IN ('negative','0')`**（1265/1267/1273 金标）；
  ⚠️ **abnormal → 照抄 evidence 的原文 `X NOT IN ('-','+-')`，不要翻译成 `NOT IN ('negative','0')`**！
  库里根本**没有** `'-'`/`'+-'` 这两个值 → `NOT IN ('-','+-')` 实际等于“几乎全部行”，
  而翻译成 `NOT IN ('negative','0')` 会剔掉正常行 → 结果不同（1266 金标实测）。
- **诊断值一律 `=` 精确匹配**：`Diagnosis = 'APS'` 不是 `LIKE '%APS%'`（1264：LIKE 多出组合诊断行）。
- ⭐ **“diagnosed with X” 一律用 `Patient.Diagnosis`**，哪怕题干写 “in the examination”（1273 金标用的是 `T1.Diagnosis`＝Patient）。

### ⚠️ 金标自身有 OR/AND 缺括号的 bug（实测 3 次：1248 / 1265 / 1219）

- 形态：条件写成 `T2.RNP = 'negative' OR T2.RNP = '0' AND T1.Admission = '+'`
  —— 没括号 ⇒ 实际语义是 `'negative' OR ('0' AND Admission='+')`，我写成带括号的 `IN (…) AND …` → 计数不同。
- 同样形态：1248 `FG <= 150 OR FG >= 450 AND Birthday > '1980-01-01'`、1219 的 `(F AND a) OR (M AND b AND c)`。
- ⇒ **遇到“两值之一 AND 另一条件”的结构，按金标的无括号写法写**（得分优先；语义上确实是金标错）。

### 计数题的金标结构（⭐ 第 25 轮修正：上一版结论写反了！）

**实测 6 道（1287/1289/1298/1304 支持，1267/1308 例外），绝大多数长这样：**

```sql
SELECT COUNT(DISTINCT T1.ID) FROM Patient T1
  INNER JOIN Laboratory T2 ON T1.ID = T2.ID
  [INNER JOIN Examination T3 ON T1.ID = T3.ID]
WHERE <T1 上的条件> AND <T2/T3 上的条件>
```

- ⭐⭐ **`Patient` 永远是 T1，`Examination` 永远是 T3** —— 即使条件在
  Thrombosis / Symptoms / ANA Pattern / KCT / RVVT / aCL 上（1287/1289/1298/1304 四道金标全是这形状）。
- ⭐ **“how many patients” 默认 `COUNT(DISTINCT T1.ID)`**（患者数），
  只有金标根本不用 Patient 表时才 `COUNT(T1.ID)` 无 DISTINCT（1267/1308 是这种例外）。
- ⚠️ **换 T1 会改变候选集，直接改变答案**：`Examination.ID` 只有 **70** 个能连上 Laboratory/Patient，
  而 `Laboratory` 有 302 个 —— 所以“最高 TG 的患者的 Diagnosis”（1300）这类极值题，
  用 `Examination T1 JOIN Laboratory T2` 和 `Patient T1 JOIN Laboratory T2` **取到的不是同一批行**。
- **`Diagnosis` 用哪张表的**：Patient 参与 → `Patient.Diagnosis`（1273）；
  Patient 不参与（Examination+Laboratory 的极值/属性题）→ `Examination.Diagnosis`（1300 金标）。

- ⭐ **诊断名一律 `=` 精确**（1264 `='APS'`、1289 `='SJS'` 金标；用 `LIKE '%X%'` 会吃进组合诊断行）；
  唯一例外是 `SLE` 有时写 `LIKE '%SLE%'`（1279）——两种在无组合行时结果相同。

## 惯例卡片（实测统计，n=135 道已提交题的金标；数据集 dev2025）

- 计数形态：COUNT(DISTINCT) 29 / COUNT(列) 19 / COUNT(*) 6 / 无 81　⇒ 本库偏去重（29/54 计数题）⇒ 计数先试 `COUNT(DISTINCT 实体id)`
- 主表（FROM 第一张）：Patient 113 / Examination 12 / Laboratory 10　⇒ 主表几乎总是 **Patient**（113/135）
- `SELECT DISTINCT`：25/135　|　`*100`：8　|　`BETWEEN`：12
- 输出列数分布：1列×109 / 2列×15 / 3列×9 / 4列×2
- JOIN 数分布：0:21, 1:101, 2:12, 4:1

> 由 `bird_conventions db=thrombosis_prediction write_card=true` 生成（与工具输出同源），重跑即刷新；数字不要手改。
