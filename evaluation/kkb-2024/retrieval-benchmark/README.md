# Phase 4 — Retrieval benchmark

Bu dizin, frozen canonical KKB input üzerinde yalnız chunker değişkenini karşılaştıran
development benchmark'ını içerir.

## Frozen girdiler

- Canonical units SHA256:
  `2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5`
- Gold set: `gold-queries.json`
- Gold query sayısı: `50`
- Adaylar: public Legacy `chat_rag` compatibility adapter, V3, A4/V4 ve C3

Gold sorular retrieval çıktıları görülmeden manuel hazırlanmıştır. Her kayıtta soru,
canonical `evidence_unit_ids`, fiziksel `evidence_pages` ve kısa expected answer
bulunur. Bunlar answer-generation metriği değil retrieval evidence ground truth'udur.
İlk sette her soru tek canonical evidence unit'e bağlıdır. Sonuçlar görüldükten sonra
gold'u genişletmek benchmark kontaminasyonu yaratacağından set aynen korunmuştur;
bu nedenle fragmentation metriği bu checkpoint'te çoğunlukla overlap veya aynı
evidence unit'in birden fazla chunk'ta bulunmasını ölçer.

## Sabit retrieval hattı

- Dense: `intfloat/multilingual-e5-base`
- Query prefix: `query: `
- Document prefix: `passage: `
- Uzun input: deterministic sentence fragment + token-weighted pooling
- Sparse: deterministic Unicode BM25 (`k1=1.5`, `b=0.75`)
- Fusion: deterministic equal-weight RRF (`k=60`)
- Query expansion/contextualization/reranker: kapalı
- Token metriği: configured PoC `tiktoken:cl100k_base`

Config ve komut:

```powershell
py -3.11 -m amsc.run_retrieval_benchmark `
  --config configs/retrieval-benchmark-v1.yaml `
  --output evaluation/kkb-2024/retrieval-benchmark/results
```

## Metric semantiği

- `Hit@K`: ilk K chunk içinde en az bir gold evidence unit bulunması.
- `MRR`: ilk evidence-bearing chunk sırasının reciprocal rank'i.
- `Evidence coverage@K`: ilk K chunk'ın kapsadığı gold evidence unit oranı.
- `Evidence fragmentation`: candidate corpus'ta evidence'ı bulunan sorular için,
  gold evidence ile kesişen corpus chunk sayısı. Overlap bu değeri artırabilir.
- `Source evidence coverage`: gold evidence'ın candidate corpus'a hiç girip girmediği;
  retrieval skorundan önceki chunk-source kaybını görünür kılar.
- `Retrieved irrelevant-token ratio`: ilk K chunk tokenlarının, gold evidence unit
  tokenlarına atfedilemeyen yaklaşık oranı.
- Latency: shared no-cache query embedding ile candidate-specific dense + BM25 + RRF
  araması ayrı raporlanır. Soğuk corpus embedding ölçümü ortam bağımlı ayrı kayıttır.

## Yorumlama guardrail'i

C3 boundary `±1 F1=0.6667` bir development sonucudur ve semantic improvement kanıtı
değildir; Phase 3C genuine semantic rescue sayısı `0` kalmıştır. Retrieval sonuçları da
aynı 50 soruluk development checkpoint'iyle sınırlıdır ve holdout doğrulaması değildir.

Legacy satırı KKB production agentic chunker'ı temsil etmez. Public kaynak kodun
canonical parser üzerinde çalışan, farkları açıkça belgelenmiş compatibility adapter'ıdır.
