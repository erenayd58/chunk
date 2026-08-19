# V5 Scale Calibration Research — KKB Development Checkpoint

> Outcome: hypothesis not supported on development checkpoint. This is a development checkpoint only; V5 is not validated.

No KKB gold annotation was used to fit weights, thresholds, or constants. B1 is diagnostic-only; B2 uses the frozen per-scale estimator, frozen V3 scale weights, and threshold-relative excess. B3 adds the unchanged post-conformance semantic-safe merge.

## B0–B3 results

| Run | Exact P/R/F1 | ±1 P/R/F1 | Sem TP/FP | Size TP/FP | Hard TP/FP | FN | Suppression FN | Chunks | <160 | Size fallback | Hard fallback |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.4286/0.4000/0.4138 | 0.5714/0.5333/0.5517 | 3/0 | 5/3 | 0/3 | 7 | 5 | 244 | 2.46% | 154 | 19 |
| B1 | 0.4286/0.4000/0.4138 | 0.5714/0.5333/0.5517 | 3/0 | 5/3 | 0/3 | 7 | 5 | 244 | 2.46% | 154 | 19 |
| B2 | 0.5385/0.4667/0.5000 | 0.5385/0.4667/0.5000 | 4/1 | 3/2 | 0/3 | 8 | 5 | 247 | 2.02% | 122 | 19 |
| B3 | 0.5833/0.4667/0.5185 | 0.5833/0.4667/0.5185 | 4/1 | 3/1 | 0/3 | 8 | 5 | 245 | 1.22% | 121 | 19 |

## Original seven HIGH false negatives

| Annotation | Suppression | B1 candidate scales at gold | B0 | B1 | B2 | B2 mechanism/scales | B3 | B3 mechanism/scales |
|---|---:|---|---|---|---|---|---|---|
| risk-narrative-gap-007 | true | none | MISSED | MISSED | MISSED | -/- | MISSED | -/- |
| risk-true-heading-transitions-gap-006 | true | none | MISSED | MISSED | MATCHED_EXACT | indirect_size_fallback/- | MATCHED_EXACT | indirect_size_fallback/- |
| project-missed-heading-gap-004 | true | none | MISSED | MISSED | MISSED | -/- | MISSED | -/- |
| project-missed-heading-gap-005 | false | none | MISSED | MISSED | MISSED | -/- | MISSED | -/- |
| hr-false-heading-gap-008 | true | none | MISSED | MISSED | MISSED | -/- | MISSED | -/- |
| hr-false-heading-gap-009 | false | none | MISSED | MISSED | MISSED | -/- | MISSED | -/- |
| financial-table-pressure-gap-001 | true | none | MISSED | MISSED | MISSED | -/- | MISSED | -/- |

## Guardrail

KKB is a development checkpoint. Better B2/B3 scores are evidence for a holdout experiment, not evidence that V5 is validated.
