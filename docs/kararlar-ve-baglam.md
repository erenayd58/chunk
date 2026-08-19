# Sohbetten Aktarılan Bağlam ve Kararlar

Bu belge, **“Chunklama PoC Planı”** başlıklı referans sohbetten (`6a841269-93cc-83ed-a9f4-cafd0d69458a`) projeye aktarılan bilgilerin karar kaydıdır. Tam konuşma dökümü yerine, uygulamayı etkileyen doğrulanmış kullanıcı bilgileri ile alınan tasarım kararları özetlenmiştir.

## Problem tanımı

Mevcut chunk sınırları her zaman anlam sınırlarıyla örtüşmüyor. Bunun sonucunda konu bütünlüğü bozulabiliyor ve retrieval katmanına yanlış ya da eksik bağlam taşıyan chunk'lar gelebiliyor.

PoC'nin çözmesi gereken soru şudur:

> Mevcut cosine tabanlı semantic-momentum yaklaşımının kaçırdığı veya yanlış ürettiği sınırları, LLM kullanmadan, daha geniş bağlamı ve doküman yapısını birlikte değerlendirerek daha doğru bulabilir miyiz?

## Bilinen mevcut sistem bağlamı

Referans sohbette paylaşılan şirket içi bilgilere göre:

- Girdiler arasında PDF, DOCX, XLS/XLSX, PPT/PPTX, HTML/HTM, URL, TXT, Markdown, XML, JSON ve CSV bulunuyor.
- Parser kaynağı genel olarak IDP; başlık, alt başlık, paragraf, liste ve tablo gibi yapılar metadata olarak korunuyor.
- Mevcut chunklama hibrit: agentic/semantic-momentum, heading, paragraf, token ve recursive karakter kuralları birlikte kullanılıyor.
- Semantic momentum embedding cosine similarity'sine dayanıyor; dolayısıyla yalnızca komşu cosine + sabit eşik çözümü mevcut yaklaşımı tekrar eder.
- Sohbette aktarılan mevcut sınırlar: `soft_max_tokens = 1126`, recursive `chunk_size = 2048` karakter ve `chunk_overlap = 128` karakter.
- Chunk üretiminden sonra embedding sağlayıcısı pluggable yapıdadır ve model seçimi yönetim katmanından değiştirilebilir.
- Retrieval hattında semantic search, BM25, RRF fusion ve rerank birlikte kullanılıyor.
- İçerik Türkçe ağırlıklı, az miktarda İngilizce doküman mevcut.
- Hazır bir soru-cevap benchmark'ı yok; gözlem için Langfuse kullanılıyor.
- İlk PoC dokümanı 2024 faaliyet raporu olacak.

Bu maddeler depo içindeki koddan doğrulanmış sabitler değil, referans sohbette aktarılan sistem bilgisidir. Entegrasyon öncesinde gerçek konfigürasyon ve veri sözleşmeleriyle tekrar doğrulanmalıdır.

## Alınan karar

Seçilen nihai yaklaşım:

> **Adaptive Multi-Signal Semantic Chunking:** Dokümanın kendi anlamsal dağılımına adapte olan; komşu ve çok ölçekli pencere embedding değişimini sınırlı heading desteğiyle birleştiren; configured-token-counter sınırları ve korumalı küçük-parça çözümü uygulayan LLM'siz chunklama.

Bu seçim dört ana iyileştirmeyi tek çözümde toplar:

1. Sabit cosine eşiği yerine doküman dağılımından üretilen adaptif eşik.
2. Yalnızca iki komşu birim yerine `1↔1`, `2↔2` ve `3↔3` bağlam pencereleri.
3. Heading sınırlarını hard rule olarak değil, semantik eşiğe yakın sınırları sınırlı biçimde destekleyen sinyal olarak kullanma. Temel birim paragraf olduğu için sabit `paragraph_signal` kullanılmaz; yalnızca uzun paragraf fallback fragment'larında intra-paragraph cezası uygulanır.
4. Türkçe ağırlıklı içeriğe uygun embedding modelini ablation ile seçme; model seçimini algoritmik yenilik olarak sunmama.

## Kapsam dışı

- PDF/DOCX parsing kalitesini iyileştirmek.
- Her sınır için LLM/API çağırmak.
- Üretimdeki mevcut sistemi birebir yeniden kurmak.
- İlk sürümde change-point detection gibi ayrı bir araştırma motoru geliştirmek.
- Baştan sona RAG veya reranker tasarımını değiştirmek.

Change-point detection, ana çözüm sonuçlandıktan sonra deneysel bir sonraki faz adayıdır.

## Başarı yorumu

Şirket mevcut sistemi zaten bildiği için PoC'de üretim chunker'ını kopyalayan kapsamlı bir eski/yeni karşılaştırması gerekmiyor. Bunun yerine seçilen çözüm:

- gerçek doküman üzerinde sınır örnekleriyle,
- küçük bir gold evidence soru setiyle,
- sınır, bütünlük, boyut ve retrieval metrikleriyle,
- çözüm bileşenlerinin ablation sonuçlarıyla

kanıtlanacaktır.

## Açık entegrasyon noktaları

Aşağıdakiler tasarımın önünü kesmez, fakat gerçek entegrasyondan önce netleştirilmelidir:

- IDP çıktısının kesin şeması ve unit türleri.
- Üretim tokenizer'ı ve 1126 token değerinin soft/hard davranışı.
- Kullanılacak onaylı embedding modeli ve çalışma ortamı.
- Top-K ve rerank ayarları.
- Tablo/listelerin atomic unit olarak nasıl temsil edildiği.

## V1 uygulama kararları

- Semantic-boundary embedding ile gelecekteki retrieval embedding ayrı arayüzlerdir; ilk PoC aynı underlying modeli kullanabilse de evaluator boundary modeline bağlanmaz.
- Chunk token sayımı embedding tokenizer'ından bağımsız `TokenCounter` üzerinden yapılır.
- V1 varsayılanı `tiktoken:cl100k_base` ve `hard_max_tokens=1126` değeridir. KKB production limitinin gerçek tokenizer'ı bilinmediği için garanti yalnızca configured PoC sayacına göredir.
- `multilingual-e5-base` symmetric semantic similarity girdileri `query: ` prefix'iyle hazırlanır. 512 model-token sınırını aşan birimler sessizce truncate edilmez; deterministik sentence fragment + token-weighted pooling uygulanır.
- `160/700/900`, sabit threshold ve skor ağırlıkları optimize edilmiş üretim değerleri değil, PoC başlangıç parametreleridir. Gelecekteki `mad_lambda` için de aynı durum geçerlidir.
- Gold boundary annotation tüm dokümana zorunlu değildir; 5–10 kritik bölüm yeterlidir. Retrieval değerlendirmesinde 30–50 gold question/evidence hedefi korunur.

## V2 uygulama kararları

- V1 davranışı dondurulmuştur; V2'nin tek algoritmik farkı fixed semantic threshold yerine hierarchical adaptive threshold'dur.
- Threshold scope'u komşu content unit'lerin `section_path` longest-common-prefix'idir. Yeterli örnek yoksa en derin section'dan parent'a ve document'a çıkılır; parent sample setleri descendant boundary'leri kapsar.
- `min_section_boundaries=20`, `min_document_boundaries=8`, `mad_lambda=1.5`, quantile sınırları ve `short_document_fallback_threshold=0.20` optimize edilmiş değerler değil PoC başlangıç parametreleridir.
- Sekizden az document boundary'sinde Q75 kullanılmaz; sabit short-document fallback uygulanır ve `method=short_document_fixed_fallback`, `low_confidence=true` yazılır.
- `threshold_scope_kind=section|parent_section|document`, scope kullanım oranlarının boundary JSONL üzerinden raporlanabilmesi için korunur.
- Selector skoru değiştirilmemiştir. Farklı local threshold'lardaki candidate'ların raw semantic shift ile kıyaslanması bilinen V2 limitation'ıdır; percentile/threshold-relative kalite sonraki sürüme bırakılmıştır.
- `2↔2`/`3↔3`, heading boost, protected boundary, cohesion-aware merge ve retrieval evaluator V2 kapsamında değildir.

## V3 uygulama kararları

- V2 davranışı `v2-adaptive-threshold` olarak dondurulmuştur; V3'ün tek algoritmik farkı semantic shift hesabının `1↔1`, `2↔2`, `3↔3` multi-scale weighted mean olmasıdır.
- Scale-k yalnızca boundary'nin iki tarafında da aynı semantic run içinde tam k content unit varsa hesaplanır. Kısaltılmış/asimetrik window kullanılmaz.
- Window pooling, heading'siz exact semantic text'in configured PoC `TokenCounter` sayımından `sqrt(token_count)` ağırlığı üretir. Unit ve pooled window vektörleri L2-normalize edilir.
- `0.35/0.26/0.39` scale ağırlıkları optimize edilmiş değerler değildir. Yalnızca available scale'ler üzerinde toplamları bir olacak şekilde yeniden normalize edilir.
- `shift_1/2/3`, `available_scales`, `scale_count` ve effective ağırlıklar boundary provenance'ında saklanır. Top-level cosine `1↔1`, top-level shift birleşik değerdir.
- Hierarchical adaptive estimator, selector, token policy, heading exclusion, E5/cache ve adaptive tail resolver V2 ile aynıdır.
- Farklı available-scale bileşimlerinden üretilen shift'lerin aynı adaptive threshold dağılımında değerlendirilmesi bilinen V3 limitation'ıdır. Ayrı threshold veya ek normalizasyon uygulanmaz.
- Heading boost, structural relaxation, protected boundary, percentile selector, cohesion-aware merge ve retrieval evaluator V3 kapsamında değildir.

## V4 uygulama kararları

- Canonical KKB input, gold annotations ve V3 golden çıktıları V4 öncesinde freeze edilmiştir. V4 parser/checkpoint adapter davranışını veya V1/V2/V3 orchestration'ını değiştirmez.
- Structural evidence parser-agnostic ve soft'tur. Heading attachment identity, `section_path` geçişi ve table/list/visual atomic türü kanıt sağlar; generic heading hiçbir zaman protected veya mandatory boundary olmaz.
- Bounded relaxation `max_threshold_relaxation=0.04` ve `semantic_floor=0.12` PoC başlangıç değerleriyle uygulanır. Original threshold semantic floor'un altındaysa threshold daha da düşürülmez.
- Selector `effective_boundary_strength` kullanır. Merge cohesion ve high-confidence guard ise structure'dan bağımsız `original_adaptive_threshold` ve `original_boundary_strength` kullanır.
- Merge yalnız adjacent ve small-chunk-focused adaylarda, retained unit embedding'lerinden token-sqrt pooled cosine ile tek non-overlapping pass olarak çalışır. Original `hard_limit_fallback` boundary merge eligible değildir. Proposal sırası absolute cohesion margin → original strength → target distance → focus index → left direction → final structural tie-break'tir. Structure eligibility veto değildir.
- Atomic table/list/visual unit tek başına configured hard cap'i aşarsa atomiclik hard-cap lehine deterministic forced split ile bozulur. Provenance source unit ve fragment sırasını korur.
- A0 frozen V3'tür. A1 relative selector, A2 soft structure, A3 semantic-safe merge ve A4 full core V4 bileşimidir. Config hash ablation bileşimini içerir.
- A5 contextualization uygulanmamıştır; boundary değerlendirmesinden ayrı retrieval-side ablation olarak bırakılmıştır.
- Checkpoint primary metriği 15 HIGH gold boundary üzerinde ±1 one-to-one F1'dir. Exact F1 secondary diagnostic metriktir; `review` kayıtları primary metriğe katılmaz.
