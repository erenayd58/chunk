# KKB 2024 Prediction-Level Failure Analysis

Authoritative exact/±1 metrics are read-only invariants. Diagnostics do not alter matching, REVIEW-ignore, region filtering, or same-source fragment exclusion.

## Evaluation attribution

| Run | HIGH | Matched ±1 | Exact | Missed | Semantic TP | Size TP | Hard TP | Other TP | Ignored REVIEW |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v3 | 15 | 8 | 6 | 7 | 3 | 5 | 0 | 0 | 2 |
| a3 | 15 | 8 | 6 | 7 | 3 | 5 | 0 | 0 | 2 |
| a4 | 15 | 8 | 6 | 7 | 3 | 5 | 0 | 0 | 2 |

### FP by selected reason

- v3: `hard_limit_fallback`=3, `size_fallback`=3
- a3: `hard_limit_fallback`=3, `size_fallback`=2
- a4: `hard_limit_fallback`=2, `size_fallback`=2

## Missed HIGH boundaries

| Run | Annotation | Region | shift 1/2/3 | Combined | Threshold | Heading | Section transition | Suppression |
|---|---|---|---|---:|---:|---:|---:|---:|
| v3 | risk-narrative-gap-007 | risk-narrative | 0.073898/0.049730/0.033713 | 0.051942 | 0.065073 | false | false | true |
| v3 | risk-true-heading-transitions-gap-006 | risk-true-heading-transitions | 0.069035/0.048321/0.029567 | 0.048257 | 0.065073 | true | true | true |
| v3 | project-missed-heading-gap-004 | project-missed-heading | 0.074780/0.042836/0.035137 | 0.051014 | 0.065073 | false | false | true |
| v3 | project-missed-heading-gap-005 | project-missed-heading | 0.064835/0.035142/0.032338 | 0.044441 | 0.065073 | false | false | false |
| v3 | hr-false-heading-gap-008 | hr-false-heading | 0.079377/0.043054/0.030703 | 0.050950 | 0.065073 | true | true | true |
| v3 | hr-false-heading-gap-009 | hr-false-heading | 0.063604/0.043206/0.037359 | 0.048065 | 0.065073 | true | true | false |
| v3 | financial-table-pressure-gap-001 | financial-table-pressure | 0.085992/0.031484/0.027014 | 0.048818 | 0.065073 | true | true | true |
| a3 | risk-narrative-gap-007 | risk-narrative | 0.073898/0.049730/0.033713 | 0.051942 | 0.065073 | false | false | true |
| a3 | risk-true-heading-transitions-gap-006 | risk-true-heading-transitions | 0.069035/0.048321/0.029567 | 0.048257 | 0.065073 | true | true | true |
| a3 | project-missed-heading-gap-004 | project-missed-heading | 0.074780/0.042836/0.035137 | 0.051014 | 0.065073 | false | false | true |
| a3 | project-missed-heading-gap-005 | project-missed-heading | 0.064835/0.035142/0.032338 | 0.044441 | 0.065073 | false | false | false |
| a3 | hr-false-heading-gap-008 | hr-false-heading | 0.079377/0.043054/0.030703 | 0.050950 | 0.065073 | true | true | true |
| a3 | hr-false-heading-gap-009 | hr-false-heading | 0.063604/0.043206/0.037359 | 0.048065 | 0.065073 | true | true | false |
| a3 | financial-table-pressure-gap-001 | financial-table-pressure | 0.085992/0.031484/0.027014 | 0.048818 | 0.065073 | true | true | true |
| a4 | risk-narrative-gap-007 | risk-narrative | 0.073898/0.049730/0.033713 | 0.051942 | 0.065073 | false | false | true |
| a4 | risk-true-heading-transitions-gap-006 | risk-true-heading-transitions | 0.069035/0.048321/0.029567 | 0.048257 | 0.065073 | true | true | true |
| a4 | project-missed-heading-gap-004 | project-missed-heading | 0.074780/0.042836/0.035137 | 0.051014 | 0.065073 | false | false | true |
| a4 | project-missed-heading-gap-005 | project-missed-heading | 0.064835/0.035142/0.032338 | 0.044441 | 0.065073 | false | false | false |
| a4 | hr-false-heading-gap-008 | hr-false-heading | 0.079377/0.043054/0.030703 | 0.050950 | 0.065073 | true | true | true |
| a4 | hr-false-heading-gap-009 | hr-false-heading | 0.063604/0.043206/0.037359 | 0.048065 | 0.065073 | true | true | false |
| a4 | financial-table-pressure-gap-001 | financial-table-pressure | 0.085992/0.031484/0.027014 | 0.048818 | 0.065073 | true | true | true |

### Multi-scale suppression

- v3: 5 HIGH FN
- a3: 5 HIGH FN
- a4: 5 HIGH FN

## Accepted merge diagnostics

| Run | Boundary | Original reason | Shift | Threshold | Strength | Pair shift | Margin | Structure compatible |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| a3 | 922 | size_fallback | 0.028279 | 0.065073 | 0.000000 | 0.043512 | 0.021561 | True |
| a3 | 1327 | adaptive_semantic_boundary | 0.084496 | 0.065073 | 0.020775 | 0.064474 | 0.000599 | False |
| a4 | 922 | size_fallback | 0.028279 | 0.065073 | 0.000000 | 0.043512 | 0.021561 | True |
| a4 | 1327 | adaptive_semantic_boundary | 0.084496 | 0.065073 | 0.020775 | 0.064474 | 0.000599 | False |

## Original boundary strength distribution

| Run | N | Min | Median | P75 | P90 | P95 | Max | Guard | At/above guard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| a3 | 136 | 0.000074 | 0.006778 | 0.011498 | 0.016934 | 0.024595 | 0.035013 | 0.500000 | 0 |
| a4 | 136 | 0.000074 | 0.006778 | 0.011498 | 0.016934 | 0.024595 | 0.035013 | 0.500000 | 0 |

### Boundary 1327 case study

- a3: original reason `adaptive_semantic_boundary`, original shift 0.084496, threshold 0.065073, strength 0.020775, pooled pair shift 0.064474, margin 0.000599, structure compatibility `False`.
- a4: original reason `adaptive_semantic_boundary`, original shift 0.084496, threshold 0.065073, strength 0.020775, pooled pair shift 0.064474, margin 0.000599, structure compatibility `False`.

## HIGH/REVIEW proximity (distance <= 1)

| Region | HIGH | REVIEW | Gaps | Distance |
|---|---|---|---|---:|
| legal-list-to-operations | legal-list-to-operations-gap-012 | legal-list-to-operations-gap-013 | 863 / 864 | 1 |

## Five observed failure patterns (A4 focus)

1. Multi-scale suppression affects 5 of 7 HIGH FN.
2. All available individual scales are at/below threshold for 2 HIGH FN.
3. Combined shift is already an adaptive semantic candidate but the interval selector does not cut within ±1 for 0 HIGH FN.
4. 4 HIGH FN have an intervening heading; 4 have a parser section transition.
5. 4 primary FP are produced by size/hard fallback boundaries rather than semantic boundaries.
