# V1/V2/V3/V4 Implementasyon Mimarisi

## Modüller

```text
src/amsc/
  models.py        canonical ve çıktı modelleri
  config.py        strict ve sürüme özel V1/V2/V3/V4 YAML config
  io.py            JSONL validation ve çıktı writer
  units.py         heading attachment ve rendered token budgeting
  tokenization.py  TokenCounter protokolü ve tiktoken adapter'ı
  embeddings.py    boundary/retrieval protokolleri, E5 input ve pooling
  cache.py         disk embedding cache
  features.py      raw 1↔1 ve multi-scale semantic shift
  thresholds.py    fixed ve hierarchical adaptive estimator'lar
  selection.py     ortak interval selector, V1/V2 tail resolver'ları
  chunker.py       ortak orchestration ile V1/V2/V3 facade'ları
  structure.py     parser-agnostic structural evidence ve bounded support
  strength.py      original/effective threshold-relative strength scorer'ları
  v4_selection.py  ayrı V4 threshold-relative/raw ablation selector'ı
  merge.py         retained-embedding semantic-safe merge resolver
  v4_chunker.py    V3'ten ayrı V4 orchestration ve A1–A4 composition
  evaluation.py    deterministic exact/±1 boundary ve chunk metrikleri
  failure_analysis.py authoritative metricten bağımsız prediction/gold/merge audit
  cli.py           validate/chunk komutları
```

## Veri akışı

```text
canonical JSONL
  → strict validation
  → heading attachment
  → rendered-token hard split planning
  → cache-aware semantic boundary embedding
  → V1/V2 adjacent veya V3 multi-scale semantic shift
  → V1 fixed veya V2/V3 hierarchical adaptive candidate set
  → V1–V3 raw-shift veya V4 threshold-relative interval scoring
  → non-semantic short-tail cleanup
  → V4 optional semantic-safe adjacent merge
  → exact configured-counter invariant
  → chunks.jsonl + boundaries.jsonl + resolved-config.json
```

## Extension point'ler

- `SemanticThresholdEstimator` protokolü V1 `FixedThresholdEstimator` ile V2 `HierarchicalAdaptiveThresholdEstimator` implementasyonlarını selector'dan ayırır.
- `SemanticFeatureExtractor` protokolü adjacent V1/V2 ve multi-scale V3 feature hesaplarını ortak orchestration'dan ayırır.
- V4, V3 facade'ına koşul eklemeden ayrı orchestration, structural evidence, strength, selector ve merge dependency'leri kullanır.
- Retrieval evaluator yalnızca `RetrievalEmbedder` kullanır; boundary embedder ve cache namespace'inden bağımsızdır.
- Production tokenizer öğrenildiğinde `TokenCounter` adapter'ı değiştirilir; chunker orchestration değişmez.

## Test stratejisi

Testler model indirmeden fake model tokenizer ve deterministic embedding backend kullanır. Ayrı unit test gerçek `cl100k_base` sayım/split davranışını kontrol eder.

Kapsam:

- canonical validation ve sıra/kimlik hataları,
- heading exclusion/attachment ve oversized heading,
- heading-aware content bütçesi,
- prefix, 512-limit fallback ve weighted pooling,
- rol/politika duyarlı cache,
- exact semantic text hash'i; whitespace-normalized cache key kullanılmaması,
- cosine/threshold hesabı,
- ilk threshold yerine interval optimumu,
- target-distance ve size/hard fallback,
- yalnızca non-semantic fallback tail merge,
- exact configured-counter hard cap,
- uçtan uca chunk ve provenance JSONL.

V1 ve V2 fixture çıktıları `chunks.jsonl` ve `boundaries.jsonl` için byte-level golden testle korunur. V2 testleri median/MAD, sabit `Q75-Q25` IQR, bağımsız quantile clamp, positive-tail, uniform-document degeneracy, short-document fixed fallback, section→parent→document scope çözümü, descendant sample seti, scope-kind provenance, adaptive tail koruması ve CLI routing'i kapsar. V3 testleri multi-scale cosine, token-sqrt pooling, L2 normalization, edge weight renormalization, `available_scales`/`scale_count`, outlier suppression, gerçek topic transition, semantic-run isolation, hard cap ve determinism'i doğrular.

## V2 threshold akışı

1. Bütün heading'ler semantic embedding listesinden çıkarılır; sadece content run'ları embed edilir.
2. Bütün run'lardaki raw boundary feature'ları selection başlamadan önce toplanır.
3. Boundary scope'u komşu `section_path` değerlerinin longest-common-prefix'i olarak hesaplanır.
4. En derin yeterli ve ayırt edilebilir section dağılımı kullanılır; gerekirse parent/document'a çıkılır.
5. Document örneği sekizden azsa `short_document_fixed_fallback` kullanılır; quantile türetilmez.
6. Her boundary kendi local threshold'una göre candidate olur.
7. Ortak interval selector candidate'ları V1 ile aynı raw semantic shift + target-distance skoru üzerinden seçer.

`threshold_scope_kind` boundary JSONL'de bulunduğu için section/parent/document kullanım oranları ek bir runtime metriği eklenmeden hesaplanabilir. Farklı local threshold'lardaki candidate'ların raw shift ile kıyaslanması V2 limitation'ıdır; threshold-relative veya percentile kalite sonraki sürüme bırakılmıştır.

## V3 feature akışı

1. Semantic run içindeki content-unit embedding'leri V2 ile aynı cache/E5 akışından alınır.
2. Full-symmetric `1↔1`, `2↔2`, `3↔3` pencereleri belirlenir; run sınırı aşılmaz.
3. Unit embedding'leri configured-counter token sayısının kareköküyle ağırlıklandırılır ve pooled window L2-normalize edilir.
4. Her available scale için shift hesaplanır.
5. `0.35/0.26/0.39` başlangıç ağırlıkları available scale'ler üzerinde yeniden normalize edilerek birleşik semantic shift üretilir.
6. `available_scales`, `scale_count`, scale shift'leri ve effective ağırlıklar provenance'a yazılır.
7. Değişmeyen V2 threshold estimator birleşik shift dağılımını kullanır.

Farklı available-scale bileşimlerinin aynı threshold dağılımında değerlendirilmesi V3/V4 limitation'ıdır; ayrı threshold veya composition normalization uygulanmaz.

## V4 core akışı

1. V3 ile aynı heading attachment, hard-split planning, cached unit embedding, multi-scale feature ve hierarchical adaptive threshold aşamaları çalışır.
2. Exact unit embedding'leri `unit_id → vector` retained map olarak tutulur; merge yeni embedding çağrısı yapmaz.
3. Structural evidence provider heading attachment identity/provenance, section transition ve atomic content-type geçişlerini boundary bazında çıkarır.
4. Soft policy original adaptive threshold'u en çok `0.04` gevşetir; `0.12` semantic floor original threshold'u yükseltmek için kullanılmaz.
5. Dual scorer hem original hem effective threshold-relative strength'i provenance'a yazar.
6. V4 selector A1/A4'te effective strength + target-distance, A2/A3'te frozen raw semantic shift + target-distance kullanır.
7. V3 tail resolver değişmeden çalışır.
8. A3/A4'te semantic-safe merge adjacent small-chunk çiftlerini original threshold ve original strength ile değerlendirir, retained embedding'lerden pair shift üretir ve tek non-overlapping pass uygular. `hard_limit_fallback` original boundary'leri merge değerlendirmesine girmeden reddedilir.
9. Her çıktı chunk'ı full rendered text üzerinden configured-counter hard cap invariant'ına yeniden doğrulanır.

Structure merge uygunluğunu hard biçimde etkileyemez. Aynı section/identity bilgisi yalnız
provenance ve deterministic proposal ordering için kullanılabilir. Merge'de selector'ın
effective threshold'u kullanılmaz.

Proposal ranking sırası frozen olarak: higher absolute cohesion margin, lower original
boundary strength, lower target distance, lower original focus index, left direction ve
yalnız otherwise exact tie durumunda less structural mismatch. Relative pair-shift oranı
ranking criterion değildir.

## Atomic hard-cap politikası

Table, list ve visual unit'ler normalde tek semantic unit olarak korunur. Herhangi biri
heading/separator bütçesi dahil tek başına hard cap'i aşıyorsa mevcut deterministic
`TokenCounter.split()` yolu ile zorunlu fragment'lara ayrılır. Bu istisna table, list ve
visual için aynıdır; hard cap atomiclikten daha güçlü invariant'tır. V4 provenance'ı
`atomic_type`, `source_unit_id`, fragment index/count ve `configured_hard_cap_forced_split`
nedenini saklar.

## V4 ablation composition

| Bileşim | Soft structure | Selector sinyali | Semantic-safe merge |
|---|---:|---|---:|
| A0 | Hayır | Frozen V3 raw shift | Hayır |
| A1 | Hayır | Threshold-relative original strength | Hayır |
| A2 | Evet | Frozen V3 raw shift | Hayır |
| A3 | Hayır | Frozen V3 raw shift | Evet |
| A4 | Evet | Threshold-relative effective strength | Evet |

`configs/v4.yaml` strict'tir; `--ablation` yalnız V4 için kabul edilir ve resolved
config/config hash'e girer. A5 contextualization bilerek uygulanmamıştır.

## 2024 faaliyet raporu

Depodaki PDF doğrudan işlenmez. IDP/parser çıktısı aşağıdaki dosyaya normalize edildikten sonra:

```powershell
py -3.11 -m amsc.cli validate --input data/kkb-2024.units.jsonl

py -3.11 -m amsc.cli chunk `
  --input data/kkb-2024.units.jsonl `
  --config configs/v1.yaml `
  --output artifacts/kkb-2024-v1

py -3.11 -m amsc.cli chunk `
  --input data/kkb-2024.units.jsonl `
  --config configs/v2.yaml `
  --output artifacts/kkb-2024-v2

py -3.11 -m amsc.cli chunk `
  --input data/kkb-2024.units.jsonl `
  --config configs/v3.yaml `
  --output artifacts/kkb-2024-v3

py -3.11 -m amsc.cli chunk `
  --input data/kkb-2024.units.jsonl `
  --config configs/v4.yaml `
  --ablation a4 `
  --output artifacts/kkb-2024-v4-a4
```

V1/V2/V3/V4 çıktıları frozen representative region'larda 15 HIGH boundary ile exact ve ±1 one-to-one evaluator üzerinden karşılaştırılır. 30–50 gold question/evidence retrieval seti ilerideki retrieval-side ablation için hazırlanır.

## Bilinçli kapsam dışı

- scale-composition normalization veya ayrı adaptive threshold,
- generic heading protection/mandatory cut,
- percentile selector scoring,
- iterative veya non-adjacent merge,
- A5 contextualization,
- retrieval/BM25/RRF/rerank,
- PDF/IDP parsing,
- LLM/API çağrısı,
- production tokenizer uyumluluk iddiası.
