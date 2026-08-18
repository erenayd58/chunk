# V1 Implementasyon Mimarisi

## Modüller

```text
src/amsc/
  models.py        canonical ve çıktı modelleri
  config.py        strict V1 YAML config
  io.py            JSONL validation ve çıktı writer
  units.py         heading attachment ve rendered token budgeting
  tokenization.py  TokenCounter protokolü ve tiktoken adapter'ı
  embeddings.py    boundary/retrieval protokolleri, E5 input ve pooling
  cache.py         disk embedding cache
  features.py      1↔1 cosine semantic shift
  selection.py     interval selector ve V1 tail resolver
  chunker.py       V1 orchestration ve provenance
  cli.py           validate/chunk komutları
```

## Veri akışı

```text
canonical JSONL
  → strict validation
  → heading attachment
  → rendered-token hard split planning
  → cache-aware semantic boundary embedding
  → adjacent cosine semantic shift
  → fixed-threshold candidate set
  → interval semantic+size scoring
  → non-semantic short-tail cleanup
  → exact configured-counter invariant
  → chunks.jsonl + boundaries.jsonl + resolved-config.json
```

## Extension point'ler

- V2, `AdjacentSemanticFeatureExtractor` çıktısına dokunmadan yeni bir threshold estimator ekleyebilir.
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

## 2024 faaliyet raporu

Depodaki PDF doğrudan işlenmez. IDP/parser çıktısı aşağıdaki dosyaya normalize edildikten sonra:

```powershell
py -3.11 -m amsc.cli validate --input data/kkb-2024.units.jsonl

py -3.11 -m amsc.cli chunk `
  --input data/kkb-2024.units.jsonl `
  --config configs/v1.yaml `
  --output artifacts/kkb-2024-v1
```

V1 çıktısı daha sonra seçilmiş 5–10 kritik section'da boundary annotation ile incelenir. 30–50 gold question/evidence retrieval seti V2–V4 ablation ve ilerideki yerel evaluator için hazırlanır.

## Bilinçli kapsam dışı

- adaptive/MAD ve section threshold,
- `2↔2`/`3↔3`,
- heading boost/protected boundary,
- genel cohesion-aware merge,
- retrieval/BM25/RRF/rerank,
- PDF/IDP parsing,
- LLM/API çağrısı,
- production tokenizer uyumluluk iddiası.
