# Seçilen Çözüm: Adaptive Multi-Signal Semantic Chunking

## Durum

Seçilen nihai yaklaşım Adaptive Multi-Signal Semantic Chunking olarak korunmaktadır. Uygulama bilinçli biçimde aşamalıdır:

| Sürüm | İçerik | Durum |
|---|---|---|
| V1 | `1↔1` cosine, fixed threshold, interval selector, token kısıtları | Uygulandı |
| V2 | Section/document adaptive semantic threshold | Uygulanmadı |
| V3 | `1↔1`, `2↔2`, `3↔3` multi-scale semantic shift | Uygulanmadı |
| V4 | Bounded heading assistance, protected boundary ve güvenli tail/merge | Uygulanmadı |

V1 üretim çözümü değil; final algoritmanın veri sözleşmesi, embedding, seçim ve provenance temellerini doğrulayan PoC basamağıdır.

## Girdi ve semantic unit

Parser/IDP çıktısı hazır kabul edilir. Canonical JSONL'de her satır sıralı bir unit taşır:

```json
{
  "document_id": "kkb-2024",
  "unit_id": "u-001",
  "order": 1,
  "text": "...",
  "type": "heading|paragraph|list|table",
  "heading_level": 2,
  "section_path": ["İnsan Kaynakları"],
  "source": {"page": 84, "block": 3}
}
```

Temel semantic unit paragraf/list/table içerik bloğudur. Heading unit'leri:

- semantic embedding listesine girmez,
- takip eden content unit'e bağlanır,
- chunk metninde content'ten önce render edilir,
- `section_path` ve source provenance içinde korunur.

Temel unit zaten paragraf olduğu için sabit `paragraph_signal` yoktur. V4'te yalnızca oversized-paragraph fragment sınırları için intra-paragraph cezası kullanılacaktır.

## Ayrı token ve embedding sorumlulukları

Chunk boyutu `TokenCounter` ile hesaplanır. Boundary embedding modelinin tokenizer'ı yalnızca model-input hazırlamada kullanılır.

V1 varsayılanı:

```text
TokenCounter = tiktoken:cl100k_base
hard_max_tokens = 1126
hard_cap_semantics = configured_poc_counter_only
```

Bu, KKB production tokenizer'ına göre 1126 garantisi değildir. Production tokenizer öğrenildiğinde `TokenCounter` değiştirilmelidir.

`SemanticBoundaryEmbedder` ve `RetrievalEmbedder` kavramsal olarak ayrı protokollerdir. V1 yalnızca boundary embedder'ı kullanır. Gelecekte aynı model ağırlıkları kullanılsa bile cache namespace, prefix politikası ve evaluator config'i ayrı kalır.

## E5 input politikası

`intfloat/multilingual-e5-base` model kartı symmetric semantic similarity görevlerinde `query: ` prefix'ini önerir ve uzun girdilerin en fazla 512 model-token seviyesinde truncate edildiğini belirtir. V1 sessiz truncation'a izin vermez: [Multilingual E5 model kartı](https://huggingface.co/intfloat/multilingual-e5-base/blob/main/README.md).

```text
prefix_policy = symmetric_query
prefix = "query: "
model_input_limit = tokenizer.model_max_length
```

Limit aşılırsa:

1. Metin deterministik cümle fragment'larına ayrılır.
2. Cümleler prefix ve special tokenlar dahil limite göre paketlenir.
3. Tek cümle hâlâ uzunsa model tokenizer token pencerelerine ayrılır.
4. Her fragment aynı `query: ` prefix'iyle embed edilir.
5. Vektörler prefix hariç model-token sayısıyla ağırlıklı ortalanır ve L2-normalize edilir.

Provenance; prefix politikasını, model input limitini, fragment sayısını ve `token_weighted_mean` pooling bilgisini taşır. Cache anahtarı bunların tamamını içerir.
Metin bileşeni için whitespace normalizasyonu yapılmaz; hash, `embed_units` çağrısına verilen semantic text'in UTF-8 içeriği üzerinden doğrudan hesaplanır. Böylece boşluk ve satır sonu farkları ayrı cache kayıtları üretir.

## Heading-aware rendered token bütçesi

Heading embed edilmese de chunk metninin parçasıdır. Bu nedenle içerik split'i şu bütçeyle başlar:

```text
available_content_budget =
    hard_max_tokens
  - leading_heading_tokens
  - render_separator_tokens
```

Asıl karar, tam render edilmiş metnin configured `TokenCounter` ile sayımına göre verilir. Tokenizasyon toplamsal olmayabileceği için ilk tahminden sonra fragment deterministik biçimde küçültülür. Boundary selector da aday boyutunu unit-token toplamıyla değil, tam render edilmiş aday metniyle hesaplar.

Heading yalnızca ilk content fragment'ında render edilir. Sonraki fragment'lar section metadata'sını taşır fakat heading metnini tekrar etmez. Tek başına hard cap'i aşan heading, provenance'ı korunarak token fragment'larına bölünür.

## V1 semantic boundary ve seçim

Komşu content unit'ler için:

```text
semantic_shift(b) = (1 - cosine(E_b, E_(b+1))) / 2
semantic_candidate(b) = semantic_shift(b) >= fixed_threshold
```

Selector ilk threshold geçen boundary'yi seçmez. Chunk başlangıcından itibaren `[min_tokens, soft_max_tokens]` aralığındaki bütün boundary'leri değerlendirir:

```text
tokens <= target:
  target_distance = (target - tokens) / (target - min)

tokens > target:
  target_distance = (tokens - target) / (soft_max - target)

selection_score =
    0.80 × semantic_shift
  + 0.20 × (1 - target_distance)
```

Semantic candidate'lar içinden en yüksek skor seçilir. Aday yoksa soft max aşılacağı zaman `size_fallback`; güvenli soft boundary yoksa `hard_limit_fallback` kullanılır. Son karar her zaman tam render edilmiş metin üzerinde doğrulanır.

V1 tail kuralı yalnızca final chunk `min_tokens` altında kaldığında çalışır. Aradaki boundary `size_fallback`/`hard_limit_fallback` ve non-semantic ise, birleşik metin configured hard cap'i aşmamak koşuluyla kaldırılır. Gerçek semantic boundary hiçbir durumda tail uğruna kaldırılmaz. Genel cohesion-aware merge V4'e aittir.

## Başlangıç parametreleri

```text
fixed_threshold = 0.20
min_tokens = 160
target_tokens = 700
soft_max_tokens = 900
hard_max_tokens = 1126
semantic_weight = 0.80
size_weight = 0.20
```

Bu değerler optimize edilmiş parametreler değildir. `configs/v1.yaml` ve çıktı `parameter_status=poc_initial_not_optimized` alanı bunu açıkça belirtir. V2'de kullanılacak MAD lambda da başlangıç parametresi olarak ele alınacaktır.

## Açıklanabilir çıktı

Her chunk şunları taşır:

- raw ve prepared unit kimlikleri,
- sayfa/blok source spans,
- exact configured-counter token sayısı,
- start/end boundary nedeni,
- cosine, semantic shift, threshold ve selection score,
- boundary model/prefix/input-limit bilgisi,
- semantic fragment/pooling/cache provenance,
- token counter kimliği ve hard-cap semantics,
- algoritma sürümü ve config hash.

## V2–V4 tasarım yönü

V2'de threshold yalnızca semantic dağılımdan üretilecektir. Yeterli örneği olan en derin ortak section kullanılacak; veri yetersizse parent ve document fallback uygulanacaktır. Heading, final-score dağılımına katılmak yerine semantic threshold'u sınırlı ölçüde gevşeten ikinci aşama sinyal olacaktır.

V3, heading'leri dışarıda tutarak `1↔1`, `2↔2`, `3↔3` pencerelerini ve tüm scale provenance'ını ekleyecektir.

V4, heading-assisted sınırları, yüksek güvenli protected boundary'leri, intra-paragraph penalty'yi ve protected/section boundary'leri bozmayan küçük-parça çözümünü ekleyecektir.

## Değerlendirme

- Gold boundary annotation tüm faaliyet raporu için zorunlu değildir; 5–10 kritik bölüm yeterlidir.
- Retrieval değerlendirmesi için 30–50 gold question/evidence hedeflenir.
- V1'de retrieval evaluator, BM25/RRF, rerank ve Langfuse entegrasyonu yoktur.
- PDF/IDP parsing ve chunk sınırı için LLM/API çağrısı kapsam dışıdır.
