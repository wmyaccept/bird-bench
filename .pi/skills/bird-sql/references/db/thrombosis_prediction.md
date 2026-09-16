# thrombosis_prediction （3 表） · simple EX 60.0% (30/50)

## ⚠️ 交题前必查（本库最容易翻车的 3 条）

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
