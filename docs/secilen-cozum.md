# Seçilen Çözüm: Adaptive Multi-Signal Semantic Chunking

## Durum

Seçilen nihai yaklaşım Adaptive Multi-Signal Semantic Chunking olarak korunmaktadır. Uygulama bilinçli biçimde aşamalıdır:

| Sürüm | İçerik | Durum |
|---|---|---|
| V1 | `1↔1` cosine, fixed threshold, interval selector, token kısıtları | Uygulandı |
| V2 | Hierarchical section/parent/document adaptive semantic threshold | Uygulandı |
| V3 | `1↔1`, `2↔2`, `3↔3` multi-scale semantic shift | Uygulandı |
| V4 | Bounded heading assistance, protected boundary ve güvenli tail/merge | Uygulanmadı |

V1, V2 ve V3 üretim çözümü değildir; final algoritmanın veri sözleşmesi, embedding, seçim ve provenance temellerini doğrulayan PoC basamaklarıdır.

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

## V2 hierarchical adaptive threshold

V2'nin V1'den tek algoritmik farkı semantic candidate üretimidir. `1↔1` cosine, exact-text embedding cache, heading exclusion, token politikası, interval selector skoru ve fallback/tail davranışı korunur.

Her boundary'nin başlangıç scope'u komşu content unit'lerin `section_path` değerlerinin en uzun ortak prefix'idir. Threshold'lar selection başlamadan önce dokümandaki bütün semantic boundary'lerden hazırlanır. Bir scope'un örnekleri, o scope ve tüm descendant scope'lardaki boundary'leri içerir. Çözümleme en derin section'dan parent section'lara, ardından document dağılımına çıkar.

Yeterli örnekte robust hesap:

```text
median = median(S)
mad = median(abs(S - median))
robust_scale = 1.4826 × mad

MAD yetersizse:
  robust_scale = (Q75 - Q25) / 1.349

raw_threshold = median + mad_lambda × robust_scale
threshold = min(Q90, max(Q75, raw_threshold))
```

IQR her zaman gerçek `Q75 - Q25` değeridir. Config'teki `quantile_floor` ve `quantile_ceiling` yalnızca son threshold clamp quantile'larını belirler; dispersion hesabını değiştirmez. Provenance yöntemi kullanılan scale'e göre `mad_quantile` veya `iqr_quantile` olarak ayrılır.

MAD ve IQR sıfır olup positive tail varsa en küçük median-üstü değer kullanılır. Tamamen eşit section dağılımı parent'a çıkar; yeterli örnekli tamamen eşit document dağılımı semantic candidate üretmez.

Document boundary sayısı `min_document_boundaries=8` değerinin altındaysa Q75 gibi veri-türetilmiş bir eşik kullanılmaz. Açık PoC parametresi `short_document_fallback_threshold=0.20` uygulanır ve provenance şunları taşır:

```text
method = short_document_fixed_fallback
low_confidence = true
threshold_scope_kind = document
```

Normal scope provenance'ında threshold, scope, sample count, median/MAD/scale/quantile değerleri, yöntem ve `threshold_scope_kind=section|parent_section|document` bulunur. V2 semantic chunk sınırı `adaptive_semantic_boundary` olarak işaretlenir.

Selector V2'de bilinçli olarak değiştirilmemiştir:

```text
selection_score =
    0.80 × raw_semantic_shift
  + 0.20 × (1 - target_distance)
```

Farklı local threshold'lardan gelen candidate'ların raw semantic shift ile karşılaştırılması V2'nin bilinen limitation'ıdır. Percentile, threshold-relative margin veya normalize boundary quality sonraki sürüme bırakılmıştır.

## V3 multi-scale semantic context

V3'ün V2'den tek algoritmik farkı `semantic_shift` hesabıdır. Her boundary için semantic run sınırları içinde full-symmetric olarak bulunabilen `1↔1`, `2↔2` ve `3↔3` pencereleri hesaplanır. Heading-only unit'ler window girdisi değildir ve attached heading metni token ağırlığına katılmaz.

Window embedding, mevcut cache'li content-unit embedding'lerinden üretilir; yeni embedding çağrısı yapılmaz:

```text
unit_weight_i = sqrt(configured_token_counter.count(unit.text_for_embedding))

pooled_window = L2_normalize(
  Σ(unit_weight_i × L2_normalize(unit_embedding_i))
  / Σ(unit_weight_i)
)
```

Her available scale için `shift_k=(1-cosine_k)/2` hesaplanır. Birleşik shift, yalnızca available scale ağırlıklarının yeniden normalize edildiği weighted mean'dir:

```text
base_weights = {1: 0.35, 2: 0.26, 3: 0.39}

effective_weight_k =
  base_weight_k / Σ(base_weight_j for j in available_scales)

semantic_shift =
  Σ(effective_weight_k × shift_k for k in available_scales)
```

Provenance; `shift_1/2/3`, `available_scales`, `scale_count`, effective ağırlıklar, pooling politikası ve token counter kimliğini taşır. Top-level `cosine_similarity` gerçek `1↔1` cosine değeridir; top-level `semantic_shift` birleşik weighted mean'dir.

V3'ün bilinen limitation'ı, `[1]`, `[1,2]` ve `[1,2,3]` gibi farklı available-scale bileşimlerinden gelen shift değerlerinin aynı hierarchical adaptive threshold dağılımında birlikte değerlendirilmesidir. V3 bu fark için ayrı threshold, scale-composition normalization, percentile düzeltmesi veya edge calibration uygulamaz. `available_scales` ve `scale_count` sonraki analizler için korunur.

## Başlangıç parametreleri

```text
fixed_threshold = 0.20
V2 mad_lambda = 1.5
V2 min_section_boundaries = 20
V2 min_document_boundaries = 8
V2 short_document_fallback_threshold = 0.20
V3 shift weights = 0.35 / 0.26 / 0.39
min_tokens = 160
target_tokens = 700
soft_max_tokens = 900
hard_max_tokens = 1126
semantic_weight = 0.80
size_weight = 0.20
```

Bu değerler optimize edilmiş parametreler değildir. `configs/v1.yaml`, `configs/v2.yaml`, `configs/v3.yaml` ve çıktı `parameter_status=poc_initial_not_optimized` alanı bunu açıkça belirtir.

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

## V4 tasarım yönü

V4, heading-assisted sınırları, yüksek güvenli protected boundary'leri, intra-paragraph penalty'yi ve protected/section boundary'leri bozmayan küçük-parça çözümünü ekleyecektir.

## Değerlendirme

- Gold boundary annotation tüm faaliyet raporu için zorunlu değildir; 5–10 kritik bölüm yeterlidir.
- Retrieval değerlendirmesi için 30–50 gold question/evidence hedeflenir.
- V1/V2/V3'te retrieval evaluator, BM25/RRF, rerank ve Langfuse entegrasyonu yoktur.
- PDF/IDP parsing ve chunk sınırı için LLM/API çağrısı kapsam dışıdır.
