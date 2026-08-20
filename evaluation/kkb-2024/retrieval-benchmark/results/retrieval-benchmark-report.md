# Phase 4 — KKB Retrieval Benchmark

Bu development benchmark'ında parser/input ve retrieval hattı sabittir; yalnız chunker değişir.
Query expansion, contextualization ve reranker kapalıdır. Dense retrieval, BM25 ve deterministic RRF tüm adaylarda aynıdır.

| Chunker | Chunks | Hit@1 | Hit@3 | Hit@5 | MRR | Evidence coverage@5 | Source coverage | Fragmentation* | Irrelevant tokens@5 | Search p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Legacy chat_rag | 244 | 0.2600 | 0.3800 | 0.4000 | 0.3183 | 0.4000 | 0.5800 | 1.138 | 0.9745 | 0.856 |
| V3 | 244 | 0.5400 | 0.6800 | 0.8000 | 0.6280 | 0.8000 | 1.0000 | 1.000 | 0.9552 | 1.154 |
| A4 / V4 | 244 | 0.5400 | 0.7000 | 0.7800 | 0.6257 | 0.7800 | 1.0000 | 1.000 | 0.9559 | 0.778 |
| C3 | 239 | 0.5400 | 0.7400 | 0.8200 | 0.6413 | 0.8200 | 1.0000 | 1.000 | 0.9551 | 0.540 |

`Fragmentation*` yalnız gold evidence'ı candidate corpus'ta bulunan sorular üzerinde hesaplanır.
Bu ilk gold sette her soru tek canonical evidence unit'e bağlıdır; bu nedenle evidence coverage Hit@K ile aynı, fragmentation ise ağırlıkla overlap/duplicate-fragment etkisini gösterir.

## Query-level farklar

- C3'ün V3'e göre Hit@5 kazandığı sorular: q012, q036, q037
- C3'ün V3'e göre Hit@5 kaybettiği sorular: q001, q024
- V4'ün V3'e göre Hit@5 kazandığı sorular: yok
- V4'ün V3'e göre Hit@5 kaybettiği sorular: q017

## Yorumlama sınırı

C3 boundary ±1 F1=0.6667 is a development result, not evidence of semantic improvement; Phase 3C genuine semantic rescue count remained 0.
C3'ün `0.6667` boundary F1 değeri semantic improvement olarak yorumlanamaz; genuine semantic rescue sayısı `0` olarak kalmıştır.

Legacy satırı KKB production agentic chunker değildir. Public `MurselTasgin/chat_rag` kodunun pinlenmiş code-default davranışını frozen canonical input üzerinde çalıştıran compatibility adapter'dır.
Public legacy akışının kısa section'ları düşürme davranışı frozen canonical heading'lerle birlikte evidence kaybı üretmiştir. Bu nedenle legacy retrieval skoru production KKB legacy sistemine genellenemez.

## Metric tanımları

- `Hit@K`: İlk K sonuçta en az bir gold evidence unit bulunan soru oranı.
- `MRR`: İlk evidence-bearing chunk sırasının reciprocal rank ortalaması.
- `Evidence coverage@K`: İlk K sonuçta kapsanan gold evidence unit oranı.
- `Fragmentation`: Gold evidence ile kesişen corpus chunk sayısının soru başına ortalaması; overlap da bu değeri artırır.
- `Irrelevant tokens@K`: İlk K chunk tokenlarından gold evidence unit tokenlarına atfedilemeyen kısmın oranı.
- Latency: Query embedding ortak olarak bir kez ölçülür; tabloda candidate-specific dense+BM25+RRF arama medyanı gösterilir.

Bu veri seti KKB development checkpoint'idir; sonuçlar ikinci doküman/holdout olmadan validated production sonucu değildir.
