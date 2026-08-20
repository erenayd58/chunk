# Chunklama PoC

Bu depo, KKB dokümanlarında konu geçişlerini LLM/API çağrısı olmadan bulmayı amaçlayan **Adaptive Multi-Signal Semantic Chunking** PoC'sini içerir.

Nihai çözüm V4'tür; depoda **V1–V4** ve V4 için A0–A4 ablation bileşimleri uygulanmıştır:

- canonical JSONL validation,
- heading exclusion/attachment,
- embedding tokenizer'ından bağımsız `TokenCounter`,
- E5 `query: ` prefix'i ve uzun metinler için fragment pooling,
- cache'li semantic-boundary embedding,
- V1/V2 komşu `1↔1` veya V3/V4 `1↔1`/`2↔2`/`3↔3` semantic shift,
- V1 sabit threshold veya V2/V3/V4 hierarchical adaptive threshold,
- V1–V3 raw-shift veya V4 threshold-relative interval boundary selection,
- parser-agnostic bounded structural support ve semantic-safe small-chunk merge,
- tam render edilmiş metin üzerinde configured-token-counter hard cap,
- açıklanabilir chunk/boundary provenance.

## Kurulum

```powershell
py -3.11 -m pip install -e ".[dev]"
```

Gerçek `multilingual-e5-base` modelini kullanmak için:

```powershell
py -3.11 -m pip install -e ".[model]"
```

Phase 4 retrieval benchmark'ını çalıştırmak için:

```powershell
py -3.11 -m pip install -e ".[benchmark]"
```

Checkpoint evaluation için PDF extraction adapter'ını kullanmak üzere:

```powershell
py -3.11 -m pip install -e ".[checkpoint]"
```

Checkpoint extra'sı `pymupdf4llm[layout]==0.3.4` sürümünü sabitler. Adapter,
`pymupdf.layout` modülünü `pymupdf4llm` paketinden önce yükler ve layout
backend'i gerçekten aktif değilse legacy extraction'a düşmek yerine hata verir.

## Kullanım

```powershell
py -3.11 -m amsc.cli validate `
  --input tests/fixtures/sample.units.jsonl

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

V4 ablation seçenekleri `a1`, `a2`, `a3` ve `a4` değerleridir. `a4` full core
V4 bileşimidir. A5 contextualization bu fazda bilinçli olarak uygulanmamıştır.

Frozen evaluator metriklerini değiştirmeden prediction-level audit üretmek için:

```powershell
py -3.11 -m amsc.failure_analysis `
  --units data/kkb-2024.units.jsonl `
  --annotations evaluation/kkb-2024/checkpoint.annotations.json `
  --run v3=evaluation/kkb-2024/baseline/v3 `
  --run a3=evaluation/kkb-2024/v4-ablation/a3 `
  --run a4=evaluation/kkb-2024/v4-ablation/a4 `
  --output evaluation/kkb-2024/failure-analysis
```

Bu katman authoritative `evaluate_checkpoint()` sonucunu persisted `metrics.json` ile
eşitlik kontrolünden geçirir. Prediction sınıflandırması, HIGH/REVIEW semantiği,
region filtering ve exact/±1 matching değişmez; yalnız ayrı diagnostic JSONL/Markdown
üretilir.

## Phase 3C freeze ve Phase 4 retrieval benchmark

Phase 3C comparator sonucu `phase3c-development-result` etiketiyle dondurulmuştur.
C3'ün boundary `±1 F1=0.6667` sonucu yalnız development bulgusudur; genuine
semantic rescue sayısı `0` kaldığı için semantic improvement olarak yorumlanmaz.

Phase 4, frozen canonical KKB input üzerinde Legacy `chat_rag`, V3, A4/V4 ve C3
chunk'larını aynı retrieval hattıyla karşılaştırır. Gold set, retrieval sonuçları
çalıştırılmadan önce elle hazırlanmış 50 question/evidence kaydı içerir. Query
expansion, contextualization ve reranker kullanılmaz; bütün adaylarda aynı
`multilingual-e5-base`, Unicode BM25 ve deterministic RRF config'i çalışır:

```powershell
py -3.11 -m amsc.run_retrieval_benchmark `
  --config configs/retrieval-benchmark-v1.yaml `
  --output evaluation/kkb-2024/retrieval-benchmark/results
```

Benchmark config'i canonical SHA'yı, public legacy kaynak commit'ini, E5 query ve
document prefix'lerini, BM25/RRF ayarlarını ve frozen aday chunk dosyalarını
sabitler. Retrieval embedding cache'i semantic-boundary cache'inden rol ve dizin
olarak ayrıdır. Query latency ölçümünde query cache kullanılmaz.

Public Legacy karşılaştırması, [MurselTasgin/chat_rag](https://github.com/MurselTasgin/chat_rag)
kodunun frozen canonical input üzerindeki uyumluluk adapter'ıdır; KKB production
agentic chunker'ının birebir reprodüksiyonu değildir. Public sentence packing,
overlap ve kısa-tail düşürme davranışı korunur, fakat canonical parser'ı sabit tutmak
ve generated retrieval header/contextualization eklememek için adapter sınırları
açıkça raporlanır. NLTK English Punkt yerine deterministic punctuation-span
tokenizer kullanılması da pinlenmiş bir compatibility farkıdır.

Üretilen ana çıktılar:

- `summary.json`: Hit@1/3/5, MRR, evidence coverage/fragmentation, irrelevant-token
  ratio ve latency karşılaştırması.
- `query-comparison.jsonl`: soru bazında ilk ilgili sıra ve Hit@K değişimleri.
- Her aday dizinindeki `chunks.jsonl`, `query-results.jsonl` ve `metrics.json`:
  corpus/provenance, deterministik ranking ve ayrıntılı ölçümler.
- `retrieval-benchmark-report.md`: aynı sonuçların human-readable özeti.

Bu benchmark KKB development checkpoint'idir; ikinci belge/holdout olmadan
validated production sonucu değildir.

`chunk` komutu model dosyalarını ilk kullanımda yerel ortama indirir. PDF parsing bu projenin kapsamında değildir; komut hazır canonical IDP/JSONL çıktısı bekler.

## Checkpoint PDF adapter'ı

KKB 2024 Faaliyet Raporu için deterministic checkpoint girdisi seçili fiziksel
sayfalardan üretilebilir:

```powershell
py -3.11 -m amsc.prepare_checkpoint `
  --input kkbfaaliyetraporu2024.pdf `
  --output data/kkb-2024.units.jsonl `
  --pages 40-55 `
  --layout-profile configs/checkpoint-kkb-2024.yaml
```

`--pages` opsiyoneldir; değerler 1-based fiziksel PDF sayfalarıdır ve aralıklar
inclusive'dir. Örneğin `40-55,61,70-72` geçerlidir. Parametre verilmezse bütün
doküman işlenir.

Adapter `page_chunks=True`, `header=False`, `footer=False` ve
`force_ocr=False` ile PyMuPDF4LLM layout extraction kullanır. Landscape
fiziksel sayfalar deterministic olarak sol ve sağ mantıksal sayfalara ayrılır;
extraction sırası `left_then_right` olur. Bu spread-aware crop, dört sütunlu
faaliyet raporu spread'lerinde bir paragrafın bir sonraki sütundaki devamının
araya başka sütunlar girmeden gelmesini sağlar. KKB checkpoint profile ayrıca
her mantıksal sayfada `logical_columns=2` ve
`reading_order=column-major-left-to-right` politikasını explicit olarak uygular;
kolon sayısı otomatik tahmin edilmez. `page_boxes` logical bbox'ları iki kolona
atanır, her dikey bantta önce sol sonra sağ kolon `y` sırasıyla okunur. İki
kolonu kesen full-width box'lar kendi dikey konumlarında bant ayırıcı olarak
korunur. Markdown `pos` değerleri yalnız exact metin dilimini almak için
kullanılır, reading-order kaynağı değildir. Heading için adapter-side bir
heuristic uygulanmaz; heading tipi yine layout Markdown'ındaki `#` işaretinden
gelir.

Üretilen Markdown heading, paragraph, list ve table atomlarına ayrılır;
PyMuPDF4LLM page chunk'ları final semantic chunk olarak kullanılmaz. V1/V2/V3
daha sonra boundary kararlarını kendileri verir.

`page_boxes.class == "picture"` bölgeleri normal Markdown paragraph'larına
parçalanmaz. Her picture bölgesi canonical şemayı genişletmeden `paragraph`
olarak map edilen tek bir `v-xxxxx` visual-content unit olur. `Start of picture
text` ile `End of picture text` arasındaki layout text tek textual surrogate'a
dönüştürülür; `<br>` yalnız satır sonuna çevrilir ve sayısal metin yeniden
yorumlanmaz. `picture intentionally omitted` placeholder'ı semantic içeriğe
alınmaz. Layout text bulunmayan dekoratif görseller canonical semantic JSONL'e
unit üretmez; visual provenance sidecar'da `canonical_unit_id=null` olarak
korunur. OCR force edilmez ve caption/LLM üretilmez.

Canonical JSONL'nin yanında aynı basename ile `.manifest.json` ve
`.visual-provenance.jsonl` üretilir.
Manifest source PDF SHA256, PyMuPDF4LLM sürümü, seçili sayfalar, page-number
semantiği ve extraction parametrelerini taşır.

Visual provenance sidecar her picture için canonical unit ID, raw extracted
picture text, physical page, logical page side, physical-page bbox,
`raw_layout_class=picture`, `content_origin=visual` ve
`extraction_method=layout_text` alanlarını taşır. Böylece canonical unit
V1/V2/V3 tarafından text olarak tüketilirken kayıpsız extraction provenance'ı
ayrı tutulur.

Canonical `source.page` ve `source.physical_page` 1-based fiziksel PDF
sayfasıdır. `source.logical_page_side`, landscape spread için `left`/`right`,
diğer sayfalar için `single` değeridir. `source.block` gerçek
bir PyMuPDF layout block ID'si değildir; her sayfada Markdown atomization
sonrasında 1'den başlayan adapter-local atomic block sırasıdır. Bbox veya layout
identity provenance'ı olarak yorumlanmamalıdır. Yalnız visual-content
unit'lerinde `source.picture_bbox`, fiziksel PDF sayfasının koordinatlarını
taşır. Explicit profile çıktısında `source.layout_bbox_logical`,
`source.layout_bbox_physical`, `source.layout_box_index`, `source.logical_column`,
`source.layout_band` ve `source.layout_reading_order_index` alanları bbox tabanlı
checkpoint sıralamasını denetlenebilir kılar. Bunlar production layout identity
garantisi değildir.

Human-readable checkpoint QA preview üretmek için:

```powershell
py -3.11 -m amsc.checkpoint_qa `
  --input artifacts/checkpoint-smoke/kkb-2024.pages-40-42.units.jsonl `
  --output artifacts/checkpoint-smoke/kkb-2024.pages-40-42.qa-preview.md
```

QA özeti `canonical_order_integrity` altında yalnız `1..N` canonical order
bütünlüğünü kontrol eder. Bbox tabanlı column-major uygunluğu ve kısa/yarım
biten paragraf manuel inceleme adayları ayrı `layout_reading_order_review`
alanında raporlanır.

Bu adapter yalnız V1/V2/V3/V4 checkpoint evaluation girdisi içindir; final
production parser/IDP implementasyonu değildir.

## Token limiti notu

V1'de `hard_max_tokens=1126`, varsayılan `tiktoken:cl100k_base` sayacına göre uygulanır. KKB production limitinin hangi tokenizer'a göre tanımlandığı bilinmediğinden bu, **production-tokenizer uyumluluk garantisi değildir**. Çıktı bu durumu `hard_cap_semantics=configured_poc_counter_only` alanıyla açıkça taşır.

`160/700/900`, `fixed_threshold=0.20`, adaptive MAD/quantile/minimum-sample ayarları, `short_document_fallback_threshold=0.20`, V3 `0.35/0.26/0.39` scale ağırlıkları ve `0.80/0.20` seçim ağırlıkları optimize edilmiş değerler değil, PoC başlangıç parametreleridir.

## Dokümanlar

- [Bağlam ve kararlar](docs/kararlar-ve-baglam.md)
- [Seçilen çözüm](docs/secilen-cozum.md)
- [V1/V2/V3 implementasyon planı ve mimarisi](docs/implementasyon-plani.md)

## Test

```powershell
py -3.11 -m pytest
```

Testler model indirmeden deterministic backend/tokenizer doubles kullanır. Gerçek `cl100k_base` sayacı ayrıca unit test kapsamındadır.
