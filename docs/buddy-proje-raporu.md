# Adaptive Multi-Signal Semantic Chunking — Proje Raporu

Bu rapor, KKB dokümanları için LLM çağırmadan konu geçişlerini bulmaya çalışan **Adaptive Multi-Signal Semantic Chunking** (AMSC) PoC’sinin bugünkü durumunu özetler. Amaç: ne yapıldığını, neden yapıldığını, hangi ölçümlerin alındığını ve şu an nerede durduğumuzu aynı resmi paylaşmayan bir ekip arkadaşına anlatmak.

Kaynaklar: `README.md`, `docs/`, `configs/`, `src/amsc/`, `tests/`, `evaluation/kkb-2024/` altındaki authoritative raporlar ve git etiketleri. Sayılar frozen çıktılardan alınmıştır; pre-conformance (bugfix öncesi) V4 koşuları authoritative değildir.

---

## 1. Problem ve amaç

KKB tarafında RAG hattı, dokümanı parçalara (**chunk**) ayırıp bunları arama ve cevap üretiminde kullanıyor. Referans sistem bilgisine göre mevcut chunklama hibrit: anlamsal benzerlik (cosine / “semantic momentum”), başlık, paragraf, token ve recursive karakter kuralları birlikte çalışıyor. Gözlem: **chunk sınırları her zaman konu sınırlarıyla örtüşmüyor**. Konu ortasında kesilen veya iki konuyu birleştiren parçalar, retrieval’a yanlış veya eksik bağlam taşıyor.

**Chunking RAG için neden önemli?** Model ancak elindeki parçayı görür. Sınır kötüyse ilgili kanıt başka chunk’ta kalır, alakasız metin aynı chunk’a girer. Embedding, BM25 veya reranker bu hatayı sonradan tam düzeltemez.

PoC’nin sorduğu net soru şudur: Mevcut “komşu cosine + sabit eşik” tarzı yaklaşımın kaçırdığı veya yanlış ürettiği sınırları, **LLM/API olmadan**, daha geniş bağlam ve doküman yapısıyla daha doğru bulabilir miyiz?

İyileştirmeye çalıştığımız şey üretim parser’ı veya tüm RAG mimarisi değil; **anlamsal sınır kararı**. PDF/IDP parsing, her sınır için LLM, production tokenizer garantisi ve baştan sona retrieval/rerank yeniden tasarımı bilinçli olarak kapsam dışı bırakıldı. İlk gerçek doküman **KKB 2024 Faaliyet Raporu**.

Seçilen yaklaşımın adı Adaptive Multi-Signal Semantic Chunking: eşiği dokümanın kendi dağılımından üretmek, tek paragraf çiftine bakmamak, yapıyı sert kural yerine sınırlı destek olarak kullanmak, token tavanını bozmamak.

---

## 2. Kurduğum çalışma / evaluation altyapısı

Algoritmayı “biraz daha iyi hissettirmek” yerine tekrar çalıştırılabilir bir checkpoint kurdum. Nedeni basit: aynı girdi ve aynı metrik olmadan V1–V4 karşılaştırması spekülasyon olur.

| Parça | Ne | Neden |
|---|---|---|
| KKB 2024 Faaliyet Raporu | İlk PoC dokümanı; 85 fiziksel sayfa, canonical JSONL’de 1829 unit | Gerçek, Türkçe ağırlıklı, tablo/görsel/uzun paragraf baskısı olan kurumsal rapor |
| Canonical unit | Parser çıktısı heading / paragraph / list / table (görsel metin paragraph) sırasına çevrilir | Chunker parser’dan bağımsız çalışsın; layout hatası ile algoritma hatası karışmasın |
| Token limiti | `tiktoken:cl100k_base`, `min=160`, `hedef=700`, `soft=900`, `hard=1126` | Production’daki 1126 bilgisine yaklaşmak; **hangi tokenizer’ın production’da kullanıldığı bilinmiyor**, bu yüzden garanti yalnız PoC sayacına aittir |
| Embedding | `intfloat/multilingual-e5-base`, sınır kararı için `query: ` öneki; uzun metinde sessiz kesme yok, fragment + ağırlıklı ortalama | Türkçe uyumlu açık model; sınır embedding’i ile ilerideki retrieval embedding’i ayrı arayüz |
| Manuel gold sınır seti | 9 temsilî bölgede 15 `HIGH` konu geçişi; 5 `REVIEW` kayıt primary metriğe girmez | Tüm raporu etiketlemek gerekmez; belirsiz sınırlar skoru şişirmesin |
| Exact ve ±1 F1 | Exact: birebir unit çifti. ±1: bir content-unit kaymaya izin (primary) | Parser’ın kaçırdığı görsel başlık gibi 1-unit kaymalar tamamen “kaçırıldı” sayılmasın |
| SHA / golden test | Canonical SHA `2776742d…20d5`; V1–V3 fixture byte-golden; V3/A1–A4 `metrics.json` SHA freeze | Koşu değişince sessizce sapmasın |

Checkpoint PDF adapter’ı (`pymupdf4llm` layout, spread-aware iki kolon okuma) **evaluation girdisi** üretir; production IDP değildir. Heading tipi Markdown `#` işaretinden gelir; parser’ın kaçırdığı veya yanlış başlık saydığı örnekler `checkpoint.edge-cases.md` içinde açık tutulur. Gold annotation dosyasının durumu `in_review`: set dondurulmuştur ama “nihai kurumsal gold” iddiası yoktur.

Parametreler (`fixed_threshold=0.20`, MAD/quantile, V3 ölçek ağırlıkları `0.35/0.26/0.39`, V4 `semantic_floor=0.12` vb.) **optimize edilmiş üretim değerleri değil**, PoC başlangıç değerleridir. Checkpoint’e göre tune edilmediler.

---

## 3. Geliştirme süreci

Sürümler birikimli: her adım bir önceki davranışı dondurup tek bir algoritmik fark ekler. V1–V3’ün ayrı git etiketleri vardır (`v1-baseline`, `v2-adaptive-threshold`, `v3-multiscale-context`). V4 ve KKB checkpoint’i `phase3a-failure-analysis` ile birlikte dondurulmuştur.

### İlk baseline — V1

**Yaklaşım:** Komşu iki içerik biriminin embedding’i karşılaştırılır (**adjacent semantic similarity**). Anlam kayması (`semantic_shift`, düşük cosine = yüksek kayma) sabit eşiği (`0.20`) geçerse aday olur. Selector ilk geçen sınırı almaz; `[min, soft_max]` aralığındaki adaylar arasından anlam + hedef boyuta yakınlık skorunu seçer. Aday yoksa `size_fallback`, tavan zorlanırsa `hard_limit_fallback`. Tam render edilmiş metin üzerinde hard cap doğrulanır. Başlıklar embed edilmez, sonraki paragrafa bağlanır.

Bu dokümanda V1’in en yüksek kayması `0.135` olduğu için **hiç semantic candidate üretmedi**; seçilen sınırların neredeyse tamamı boyut fallback’i.

| Yaklaşım | Ne değişti? | Neden? | Sonuç (15 HIGH, ±1 / exact F1) |
|---|---|---|---|
| V1 sabit eşik + 1↔1 + token-aware seçim | İlk ölçülebilir baseline | Mevcut cosine+eşik fikrini şeffaf ve tekrarlanabilir kılmak | 0.3571 / 0.2857; 0 semantic candidate; size fallback oranı %92 |

### Adaptive threshold — V2

**Yaklaşım:** Aynı 1↔1 kayma ve aynı selector. Fark: her sınıra **dokümanın / bölümün kendi kayma dağılımından** eşik. Kapsam, komşu `section_path` ortak öneki; örnek yetmezse parent’a, sonra tüm dokümana çıkılır (hierarchical). Yeterli örnekte medyan + MAD (sağlam yayılım) ile eşik; çok kısa dokümanda sabit `0.20` fallback.

V2 bu raporda 138 semantic candidate üretti. Primary ±1 skor **V1 ile aynı kaldı** (TP=5, FP=8, FN=10). Yani “eşik artık adaptive” tek başına gold sınırları kurtarmadı; selector hâlâ ham kayma ile karşılaştırıyordu (bilinen V2 kısıtı).

| Yaklaşım | Ne değişti? | Neden? | Sonuç |
|---|---|---|---|
| V2 hierarchical adaptive eşik | Sabit 0.20 yerine local dağılım | Bu dokümanda gerçek kaymalar 0.20’nin altında; tek eşik kör kalıyordu | ±1 F1 0.3571 (V1 ile aynı); exact F1 0.2143’e düştü; semantic candidate 138 |

### Multi-scale semantic context — V3

**Yaklaşım:** Yalnızca “bu paragraf vs sonraki paragraf” (1↔1) değil; mümkünse ikişer ve üçer birimlik pencereler de (2↔2, 3↔3). Pencere vektörü mevcut unit embedding’lerinden token-karekök ağırlığıyla üretilir; yeni model çağrısı yok. Birleşik kayma, eldeki ölçeklerin `0.35/0.26/0.39` ağırlıklı ortalaması.

**Neden önemli?** Tek cümlelik stil farkı 1↔1’de yüksek kayma gibi görünebilir; asıl konu değişimi birkaç paragraf sonra netleşir. Tersine, geniş pencere yerel geçişi bastırabilir — bunu failure analysis sonra gösterdi.

V3, frozen sette **en büyük sınır-skoru sıçraması**: ±1 F1 **0.3571 → 0.5517**, exact F1 **0.2143 → 0.4138**. ±1: TP=8, FP=6, FN=7.

| Yaklaşım | Ne değişti? | Neden? | Sonuç |
|---|---|---|---|
| V3 1↔1 + 2↔2 + 3↔3 | Semantic shift çok ölçekli | Yerel gürültü vs gerçek konu geçişini ayırmak | **±1 F1 0.5517**, exact 0.4138; size fallback %63; 70 seçilmiş semantic sınır |

### Semantic-first V4 (A4 = full core)

V4, V3’ün kayma ve adaptive eşiğini korur; üzerine dört parça ekler (A0=V3, A1–A4 ablation):

1. **Threshold-relative boundary strength:** “Ham kayma ne kadar yüksek?” yerine “eşikten ne kadar yukarıda?” Selector A1/A4’te bunu kullanır; farklı local eşikleri adil karşılaştırmak için.
2. **Soft structural support:** Başlık, `section_path` geçişi, tablo/liste/görsel tür değişimi eşiği en fazla `0.04` gevşetebilir; generic başlık zorunlu kesim değildir.
3. **Token-aware selector:** Hedef boyuta uzaklık skoru korunur; karar yine render edilmiş metin üzerindendir.
4. **Semantic-safe merge:** Küçük chunk’ları komşuya, orijinal eşik ve orijinal strength ile, tek geçişte birleştirmeyi dener. Hard cap her zaman üstündür. `hard_limit_fallback` sınırları merge’e giremez.

**Conformance bug:** İlk A3/A4 koşusunda `hard_limit_fallback` sınırları yanlışlıkla merge’e uygun sayılıyordu ve sıralama mutlak cohesion margin yerine göreli pair-shift kullanıyordu. Bu yüzden 917, 925, 1307 gibi hard-limit sınırları birleşiyordu. Bugfix sonrası bu kayıtlar reddedilir; authoritative çıktı `evaluation/kkb-2024/v4-ablation/` altındadır. Eski koşu `v4-ablation.pre_conformance_fix/` içinde arşivdir, skor iddiasında kullanılmaz.

Post-fix A4: ±1 F1 **0.5517 → 0.5926**, exact **0.4138 → 0.4444**. Recall aynı (8/15); precision arttı (FP 6→4). İki merge kabul edildi (922 size_fallback, 1327 adaptive). Structural-assisted seçilmiş sınır: **0**.

| Yaklaşım | Ne değişti? | Neden? | Sonuç (post-fix) |
|---|---|---|---|
| A1 relative selector | Ham kayma yerine eşik-göreli güç | V2/V3 limitation: farklı eşikli adayları ham shift ile kıyaslamak | ±1 F1 0.5714; küçük chunk oranı arttı |
| A2 soft structure | Eşik gevşetme | Başlık/section sinyalini sert kural yapmadan kullanmak | **A0 ile birebir aynı**; floor yüzünden gevşeme çalışmadı |
| A3 semantic-safe merge | Küçük parçaları birleştir | Kısa chunk ve bazı FP’leri azaltmak | ±1 F1 0.5714; 2 merge |
| A4 A1+A2+A3 | Full core V4 | Bileşenlerin birlikte etkisi | **±1 F1 0.5926**, exact 0.4444; small-chunk oranı V3 ile aynı %2.46 |

Frozen success gate **bütünüyle geçmedi**: primary F1 iyileşti; bugfix sonrası küçük-chunk iyileşmesi kalmadı; all-fallback oranı `%71.19 → %71.60` arttı.

---

## 4. Benchmark sonuçları (authoritative)

Gold: 15 HIGH sınır, 9 bölge. Primary: ±1 one-to-one F1. Secondary: exact F1. Canonical SHA yukarıdaki frozen girdi.

| Koşu | Exact P / R / F1 | ±1 P / R / F1 | ±1 TP / FP / FN |
|---|---|---|---|
| V1 | 0.3077 / 0.2667 / 0.2857 | 0.3846 / 0.3333 / 0.3571 | 5 / 8 / 10 |
| V2 | 0.2308 / 0.2000 / 0.2143 | 0.3846 / 0.3333 / 0.3571 | 5 / 8 / 10 |
| V3 / A0 | 0.4286 / 0.4000 / **0.4138** | 0.5714 / 0.5333 / **0.5517** | 8 / 6 / 7 |
| A1 | 0.4615 / 0.4000 / 0.4286 | 0.6154 / 0.5333 / 0.5714 | 8 / 5 / 7 |
| A2 | 0.4286 / 0.4000 / 0.4138 | 0.5714 / 0.5333 / 0.5517 | 8 / 6 / 7 |
| A3 | 0.4615 / 0.4000 / 0.4286 | 0.6154 / 0.5333 / 0.5714 | 8 / 5 / 7 |
| **A4 / V4** | 0.5000 / 0.4000 / **0.4444** | 0.6667 / 0.5333 / **0.5926** | 8 / 4 / 7 |

V4’ün yaptığı iş: **daha fazla doğru sınır bulmak değil**, yanlış pozitifleri azaltmak. Recall 0.5333’te kaldı. Bu yüzden “V4 semantic olarak V3’ü net geçti” demiyoruz; precision tarafında kontrollü bir kazanç var.

Success gate’in tam geçilmemesi de buradan okunur: F1 hedefini sınır tarafında gördük, ama küçük-chunk ve fallback oranları V4’ü “boyut davranışı da iyileşti” diye kapatmaya yetmedi. Fallback hâlâ ~%71: yani seçilen sınırların çoğu hâlâ semantic candidate değil, token penceresi dolduğu için kesiliyor.

---

## 5. Failure analysis

Skor tablosundan sonra prediction-level audit çalıştırdım (`phase3a-failure-analysis`). Evaluator’ın exact/±1 eşlemesi değişmez; yalnız *neden* doğru/yanlış olduğu yazılır.

V3, A3 ve A4 için aynı tablo:

- 15 HIGH gerçek sınır
- **8’i ±1 ile yakalandı, 7’si kaçtı** (exact’te 6 yakalandı)
- Yakalanan 8 TP’nin **yalnız 3’ü semantic sınır**, **5’i size fallback**
- Hard-limit TP: 0
- A4’te kalan 4 FP’nin hepsi size/hard fallback; semantic FP yok

Kaçırılan 7 HIGH’ın **5’inde multi-scale suppression** var: bir ölçekteki kayma eşiğin üstündeyken birleşik kayma eşiğin altında kalıyor. Tipik örüntü: 1↔1 görece yüksek, 2↔2 ve 3↔3 düşük, ortalama eşiği geçemiyor. İki FN’de ise mevcut üç ölçek de eşiğin altında.

Soft structure bu config’te **aktive olmadı**. Adaptive eşikler (~0.065) `semantic_floor=0.12`’nin altında. Formül eşiği floor’un *altına* çekerek yükseltmez; gevşeme 0 kalır. Structural evidence vardır, `structural_assisted` seçilmiş sınır yoktur. Heading’li FN’ler “yapı kuralı çalıştı ama yetmedi” değil, “gevşeme hiç uygulanmadı”.

Merge **high-confidence guard** (`0.50`) gözlenen strength dağılımına göre çok yüksek: A4’te 136 sınırda max strength ≈ 0.035, guard’ı geçen 0 kayıt. Guard fiilen hiç devreye girmiyor.

**Boundary 1327** riskli kabul örneği: orijinal neden `adaptive_semantic_boundary`, pair kayması eşiğe 0.0006 marjla altında, yapı uyumu `False`. Tasarım gereği structure veto değildir; finansal tablo bölümü “bilanço tarihinden sonraki olaylar” paragrafına bağlanmış. Gold bölge dışında olsa da merge kuralının sınırda kabul ettiği bir vaka.

Mesaj: Skora bakıp durmadım. V4’ün kazancı çoğunlukla FP kesmek; hâlâ yakalanan gold’un çoğu şanslı size-fallback; asıl kaçan geçişlerde çok ölçekli ortalama ve çalışmayan soft structure görünüyor.

---

## 6. Denediğim alternatif araştırmalar

Bunlar “başarısız denemeler” değil; hipotezi ölçüp reddeden kontrollü deneyler. Gold ile parametre uydurulmadı.

### Scale-calibration (Phase 3B, etiket: `phase3b-scale-calibration-negative-result`)

**Hipotez:** 1, 2, 3 ölçeklerini *kendi* dağılımlarına göre kalibre edersek, birleşik ortalamanın bastırdığı konu geçişleri kurtulur.

- B0: V3 kontrol (byte-identical)
- B1: yalnız tanı; chunk çıktısı V3 ile aynı
- B2: ölçek-bazlı eşik-göreli kanıt + “herhangi bir ölçek candidate ise candidate”
- B3: B2 + post-fix semantic-safe merge

**Ölçüm:** B2/B3 ±1 F1 **0.5000 / 0.5185** — V3’ün 0.5517’sinin altında. Orijinal 7 HIGH FN’de B1 hiçbir ölçeği gold konumunda candidate yapmadı. B2/B3’te görülen tek “kurtarma” `indirect_size_fallback`; genuine semantic rescue **0**.

**Karar:** Hipotez development checkpoint’te desteklenmedi. V5 diye production adayı ilan edilmedi; negative result olarak donduruldu.

### Local prominence / change-point (Phase 3C, etiket: `phase3c-development-result`)

**Hipotez:** Sabit çok ölçekli ortalama yerine lokal semantic tepe (C1) veya cosine-kernel change-point (C2) daha iyi sınır adayı üretir.

- C0: yine V3 kontrol
- C1: `local_semantic_prominence` — ±1 F1 **0.3200**, önceki doğru HIGH’larda regresyon
- C2: `cosine_kernel_change_point` — ±1 F1 **0.6452**
- C3: C2 + frozen merge — ±1 F1 **0.6667**

**Ölçüm:** C3 skoru V3/V4’ten yüksek görünür. Ama orijinal 7 FN’de genuine semantic rescue yine **0**. C3’ün yakaladığı ek sınırlar `size_fallback` konumunun kayması. Semantic TP sayısı C0 ile aynı: **3**.

**Karar:** C3 “semantic olarak daha iyi yöntem” diye iddia edilmedi. Development winner seçim kuralı skoru C2’ye verdi; yorum kuralı açık: skor ≠ semantic iyileşme.

---

## 7. Şu anki durum

Git’te dondurulmuş hat:

- V1–V3 ayrı tag; V4 + gold + authoritative ablation + failure analysis `phase3a-failure-analysis`
- Phase 3B negative-result checkpoint’i mevcut
- Phase 3C development araştırması tamam (`phase3c-development-result`)
- `main` origin’den 3 commit önde (3A–3C)
- Phase 3C anındaki test seti: **167 test geçti** (model indirmeden deterministic double’lar)

Production winner **ilan edilmedi**. V4 core PoC olarak duruyor; frozen success gate tam geçmedi. C3 yalnız araştırma koşusu.

**Çalışma kopyasında (henüz commit/tag yok):** Phase 4 retrieval benchmark’ı yazıldı ve KKB development setinde koşuldu. Parser ve retrieval hattı sabit; yalnız chunker değişiyor. 50 soruluk gold, retrieval çıktıları görülmeden elle yazıldı. Adaylar: public Legacy `chat_rag` uyumluluk adapter’ı, V3, A4/V4, C3. Dense: E5 (`query:` / `passage:`), Unicode BM25, eşit ağırlıklı RRF; query expansion / contextualization / reranker kapalı.

Authoritative Phase 4 özeti (`evaluation/kkb-2024/retrieval-benchmark/results/`):

| Chunker | Hit@1 | Hit@3 | Hit@5 | MRR | Evidence coverage@5 | Source coverage |
|---|---:|---:|---:|---:|---:|---:|
| Legacy (public adapter) | 0.26 | 0.38 | 0.40 | 0.318 | 0.40 | 0.58 |
| V3 | 0.54 | 0.68 | 0.80 | 0.628 | 0.80 | 1.00 |
| A4 / V4 | 0.54 | 0.70 | 0.78 | 0.626 | 0.78 | 1.00 |
| C3 | 0.54 | 0.74 | 0.82 | 0.641 | 0.82 | 1.00 |

Bu tablo **KKB production agentic chunker karşılaştırması değildir**. Legacy satırı `MurselTasgin/chat_rag` public kodunun canonical girdi üzerindeki adapter’ıdır; kısa section düşürme + frozen heading’ler source coverage’ı 0.58’e indirmiştir. C3’ün Hit@5 avantajı, Phase 3C’deki “semantic rescue = 0” uyarısı dururken production kazananı seçmez. V4, V3’e göre Hit@5’te q017’yi kaybeder; kazandığı soru yoktur. Tek belgelik development checkpoint; holdout yok.

Çalışma kopyasındaki Phase 4 unit/gold testleri ayrıca 9 test geçiyor (toplam collect 176). Bu katman henüz git’te freeze edilmedi.

---

## 8. Bundan sonraki önerilen adım

1. Phase 4 çıktısını V1–V3 / 3A–3C gibi SHA + rapor + testle dondurmak (şu an uncommitted).
2. Retrieval sonucunu sınır F1’inden ayrı okumak: V3 ve V4 bu 50 soruda birbirine çok yakın; C3 hafif önde ama semantic iyileşme kanıtı değil; Legacy satırı production baseline değil.
3. Kazanan ilan etmeden önce ikinci belge / holdout veya en azından gold’un `in_review` kapanışı.
4. Ardından seçilen yaklaşımı mevcut `chat_rag` projesine **minimal** entegre etmek (canonical unit → chunk → aynı retrieval sözleşmesi) ve küçük bir demo/UI: soru, top-k chunk, sınır nedeni (semantic / size / hard), provenance.

A5 contextualization bilinçli olarak yapılmadı; retrieval-side ayrı deney olarak duruyor.

---

## 9. Bu projede ne yaptım?

Sözlü özet:

1. KKB 2024 raporunu canonical unit’lere çevirip SHA ile dondurdum; gold sınırları elle, belirsizleri `REVIEW` dışında tutarak etiketledim.
2. LLM’siz, tekrarlanabilir bir chunker hattı kurdum: E5 embedding, ayrı token sayacı, heading attachment, hard cap, açıklanabilir provenance.
3. V1’de komşu benzerlik + sabit eşik ile gerçek baseline aldım; bu dokümanda sabit 0.20 eşiğinin hiç semantic aday üretmediğini ölçtüm.
4. V2 ile eşiği doküman dağılımına bağladım; V3 ile 1↔1 / 2↔2 / 3↔3 bağlama geçtim. Asıl sınır-skoru sıçraması V3’te geldi (±1 F1 0.36 → **0.55**).
5. V4’te eşik-göreli seçim, yumuşak yapı ve güvenli merge ekledim; merge bug’ını bulup düzelttim. Post-fix A4 ±1 F1 **0.59**, kazanç precision; recall aynı. Success gate tam geçmedi.
6. Hataları tek tek ayırdım: 7 kaçan HIGH’ın 5’i multi-scale bastırma; yakalananların çoğu size fallback; soft structure ve merge guard bu config’te fiilen boşta.
7. Scale-calibration ve change-point deneylerini gold’a uydurmadan koştum, skor yükselse bile semantic rescue 0 olduğu için “daha iyi semantic yöntem” demeden dondurdum. Production winner yok; sıradaki iş retrieval checkpoint’ini resmi dondurmak ve entegrasyon/demo.

---

*Rapor tarihi: 19 Ağustos 2026. Authoritative sınır metrikleri: `evaluation/kkb-2024/baseline/` ve `evaluation/kkb-2024/v4-ablation/`. Failure analysis: `evaluation/kkb-2024/failure-analysis/`. Phase 3B/3C: ilgili `summary.json` + tag’ler. Phase 4 retrieval: çalışma kopyası, git freeze yok.*
