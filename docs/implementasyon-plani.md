# V1/V2 Implementasyon Mimarisi

## Modüller

```text
src/amsc/
  models.py        canonical ve çıktı modelleri
  config.py        strict ve sürüme özel V1/V2 YAML config
  io.py            JSONL validation ve çıktı writer
  units.py         heading attachment ve rendered token budgeting
  tokenization.py  TokenCounter protokolü ve tiktoken adapter'ı
  embeddings.py    boundary/retrieval protokolleri, E5 input ve pooling
  cache.py         disk embedding cache
  features.py      raw 1↔1 cosine semantic shift
  thresholds.py    fixed ve hierarchical adaptive estimator'lar
  selection.py     ortak interval selector, V1/V2 tail resolver'ları
  chunker.py       ortak orchestration ile V1/V2 facade'ları
  cli.py           validate/chunk komutları
```

## Veri akışı

```text
canonical JSONL
  → strict validation
  → heading attachment
  → rendered-token hard split planning
  → cache-aware semantic boundary embedding
  → raw adjacent cosine semantic shift
  → V1 fixed veya V2 hierarchical adaptive candidate set
  → interval semantic+size scoring
  → non-semantic short-tail cleanup
  → exact configured-counter invariant
  → chunks.jsonl + boundaries.jsonl + resolved-config.json
```

## Extension point'ler

- `SemanticThresholdEstimator` protokolü V1 `FixedThresholdEstimator` ile V2 `HierarchicalAdaptiveThresholdEstimator` implementasyonlarını selector'dan ayırır.
- V3, feature extractor'ı multi-scale implementasyonla değiştirebilir; selector `BoundaryEvidence` tüketmeye devam eder.
- V4, selector öncesinde bounded structural assistance ve sonrasında protected resolver ekleyebilir.
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

V1 fixture çıktıları `chunks.jsonl` ve `boundaries.jsonl` için byte-level golden testle korunur. V2 testleri ayrıca median/MAD, sabit `Q75-Q25` IQR, bağımsız quantile clamp, positive-tail, uniform-document degeneracy, short-document fixed fallback, section→parent→document scope çözümü, descendant sample seti, scope-kind provenance, adaptive tail koruması ve V2 CLI routing'i kapsar.

## V2 threshold akışı

1. Bütün heading'ler semantic embedding listesinden çıkarılır; sadece content run'ları embed edilir.
2. Bütün run'lardaki raw boundary feature'ları selection başlamadan önce toplanır.
3. Boundary scope'u komşu `section_path` değerlerinin longest-common-prefix'i olarak hesaplanır.
4. En derin yeterli ve ayırt edilebilir section dağılımı kullanılır; gerekirse parent/document'a çıkılır.
5. Document örneği sekizden azsa `short_document_fixed_fallback` kullanılır; quantile türetilmez.
6. Her boundary kendi local threshold'una göre candidate olur.
7. Ortak interval selector candidate'ları V1 ile aynı raw semantic shift + target-distance skoru üzerinden seçer.

`threshold_scope_kind` boundary JSONL'de bulunduğu için section/parent/document kullanım oranları ek bir runtime metriği eklenmeden hesaplanabilir. Farklı local threshold'lardaki candidate'ların raw shift ile kıyaslanması V2 limitation'ıdır; threshold-relative veya percentile kalite sonraki sürüme bırakılmıştır.

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
```

V1/V2 çıktıları daha sonra seçilmiş 5–10 kritik section'da boundary annotation ile karşılaştırılır. 30–50 gold question/evidence retrieval seti V2–V4 ablation ve ilerideki yerel evaluator için hazırlanır.

## Bilinçli kapsam dışı

- `2↔2`/`3↔3`,
- heading boost/threshold relaxation,
- percentile veya threshold-relative selector scoring,
- heading boost/protected boundary,
- genel cohesion-aware merge,
- retrieval/BM25/RRF/rerank,
- PDF/IDP parsing,
- LLM/API çağrısı,
- production tokenizer uyumluluk iddiası.
