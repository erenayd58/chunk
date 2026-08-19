# Phase 3C Semantic Comparator Research

> Development checkpoint only. No gold annotation was used for parameter tuning, and no validation claim is made.

C3 uses `c2` / `cosine_kernel_change_point` plus the frozen post-conformance semantic-safe merge.

## C0–C3 metrics

| Run | Exact P/R/F1 | ±1 P/R/F1 | Semantic TP/FP | Fallback TP/FP | FN | Chunks | Token min/med/P90/max | <160 | Size/hard fallback |
|---|---|---|---:|---:|---:|---:|---|---:|---:|
| C0 | 0.4286/0.4000/0.4138 | 0.5714/0.5333/0.5517 | 3/0 | 5/6 | 7 | 244 | 6/659.5/799/1126 | 2.46% | 154/19 |
| C1 | 0.1667/0.1333/0.1481 | 0.4000/0.2667/0.3200 | 2/2 | 2/4 | 11 | 247 | 6/659.0/841/1126 | 3.24% | 141/22 |
| C2 | 0.3750/0.4000/0.3871 | 0.6250/0.6667/0.6452 | 3/0 | 7/6 | 5 | 242 | 32/661.5/799/1126 | 1.65% | 160/17 |
| C3 | 0.4000/0.4000/0.4000 | 0.6667/0.6667/0.6667 | 3/0 | 7/5 | 5 | 239 | 96/664.0/802/1126 | 0.42% | 158/17 |

## Existing seven HIGH false negatives

| Annotation | Suppression | C1 status/reason | C2 status/reason | C3 status/reason |
|---|---:|---|---|---|
| risk-narrative-gap-007 | true | MISSED/- | MISSED/- | MISSED/- |
| risk-true-heading-transitions-gap-006 | true | MATCHED_PLUS_MINUS_ONE/size_fallback | MISSED/- | MISSED/- |
| project-missed-heading-gap-004 | true | MISSED/- | MATCHED_EXACT/size_fallback | MATCHED_EXACT/size_fallback |
| project-missed-heading-gap-005 | false | MISSED/- | MISSED/- | MISSED/- |
| hr-false-heading-gap-008 | true | MISSED/- | MISSED/- | MISSED/- |
| hr-false-heading-gap-009 | false | MISSED/- | MATCHED_EXACT/size_fallback | MATCHED_EXACT/size_fallback |
| financial-table-pressure-gap-001 | true | MISSED/- | MISSED/- | MISSED/- |

### Genuine semantic rescues

- C1: none
- C2: none
- C3: none

### Gold-position comparator evidence

| Annotation | C1 score/threshold/candidate | C2 score/threshold/candidate |
|---|---|---|
| risk-narrative-gap-007 | 0.033778/0.052018/false | 0.030308/0.043578/false |
| risk-true-heading-transitions-gap-006 | 0.031966/0.052018/false | 0.027249/0.043578/false |
| project-missed-heading-gap-004 | 0.036564/0.052018/false | 0.031922/0.043578/false |
| project-missed-heading-gap-005 | 0.031375/0.052018/false | 0.029172/0.043578/false |
| hr-false-heading-gap-008 | 0.043734/0.052018/false | 0.027072/0.043578/false |
| hr-false-heading-gap-009 | 0.023906/0.052018/false | 0.033517/0.043578/false |
| financial-table-pressure-gap-001 | 0.057190/0.052018/true | 0.025426/0.043578/false |

### Previously matched HIGH regressions

- C1: csr-visual-and-text-gap-001, legal-list-to-operations-gap-001, legal-list-to-operations-gap-012, risk-true-heading-transitions-gap-008, strategy-visual-fte-gap-001
- C2: none
- C3: none
