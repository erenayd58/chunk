# Viewer — parçalama davranışını gösteren ürün sayfası

Viewer tek bir soruya odaklanır: *bir doküman seçilen yöntemle nerede
kesiliyor, ikinci bir yöntem aynı içeriği nereden farklı kesiyor?* Salt-okur
bir builder (`amsc.viewer.build`) ve kendi template'idir; backend'e, pipeline'a
ve API sözleşmelerine dokunmaz.

## Deneyim

* **İlk açılış "Genel" ekranıdır** — hiçbir şey seçili değildir; sayfa gerçek
  durumu özetleyen bir genel bakışla açılır: dört hücrelik stat şeridi (bilgi
  tabanı / doküman / hazır analiz / parça sayısı), **Bilgi tabanları** paneli
  (yerleşik korpus + konsolun canlı tabanları, hazır sayılarıyla), **Son
  eklenenler** (canlı dokümanlar, `hazır · işleniyor · kuyrukta · hata`
  çipleriyle; hazır olana tıklamak doğrudan İncele'ye götürür; konsol yoksa
  yerine yerleşik dokümanlar listelenir) ve oturumun **Son sorguları**. Hiçbir
  sayı uydurulmaz: her hücre gömülü payload'dan okunur.
* Üstteki kompakt seçim çubuğu sırayı taşır: *Bilgi tabanı › Doküman ›
  Yöntemler*; sekmeler *Genel · İncele · Sorgu · Debug · Benchmark*.
* **Debug sekmesi** tek soruyu cevaplar: *bu sınır neden böyle oluştu, sistem
  bu karara nasıl ulaştı?* **Boru hattı** şeridi beş gerçek adımı sayılarıyla
  gösterir (Parser → Yapısal sınır → Kural katmanı → Model önerisi →
  Doğrulama); süre yalnız kaydedilmişse yazılır, koşmayan adım soluk ve
  "çalışmadı" der. **Sınır kararları** tablosu, kayıtlı karar izinden yalnız
  bir şeyin değiştiği bölümleri listeler (Kural / Model / Kalite kontrol
  kaynağı, tetikleyen problem kodu, kesim sayısı değişimi, kabul / geri
  çevrildi / geri alındı) ve filtrelenir; satır detayı sayfa, token, giderilen
  problem, öneri sayısı ve *İncele'de aç* bağlantısını taşır. **Model
  kullanımı** paneli çağrı, oy, kabul/red, token (karakterden tahmin olduğu
  yazılır) ve yaklaşık maliyeti; model koşmadıysa yalnız gerçek durumu söyler.
  **Parser bulguları** koyu mono panelde canonical üzerindeki gerçek lint
  kayıtlarını listeler. Karar izi olmayan dokümanlarda tablo yerine yöntem
  başına **sınır nedenleri** histogramı (her parçanın kayıtlı `rs` kodu)
  gösterilir. Ölçülmeyen hiçbir değer üretilmez.
* **Benchmark sekmesi** yalnız gerçekten ölçülmüş değerleri gösterir.
  Dondurulmuş dokümanlarda (KKB 2024/2022, Arçelik 2024): **Standard → Deep
  Analysis** bandı (yapısal problem S→D, kötüleşen bölüm, ilk 5'te doğru
  parça, ek maliyet), problem türü başına sınır kalitesi tablosu, "Bedeli"
  paneli ve koyu **"Neyi iddia etmiyoruz"** kutusu; ikinci bölümde gold set
  üzerinden **arama başarısı** tablosu (Hit@1/3/5, MRR, kanıt kapsama; sütun
  bazında en iyi değer ● ile işaretli, kazanan ilan edilmez); katlanır **Ham
  ölçümler** altında yapısal kalite ve zamanlama tabloları. Gold set'i
  olmayan dokümanlarda (Arçelik ve RAG Console'a sonradan eklenenler)
  Hit@k/MRR **üretilmez**; bunun yerine yöntemler yan yana gerçek parça
  sayısı, token medyan/P90, başlıkla açılma, tablo/liste bölünmesi ve —
  varsa — işleme süresiyle karşılaştırılır, Deep koşusu kendi gerçek karar
  kayıtlarıyla (danışılan bölüm, kabul/geri çevrilen öneri, çağrı, süre,
  maliyet) sunulur. Yeni yüklemelerde her yöntemin işleme süresi konsol
  paketleyicisindeki minimal telemetriyle (`variants[m].seconds`) kaydedilir;
  eski analizlerde süre "—" olarak görünür.
* **Yerleşik korpus** (build'e gömülü dokümanlar) listelenir. Canlı bilgi
  tabanları bu sayfada değil, RAG Console'un kendi Viewer ekranındadır: Step 13
  bu deponun `:8765` sunucusunu ve konsola giden `/api/demo/*` aktarmalarını
  kaldırdı (`chat_rag/docs/legacy-removal.md`).
* **Yöntemler hard-code edilmez**: yalnız o dokümanın gerçekten paketlenmiş
  kolları (canlı dokümanlarda `live.methods` içinde `ready` olanlar) sunulur.
  Ürün adları: Markdown, Hybrid, Standard, Deep Analysis.
* **Tek yöntem görünümü** okuma deneyimidir: doküman sayfa sayfa, bir kâğıt
  yaprağı üzerinde akar; parça sınırı = boşluk + ince çizgi + küçük bir etiket
  (`74 · Boyut sınırı`). Parçaya tıklayınca minimal bir kart açılır (sayfa,
  bölüm, token, sınırın insan diliyle nedeni); teknik ayrıntı kartın içinde
  ayrıca açılır.
* **İkinci yöntem seçilince** aynı yaprak kolonlara bölünür: aynı canonical
  birim her kolonda **aynı satırda** basılır (bir yöntem birimin *içinde*
  kesiyorsa metin bütün kolonlarda aynı ofsetlerden dilimlenir), böylece yalnız
  sınırlar oynar. Soldaki ince sütun, yöntemlerin ayrıştığı satırları işaretler;
  `‹ Fark / Fark ›` bu satırlar arasında sayfa atlayarak gezer. Üçüncü yöntem
  üçüncü kolon olur (en fazla üç).
* **Deep Analysis** yalnız gerçekten paketlenmiş bir koşu varsa görünür; model
  koşmadıysa çip bunu söyler (`kural tabanlı`, `modelsiz tamamlandı`…). Deep'in
  değiştirdiği sınırlar ilgili sınır etiketinde mor bir nokta taşır ve kart o
  sınırda neyin düzeldiğini söyler. Ayrı bir dashboard yoktur.
* **Parçalar üç pastel tonla boyanır** (parça sırası mod 3, komşular hiç aynı
  tona düşmez); üzerine gelinen parça kendi tonunda koyulaşır, tıklanan parça
  daha da koyulaşır ve ince bir accent çizgisi taşır.
* **Sorgu sekmesi** (üst bardaki İncele / Sorgu anahtarı; bilgi tabanı
  seçilmeden açılamaz): iki kolonlu bir çalışma alanıdır — solda geniş ana
  akış (soru, **Kapsam**: tüm bilgi tabanı ya da tek doküman, yöntem çipleri,
  **Sor**, sonuçlar), sağda yapışkan **Parametreler** paneli (Model ve Top-k
  seçicileri + canlı sistem satırları); dar ekranda panel ana akışın altına
  iner. Yöntemler onay kutusu değil **çiplerle** seçilir: tek çip o yöntemle
  sorar, birden çok çip yalnız seçilenleri karşılaştırır (ör. yalnız Deep
  Analysis + Hybrid); bilgi tabanı kapsamında tek yöntem koşar. Doküman seçmek zorunlu değildir:
  *Tüm bilgi tabanı* kapsamında soru, o yöntemle hazır her dokümanda mevcut
  `/api/retrieve` ile sırayla aranır (ilerleme görünür), en iyi eşleşen
  doküman `/api/chat` ile cevaplanır ve diğer eşleşmeler "Bu dokümanda
  cevapla" ile bir tık uzakta durur — yeni bir uç nokta yoktur ve tek
  dokümanmış gibi davranan birleşik cevap üretilmez.
  Cevap kaynak kartlarıyla gelir (S1..Sn, bölüm, sayfa, token, "cevapta
  kullanıldı"); bir kart açılıp parça metni okunabilir ve *İncele görünümünde
  aç* ile o parçaya atlanır. Dondurulmuş dokümanlarda **örnek sorular** ve
  katlanır **ölçüm soruları** tablosu (frozen koşunun kayıtlı ilk-isabet
  sıraları) kalır. Sağdaki **Parametreler** kutusu tamamen canlıdır:
  Embedding / Cevap modeli / Bağlam sunucunun `/api/health` cevabından, top-k
  ve `Yöntem · n parça` satırı anlık seçimden okunur — hiçbir model adı ya da
  sayı sayfaya gömülmez.
* **RAG Console rozeti** her ekranda üst bardadır (`RAG Console · 21/33
  doküman hazır`); konsola ulaşılamıyorsa bunu söyler, tıklanınca bilgi tabanı
  menüsü açılır. Debug ve Benchmark ekranları bilinçli olarak yoktur.

## Üretim ve sunum

```powershell
py -3.11 -m amsc.viewer.build `
  --benchmark kkb-2024=artifacts/chunk-benchmark-v5/kkb-2024 --benchmark kkb-2022=artifacts/chunk-benchmark-v5/kkb-2022 `
  --deep kkb-2024=artifacts/deep-analysis/kkb-2024-final --deep kkb-2022=artifacts/deep-analysis/kkb-2022-final `
  --deep arcelik-2024=artifacts/holdout-arcelik-2024/deep-final --label "arcelik-2024=Arçelik 2024 (holdout)" `
  --output artifacts/viewer-v3/index.html

```

`index.html` dosya olarak açılır ve yerleşik korpusla tam çalışır. Builder,
sayfanın yanına `catalog.json` yazar (`generator: amsc.viewer.build`); bu
katalog `amsc.viewer.chat` motorunun okuduğu kataloğun aynısıdır — motoru
artık konsol kendi süreci içinde koşturur.

## Veri sözleşmesi

Doküman payload'ı **birebir** `viewer.corpus.load_corpus` çıktısıdır — bu
sayfadaki gömülü dokümanlar build sırasında, konsolun Viewer ekranındaki canlı
dokümanlar `GET /api/v1/documents/<id>/analysis/payload` ile aynı şekli alır;
iki depoda tek okuyucu vardır. Sınır nedenleri
(`rs`), birim dilimleri (`seg`), üyelik (`m`) ve Deep karar kayıtları (`dec`)
okuyucunun ürettiği alanlardır; hiçbir değer yeniden hesaplanmaz ya da
uydurulmaz.
