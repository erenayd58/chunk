# Viewer v2 — Chunking + RAG PoC ürünü

Viewer v2, bu repodaki chunking araştırmasını tek bir sunulabilir üründe toplar:
dört chunking yöntemi, aynı sayfanın yöntemler arasında karşılaştırması, her sınırın
insan diliyle nedeni, gerçek bir "dokümana sor" deneyimi, mühendislik için karar izi
ve ölçümler. Tek bir HTML dosyasıdır; yalnız canlı sohbet için yerel sunucu gerekir.

## Sekmeler

| Sekme | Soru | İçerik |
|---|---|---|
| **Sunum** | Ne yaptık, fark ne? | İlk ekran **Parçaları karşılaştır** tezgâhıdır: seçilen her yöntem bir **kolon**dur ve kolonlar seçim sırasına göre dizilir (ilk seçilen solda). Paragraf ortak birimdir: aynı paragraf her kolonda aynı satırda basılır, böylece yalnız **parça sınırları** oynar. Bir parça karttır — bir sınır satırında numarası ve nedeniyle açılır (`Parça 74 · Boyut sınırına ulaşıldı · 371 tk`), sahip olduğu paragraf satırları boyunca sürer ve bir sonraki sınır satırında kapanır; **bölmeyen** kolon aynı yükseklikte kesiksiz akar ve `Parça 73 sürüyor` der. Bu iki kolonun ayrıştığı satır **ayrışma**dır: solundaki numaralı düğme oraya götürür, üstteki okuma satırı olayı cümleyle yazar ("Deep Analysis burada yeni parça açtı · Parça 74 · boyut sınırı — Standard bölmedi, devam etti · Parça 73 sürüyor") ve varsa Deep'in o sınırdaki kararını ekler. Ekran ilk ayrışmada açılır; ← → (ya da n / p) ayrışmadan ayrışmaya gezer ve ilgili parçaları görünür alana getirir; navigasyonda **yalnız sayfa** seçicisi vardır; soldaki dikey harita bütün dokümandaki ayrışmaları ve açık sayfayı gösterir. Metin *Tam / Kısa*, "Sadece ayrışmalar" aynı karar verilen blokları katlar, üç ya da dört kolonda "Yalnız Standard ↔ Deep" gezinmeyi ürünün kendi hikâyesiyle sınırlar. Sağ panel tıklanan parçanın detayıdır. **Sonuç** bandı, "Ne düzeldi?" çubukları, yöntem kartları ve metodoloji tezgâhın altındadır |
| **Sorgu** | Kullanınca nasıl çalışıyor? | *Dokümana Sor*: doküman + yöntem seç, doğal dilde sor → dense + BM25 (RRF) retrieval → aynı bölümün devam parçalarıyla bağlam → kaynaklı cevap; kaynak kartları (başlık, bölüm, sayfa, yöntem, kullanıldı mı), karta tıklayınca chunk metni ve "Sunum'da göster"; "Tüm yöntemlerle karşılaştır" aynı soruyu dört yöntemle koşar. *Gold sorgular*: frozen benchmark'ın sorgu-bazlı görünümü (çevrimdışı) |
| **Debug** | Sistem bu kararı neden verdi? | Canonical unit'ler (tip, rol, seviye, section path), her koldaki chunk/fragment/offset/method eşlemesi, parser bulguları, hard cap üstü unit'ler (temsil tavanı), unit inspector'da bölümün Deep karar izi (Standard → deterministik → final kesimler, kaldırılan kokular, LLM önerileri ve verifier kararları); bölüm kararları tablosu (durum filtresiyle) |
| **Benchmark** | Ölçümlerde sonuç ne? | Frozen benchmark v5 (üç kol) değişmeden; ayrı **Deep Analysis paneli**: koku tablosu (S→D, Δ), chunk_quality tablosu, retrieval (frozen değer kopya, Deep yeniden skorlandı), sınır kökeni, LLM çağrısı/verifier/fallback, süre, token ve maliyet tahmini, dürüst yorum; dokümanlar arası sözleşme tablosu |

## Görsel sistem

Dört sekme tek bir kabuğu paylaşır: üstte yapışkan bir başlık çubuğu (marka, alt
çizgili sekmeler, doküman seçici, RAG Console düğmesi) ve her ekranın başında aynı
üç cevabı veren bir **sayfa başlığı** — hangi ekran (küçük etiket), hangi doküman
(başlık) ve bu ekran ne işe yarar (bir cümle; Sunum'da başlık tek satıra iner, çünkü
ilk ekran karşılaştırma tezgâhınındır); sağında dokümanın bağlamı (set, Deep
Analysis durumu, birim / sayfa / yöntem sayısı).

Tezgâhın hizası tek bir kuralla ayakta durur: **satır karar verir, hücre değil.**
Pano tek bir CSS grid'idir, dolayısıyla bir "satır" bir eleman değil, kardeş
hücrelerden oluşan bir dizidir; bir yöntem paragrafın *içinde* kesiyorsa metin
bütün kolonlarda aynı ofsetlerden dilimlenir ve bir kolonun söyleyeceği bir not
varsa o not satırı bütün kolonlarda çizilir (söyleyecek şeyi olmayanda boş).
Genişliği değiştiren hiçbir işaret kullanılmaz — tek bir kolonda 11px'lik bir
iç boşluk, o kolonu bir satır aşağı kaydırmaya yeter. Zemin soğuk nötr, yüzeyler beyaz;
ürünün tek mavisi ve Deep Analysis'in tek moru dışında renk kullanılmaz. Her yöntem
kartında, şerit çipinde ve kesim çizgisinde **aynı rengi** taşır (Markdown amber,
Hybrid teal, Standard mavi, Deep Analysis mor). Sonuç bandı model çalıştıysa
mor-lacivert, çalışmadıysa gridir — durumun görüldüğü ikinci yerdir. Detay her yerde
aynı açılır bölümün arkasındadır; hiçbir bilgi silinmez, yalnız ikinci sıraya alınır.

## Üretim

```powershell
# 1. Deep Analysis koşusu (canlı model ya da replay) — yazdığı ağaç: chunks, audit, quality, proposer/, verifier/
py -3.11 -m amsc.deep_run --input data/kkb-2024.units.v3.jsonl --output artifacts/deep-analysis/kkb-2024-final --model qwen/qwen3-30b-a3b-instruct-2507 --verify

# 2. Kolu paketle (arm/, standard/, boundary-decisions.json; frozen ağaçla retrieval de skorlanır)
py -3.11 -m amsc.deep_arm --deep-tree artifacts/deep-analysis/kkb-2024-final --units data/kkb-2024.units.v3.jsonl --frozen-tree artifacts/chunk-benchmark-v5/kkb-2024

# 3. Viewer'ı üret (catalog.json yanına yazılır)
py -3.11 -m amsc.viewer_v2 `
  --benchmark kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 --benchmark kkb-2022=artifacts/chunk-benchmark-v5/kkb-2022 `
  --deep kkb-2024=artifacts/deep-analysis/kkb-2024-final --deep kkb-2022=artifacts/deep-analysis/kkb-2022-final `
  --deep arcelik-2024=artifacts/holdout-arcelik-2024/deep-final --label "arcelik-2024=Arçelik 2024 (holdout)" `
  --output artifacts/viewer-v2/index.html

# 4. Canlı sohbet için sunucu (anahtar yalnız bu süreçte, env'den)
py -3.11 -m amsc.viewer_server --viewer artifacts/viewer-v2/index.html --config configs/rag-poc.yaml --warm `
  --console-url http://127.0.0.1:5005
# → http://127.0.0.1:8765/
```

`index.html` dosya olarak açıldığında Sunum / Debug / Benchmark / gold sorgular çalışır;
Sorgu sekmesi sunucu yoksa bunu açıkça söyler ve komutu gösterir.

## Doküman ve analiz varyantı

Ürünün veri modeli iki kavramdan ibarettir:

* **Doküman** — yüklenen PDF'in kendisi, *içeriğiyle* kimliklenir (sha256).
  Aynı dosyayı ikinci kez yüklemek ikinci bir doküman yaratmaz; var olan
  dokümana yeni varyant ekler. Aynı adı taşıyan farklı iki dosya ise iki
  ayrı dokümandır.
* **Analiz varyantı** — o dokümanın canonical'ı üzerinde çalıştırılmış bir
  chunking yöntemi: Markdown, Standard, Deep Analysis, Hybrid.

Bir yükleme **bir kez** ayrıştırılır; seçilen her yöntem aynı
`units.jsonl` üzerinde çalışır ve `amsc.deep_arm.package_arm` ile
benchmark'ın kullandığı aynı yazıcıyla paketlenir. Deep Analysis seçilmişse
ingest'in kendi koşusu olduğu gibi alınır — Viewer için ikinci bir model
çağrısı asla yapılmaz. Sonradan bir yöntem eklemek (`POST
/api/demo/viewer-analysis/<doc>/methods`) dokümanı yeniden okumaz; yalnız
eksik varyantı üretir.

Viewer yalnız **gerçekten üretilmiş** varyantları karşılaştırmaya açar.
Üretilmemiş bir yöntem, karşılaştırma çubuğunda devre dışı görünür ve
nedenini söyler; sahte sonuç üretilmez.

## Hangi analiz gerçekten çalıştı?

Deep Analysis koşusunun **beş** durumu vardır (`amsc.deep_pipeline`: `ok`, `deterministic`,
`fallback_no_provider`, `fallback_provider_error`, `degraded`) ve `calls.total` *denenen*
çağrıyı sayar — hepsi başarısız olsa bile. Viewer bunları tek bir yerde,
`analysisState()` içinde, okuyucunun ayırt etmesi gereken altı duruma indirger:

| Durum | Rozet | Ekranda ne der |
|---|---|---|
| model çalıştı | *(ek rozet yok)* | maliyet ve çağrı sayısı gösterilir |
| kısmi model | `kısmi model` | uyarı: bazı çağrılar yanıtsız kaldı |
| Standard yükleme | `kural tabanlı` | model kullanılmadı; kazanç kural katmanından |
| modele gerek olmadı | `modele gerek olmadı` | Deep çalıştı, kararsız sınır çıkmadı |
| sağlayıcıya ulaşılamadı | `modelsiz tamamlandı` | uyarı: istendi ama ulaşılamadı |
| sağlayıcı yanıt vermedi | `model yanıt vermedi` | uyarı: çağrılar yanıtsız |

Yöntem kartı, hüküm cümlesi, maliyet kartı, güvence cümleleri ve Benchmark özeti bu tek
fonksiyonu okur — bu yüzden hiçbir ekran çalışmamış bir modeli faturalandıramaz.

## RAG Console bağlantısı (çalışma alanı şeridi)

`--console-url` (ya da `AMSC_CONSOLE_URL`; varsayılan `http://127.0.0.1:5005`) verildiğinde
sunucu `GET /api/workspace` uç noktasını açar ve bunu chat_rag'in
`GET /api/demo/workspace` çıktısından okur: güncel bilgi tabanları, içlerindeki dokümanlar,
parça sayıları. Sayfa kendi origin'ine sorar — tarayıcı ikinci bir adrese hiç gitmez, CORS
gerekmez, konsolun adresi HTML'e gömülmez. Konsol kapalıysa şerit "bağlanılamadı" der ve
sayfanın geri kalanı etkilenmez; dosya olarak açılan `index.html`'de şerit hiç görünmez.
Viewer bu durumu **yansıtır, saklamaz**: konsolda açılan bir bilgi tabanı bir sonraki
yenilemede (buton, ya da sekmeye geri dönüldüğünde) listede belirir.

## Canlı çalışma alanı dokümanları

Konsola yüklenen bir doküman yalnız listede görünmez; Viewer'da **gerçekten incelenir**.
Paketlemeyi konsol yapar (`chat_rag/components/viewer/analysis.py`): kendi ingest'inin
canonical unit'lerini ve — Deep Analysis yüklemesinde — koşunun kendisini `deep_run.write_tree`
ile yazar, `deep_arm.package` ile Viewer kolu haline getirir, `viewer_v2.load_corpus` ile
sayfanın payload'ını üretir. **İkinci bir parse ve ikinci bir LLM çağrısı yoktur**; Standard
modda yüklenmiş bir dokümanda karşılaştırmanın Deep tarafını `use_llm=False` deterministik
sözleşme üretir (sıfır çağrı, sıfır maliyet) ve durum böyle etiketlenir.

Bu tarafta iki uç nokta bunu taşır:

    GET  /api/live-document?doc=<id>   payload'ı konsoldan alır (sayfa kendi origin'ine sorar)
    POST /api/live-prepare  {doc}      konsola "bu dokümanın analizini hazırla" der

Sayfa payload'ı `DATA.docs` içine **canlı** işaretiyle katar. Analizi hazır olan her konsol
dokümanı ana doküman seçicide, `RAG Console — canlı dokümanlar` grubunda görünür ve oradan
doğrudan seçilebilir; sayfa henüz yüklemediyse seçim anında payload'ı çeker. Hazır olmayan
doküman listede *devre dışı* durur ve nedenini söyler (`analiz hazırlanıyor…`). Üst bardaki
**RAG Console** düğmesi aynı listeyi bir diyalogda ayrıntısıyla verir; ana içerikte yer
kaplamaz. Seçildiğinde Sunum ve Debug tam çalışır, Benchmark'ta doküman kendi "Bu dokümanda
kalite" bölümünü alır. Frozen benchmark tabloları, üç kol karşılaştırması ve dokümanlar arası tablo
bu dokümanlar için **hiç render edilmez**: gold sorgu setleri olmadığı için Hit@k/MRR
üretilmez ve uydurulmaz. Sorgu sekmesi de dokümanın RAG Console'da sorgulandığını söyler —
canlı doküman viewer sunucusunun demo korpusunda indeksli değildir.

## Sağlayıcılar ve gizli anahtarlar

`configs/rag-poc.yaml` embedding ve cevap modelini, uç noktayı ve anahtarın okunacağı
ortam değişkeninin **adını** taşır; anahtarın kendisini hiçbir dosya, artifact ya da
HTML taşımaz. Referans adaylar self-hostable: `Qwen/Qwen3-Embedding-8B` (embedding) ve
`qwen/qwen3-30b-a3b-instruct-2507` (cevap ve Deep Analysis proposer/verifier).
`provider: sentence_transformers` ile embedding tamamen yerelde koşar.

## Ürün giriş noktası (chat_rag için)

```python
from amsc.deep_pipeline import DeepAnalysisSettings, chunk_document

result = chunk_document(units, mode="deep", settings=DeepAnalysisSettings(
    proposer_model="qwen/qwen3-30b-a3b-instruct-2507",
    endpoint="https://openrouter.ai/api/v1/chat/completions",
    api_key_env="OPENROUTER_API_KEY",
    verify=True,
))
result.rows      # structural_chunker satır şeması — her modda aynı
result.status    # ok | deterministic | fallback_no_provider | fallback_provider_error | degraded
result.report    # JSON-serialisable: sayaçlar, koku toplamları, LLM etkisi, süreler; prompt/metin/anahtar yok
```

`mode="standard"` frozen structure-first yürüyüşünün kendisidir. Deep modunda anahtar
yoksa ya da sağlayıcı düşerse sonuç deterministik sözleşmedir ve `status` bunu söyler —
istisna fırlatılmaz, Standard'dan kötü bir bölümleme üretilmez.

## Claim disiplini

Bütün eşikler `poc_initial_not_optimized`. Deep Analysis model-bağımlı ve yalnız
replay-deterministiktir (seed yok). Retrieval farkları küçük gold setlerde gürültü
içindedir; ölçülebilir kazanım yapısal kalite sözleşmesindedir. Kazanan ilan edilmemiştir.
