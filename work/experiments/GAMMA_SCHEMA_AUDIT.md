# Gamma: offline schema audit

## Scope

- Dataset: dev2025, all 1,534 questions.
- Reproduce: `python tools/schema_audit.py` (stdlib only, no API calls).
- Machine results: `work/experiments/gamma_schema_audit.json`.
- The runner's default behavior is unchanged. No predictions were regenerated.
- All sizes below are **characters, not tokens**. Base prompt excludes runtime reconnaissance and retry messages.

## Findings

| Component | Mean characters |
|---|---:|
| System (direct preamble + rules) | 30,490 |
| Full schema including samples | 4,815 |
| Human-annotated descriptions | 5,651 |
| Full base prompt, including question/evidence/wrappers | 41,312 |

| Sample rendering | Schema characters saved | Base prompt characters saved |
|---|---:|---:|
| All original samples (baseline) | 0% | 0% |
| Remove all samples; retain all column metadata | 66.84% | 7.79% |
| Retain low-cardinality values; remove high-cardinality examples | 47.61% | 5.55% |
| Also retain high-cardinality examples for lexical column matches | 42.57% | 4.96% |

Every variant preserves every table and column name, type, and PK annotation. This is a structural guarantee, **not** an accuracy guarantee: sample values and formats may still matter.

## Evaluation corrections

- Replaced exploratory regex dependency extraction with SQLite authorizer callbacks during `EXPLAIN` compilation. All 1,534 gold statements compiled successfully. No gold queries were executed.
- Zero missing parses in a regex report does not establish extraction correctness. Earlier regex recall figures should remain provisional.
- Gold dependencies are used only for evaluation, not for selecting sample-bearing columns.
- The new, word-boundary lexical selector (without recon or embeddings) contains all gold-referenced columns on only 388/1,534 questions; micro column recall is 54.13%. It is a different selector from the previous prototype, not a like-for-like ablation.
- Missing a column referenced by one gold SQL is a risk, not proof that no equivalent SQL could answer the question.
- Character savings cannot be reported as token savings or EX improvements.
- This experiment does not reproduce the paper's semantic schema linking. A failed lexical prototype does not disprove embedding/LLM-assisted linking.

## Decision

Do not enable hard schema pruning. Do not start a paid sample-compression run solely on these small character savings. If prompt reduction remains the objective, first examine the larger shared rule block with separate controls and regression checks; do not assume dropping rules improves accuracy.

## Validation

The audit includes self-tests for CTEs, quoted identifiers, year columns, stars, alias scopes, COUNT(*), write rejection, rendering, and word boundaries. It is called by the runner regression suite.

Full regression finished with 325 passing checks and zero failures. A fresh isolated fixture initially exposed missing description CSV data; a synthetic CSV was added only to the local test fixture, then the full suite passed. The existing fixture generator itself remains unchanged.
