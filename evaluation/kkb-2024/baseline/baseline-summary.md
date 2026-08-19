# KKB 2024 V1/V2/V3 Frozen-Input Baseline

Canonical input SHA256: `2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5`

All runs use the checked-in, unchanged `configs/v1.yaml`, `configs/v2.yaml`, and `configs/v3.yaml`. Boundary metrics use 15 manually accepted `confidence=high` boundaries across the nine checkpoint regions. Five `confidence=review` boundaries remain outside the primary gold set; predictions within their tolerance are ignored rather than counted as false positives.

The concrete runtime and cached Hugging Face snapshot used for these persisted baselines are recorded in `environment.json`.

| Metric | V1 | V2 | V3 |
|---|---:|---:|---:|
| Chunk count | 235 | 246 | 244 |
| Token min | 61 | 6 | 6 |
| Token median | 674.0 | 658.0 | 659.5 |
| Token P90 (nearest rank) | 756 | 803 | 799 |
| Token max | 1126 | 1126 | 1126 |
| `<160` chunk count | 4 | 5 | 6 |
| `<160` chunk ratio | 0.017021 | 0.020325 | 0.024590 |
| Size fallback count | 216 | 150 | 154 |
| Size fallback ratio | 0.923077 | 0.612245 | 0.633745 |
| Hard fallback count | 18 | 19 | 19 |
| Hard fallback ratio | 0.076923 | 0.077551 | 0.078189 |
| Forced split fragment count | 16 | 16 | 16 |
| Forced same-source chunk boundary count | 8 | 8 | 8 |
| Semantic candidates | 0 | 138 | 136 |
| Primary ±1 Precision | 0.384615 | 0.384615 | 0.571429 |
| Primary ±1 Recall | 0.333333 | 0.333333 | 0.533333 |
| Primary ±1 F1 | 0.357143 | 0.357143 | 0.551724 |
| Secondary exact Precision | 0.307692 | 0.230769 | 0.428571 |
| Secondary exact Recall | 0.266667 | 0.200000 | 0.400000 |
| Secondary exact F1 | 0.285714 | 0.214286 | 0.413793 |

Match counts:

- V1 ±1: `TP=5, FP=8, FN=10`; exact: `TP=4, FP=9, FN=11`.
- V2 ±1: `TP=5, FP=8, FN=10`; exact: `TP=3, FP=10, FN=12`.
- V3 ±1: `TP=8, FP=6, FN=7`; exact: `TP=6, FP=8, FN=9`.

Threshold scope distribution across all semantic boundary evidence:

- V1: not applicable (fixed threshold).
- V2: document `1237`, section `91`, parent section `0`.
- V3: document `1237`, section `91`, parent section `0`.

V3 available-scale composition across all semantic boundary evidence:

- `[1]`: 2
- `[1,2]`: 2
- `[1,2,3]`: 1324

## Representative provenance

### V1 fixed threshold

Boundary `674`, `p-00905 → p-00906`:

- `semantic_shift=0.1094525754`
- `fixed_threshold=0.20`
- `semantic_candidate=false`
- selected reason: `size_fallback`
- candidate chunk tokens: `762`

The full corpus maximum V1 shift is `0.1354669333`, so the unchanged PoC fixed threshold produces no semantic candidate on this frozen input.

### V2 hierarchical adaptive threshold

Boundary `864`, `l-01142 → p-01144` (legal list → Operations narrative):

- `semantic_shift=0.1167283058`
- adaptive threshold `0.0915716678`
- scope kind `document`, sample count `1328`
- method `mad_quantile`, low confidence `false`
- `semantic_candidate=true`
- selected reason: `adaptive_semantic_boundary`
- candidate chunk tokens `674`, selection score `0.2837530150`

### V3 multi-scale effect

Boundary `674`, `p-00905 → p-00906`:

- `shift_1=0.1094525615`
- `shift_2=0.0567736117`
- `shift_3=0.0312267376`
- available scales `[1,2,3]`
- combined `semantic_shift=0.0652479632`
- adaptive threshold `0.0650731325`
- scope kind `document`, sample count `1328`, method `mad_quantile`
- `semantic_candidate=true`
- selected reason: `adaptive_semantic_boundary`
- candidate chunk tokens `396`, selection score `0.1396057780`

This example exposes the multi-scale plumbing but is not a gold-quality claim: `p-00906` is a visually heading-like string that the frozen parser emitted as a paragraph.

## Persisted output hashes

| File | SHA256 |
|---|---|
| V1 chunks | `9ad077e2cdaf5763224575b729445c40dafe9897e3cdc70ffe8bfead587e08cc` |
| V1 boundaries | `a860974269d13390dc6f83c3559ed7b173352a1d134bc93f5125524aa2adcf77` |
| V2 chunks | `19055f744043f4a079e0461ad1c97723f1bebc883912d2a13e029b3fea69039b` |
| V2 boundaries | `e2d308ccb1c373a69c0c0d13f16232600a6381eec45370ef9ae0a3cdb297bb96` |
| V3 chunks | `4c87d80052948e2075ada587424001fb6e5b6e58815e584ffbb028cad36d80b7` |
| V3 boundaries | `5c2f3b353bbde37b2f225c622a27b9dc6dc3e2db43ff249cbca21ba9a621456b` |
