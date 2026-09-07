# Yeni bir parçalama yöntemi eklemek

Bir parçalama yönteminin kimliği tek yerde tanımlıdır: `src/amsc/chunking/registry.py`.
Konsolun gönderdiği tel adı (`structure-only`), paketlenmiş `mapping.json`'ın
bildirdiği motor türü (`structure_first`), her ekranda görünen ürün adı
(`Standard`), tek cümlelik özet ve yeteneklerin (embedder gerekir mi, modele
danışır mı, benchmark kolu mu) hepsi oradaki bir `ChunkMethod` kaydıdır.
Viewer v3 builder'ı, Viewer okuyucusu (`amsc.viewer.corpus`), chunk benchmark'ı,
ilişki türeticisi ve chat_rag konsolu listelerini bu kayıttan okur. Yeni bir
yöntemin başka hiçbir dosyaya adının yazılması gerekmez -- Viewer'a özel bir
liste de yoktur; sınırın tamamı `docs/viewer-architecture.md`'de.

## Üç adım

Dokunulan dosya: **uygulama + tek kayıt satırı + test.** Üçü de aynı yerdedir:
yöntem modülü `src/amsc/chunking/`, kayıt `src/amsc/chunking/registry.py`,
test `tests/unit/chunking/`. Paketin tamamının haritası
[package-layout.md](package-layout.md)'dedir.

1. **Yöntem modülünü yazın.** Girdi canonical birimler, çıktı yapısal
   satır şeması: `chunk_id`, `text`, `unit_ids`, `token_count`, `pages`,
   `section_paths`, `heading`, `split_strategies`. İmza:

   ```python
   # src/amsc/chunking/fixed_window.py
   from .method import ChunkMethod, PartitionResult   # <- registry'den DEĞİL

   def partition_x(units, *, counter, budget, boundary_embedder=None,
                   respect_semantic_roles=False, **options) -> PartitionResult:
       ...

   FIXED_WINDOW = ChunkMethod(
       key="fixed-window",            # tel adı / Viewer kol adı
       kind="fixed_window",           # motor türü; benzersiz olmalı
       label="Sabit Pencere",         # ürün adı, her yerde bu
       summary="Ardışık birimleri sabit pencerelerde paketler.",
       partition=partition_x,
       needs_embedder=False,          # True ise `boundary_embedder` verilir
       options={"max_units": 3},      # canlı koşunun varsayılanları
   )
   ```

   `budget` paylaşılan token bütçesidir (`min_tokens`, `target_tokens`,
   `soft_max_tokens`, `hard_max_tokens`); her yöntem aynı bütçeyle koşar ki
   karşılaştırma yalnız sınırların nereye düştüğünü karşılaştırsın.

   **Tipler `amsc.chunking.method`'tan alınır, `amsc.chunking.registry`'tan değil.**
   `chunking.method` paketten hiçbir şey import etmeyen bir yaprak modüldür;
   `chunking.registry` sizin modülünüzü import edeceği için tipleri oradan almak
   döngü olur (`registry -> sizin modülünüz -> registry`) ve paketin import
   döngüsü muhafızını düşürür. `src/amsc/chunking/example.py` bu şekli
   birebir taşıyan, eksiksiz ve kopyalanabilir örnektir.

2. **Kaydedin.** `src/amsc/chunking/registry.py` içinde iki satır: import ve demete
   ekleme.

   ```python
   from .fixed_window import FIXED_WINDOW          # diğer importların yanında
   ...
   _BUILTIN: tuple[ChunkMethod, ...] = (MARKDOWN, HYBRID, STANDARD, DEEP, FIXED_WINDOW)
   ```

3. **Test edin.** `tests/unit/chunking/test_methods_registry.py` içindeki
   `test_the_example_partition_is_predictable` örnektir: elle hesaplanabilir
   bir girdi, beklenen `unit_ids` listesi.

Bu üç dosyadan başka hiçbir yere dokunulmaz. **Kayıt testleri de dahil:**
`test_methods_registry.py` kaç yöntem olduğunu değil, kayıtta ne varsa onun
sağlaması gereken değişmezleri (anahtar/tür benzersizliği, partition'ı olmayan
yöntem deep'tir, deep'in `baseline`'ı kayıtlı bir partition'dır, `meta()` her
anahtarı anlatır) doğrular. Geçerli bir beşinci yöntem hiçbir testi
güncellemeyi gerektirmez. Sabit tutulan tek liste dondurulmuş benchmark'ın kol
kümesidir; o bitmiş bir deneyin sözleşmesidir.

Konsol (chat_rag) kütüphaneyi sabitlenmiş bir commit'ten kurar; yöntemin
üründe görünmesi için chunk commit'lendikten sonra pin güncellenir --
komutu aşağıda, [Depolar arası pin](#depolar-arası-pin) bölümünde.

## Uçtan uca: kayıttan sonra ne oluyor?

Üç adım bittiğinde yöntem **kendiliğinden** her katmanda görünür. Her satır,
o katmanın adı nereden okuduğunu söyler — hiçbirine elle yazılmaz:

| Katman | Nasıl öğreniyor | Sonuç |
|---|---|---|
| Kütüphane | `methods.partition(key, …)` | yöntem canonical birimler üzerinde koşar |
| Konsol arka ucu (`chat_rag`) | `components/viewer/methods.py`, `amsc.chunking.registry`'i okur ve yalnız *bu makinede çalışabilir mi*, sıra ve varsayılan bilgisini ekler | `GET /api/demo/methods` yöntemi (ya da neden çalışamadığını) döner |
| Konsol ön yüzü | yükleme formu yöntem listesini aynı uçtan çeker | yükleme sırasında seçilebilir olur |
| Paketleyici | `components/viewer/analysis.py` seçilen her yöntemi tek canonical üzerinde koşturur | `artifacts/viewer-live/<doc>/variants/<key>/` |
| Viewer v3 | sayfa açılışta kendi sunucusundan `GET /api/methods` çeker; kayıt **o an** ne diyorsa onu listeler. Gömülü (derleme zamanı) kopya yalnız dosyadan açılan sayfa için yedektir | **sayfayı yeniden derlemeye gerek yok**; kolon olarak seçilebilir, kendi rengiyle çizilir |
| Viewer okuyucusu | `amsc.viewer.corpus` kolu `kind`'ıyla kabul eder | payload'da kol olarak taşınır |
| Benchmark | benchmark konfigürasyonunda bir kolun `kind`'ı olarak yazılabilir | dondurulmuş kol kümesi değişmeden karşılaştırmaya girer |
| Debug / karşılaştırma | Viewer'ın Debug sekmesi ve ayrışma gezinmesi kolları genel olarak işler | sınırların nerede ayrıştığı görünür |

Bu zincirin tamamı tek testle tutulur:
`tests/unit/chunking/test_methods_registry.py::test_a_registered_method_reaches_every_consumer_with_no_other_edit`.
Bir tüketici kaydı okumayı bırakırsa orada kırılır.

Viewer tarafının ayrıntısı — hangi dosyanın neyi yazdığı, paketleme yaşam
döngüsü, başarısız bir paketin nasıl teşhis edileceği —
[viewer-architecture.md](viewer-architecture.md) içindedir; burada
tekrarlanmaz.

## Viewer neden yeniden derlenmiyor?

Viewer sayfası bir derleme çıktısıdır ve kaydı derleme anında gömer. Eskiden
bu, kayda eklenen yeni bir yöntemin sayfada görünmesi için birinin
`python -m amsc.viewer.build` çalıştırmasını hatırlamasına bağlıydı — kimsenin
hata vermediği, yalnız yöntemin görünmediği sessiz bir adım.

Artık sayfa sunulduğunda açılışta `GET /api/methods` çağırır
(`amsc.viewer.server`), yanıtı gömülü kopyanın üzerine yazar ve değişmişse
yeniden çizer. Sunucu kaydı `amsc.chunking.registry`'ten okur, yani kütüphanede kayıtlı
olan neyse odur. Sonuç:

* **sunulan sayfa** (ürünün kullandığı yol, `start-demo.ps1`) her zaman
  günceldir, sayfa ne zaman derlenmiş olursa olsun;
* **dosyadan açılan sayfa** (araştırma derlemesi, sunucusuz) gömülü kopyayı
  kullanır — bir dosyanın taşıyabileceği tek şey odur;
* eski bir sunucu (rota yok) hiçbir şeyi bozmaz: istek başarısız olur ve
  gömülü kopya kalır.

Tutan test:
`tests/unit/chunking/test_methods_registry.py::test_a_page_built_before_the_method_existed_still_lists_it_when_served`.

## Depolar arası pin

`chat_rag` kütüphaneyi **değişmez bir commit'ten** kurar. Kütüphane değişikliği
konsola ancak pin güncellendiğinde ulaşır. Sha'yı elle kopyalamak gerekmez:

```powershell
# chunk deposunda: commit + push
git commit -am "feat(chunkers): add the fixed-window method"
git push

# chat_rag deposunda: pin'i ilerlet ve doğrula
python tools\promote_chunk_pin.py            # ../chunk HEAD'i
python tools\promote_chunk_pin.py --check    # yazmadan ne olacağını söyler
```

Komut chunk checkout'unu bulur, revizyonu çözer, **commit'lenmemiş veya
`git add` edilmemiş** bir çalışma ağacını reddeder (yeni bir chunker yeni bir
dosyadır; eklenmemiş bir dosya pin'in taşıyamayacağı tek şeydir), commit'in
bir uzak dalda bulunduğunu doğrular (yoksa temiz bir kurulum onu çekemez),
`requirements.txt` içindeki tek satırın yalnız sha'sını değiştirir ve
`tests/unit/test_amsc_pin.py`'i koşar. Testler düşerse dosyayı geri yazar.
Commit atmaz; atılacak `git` komutunu yazdırır.

## En küçük örnek

`src/amsc/chunking/example.py` çalışan, eksiksiz ve **kayıtlı olmayan** bir
yöntemdir: kopyalanmak için vardır ve beşinci bir ürün yöntemi bırakmadan
uzatma yolunun kanıtlanmasını sağlar. Bölümleme, başlıkları geçmeden ardışık
birimleri paylaşılan hedefe kadar paketler; elle hesaplanabilecek kadar
naiftir, bu yüzden testi beklenen `unit_ids` listesini doğrudan yazar.

Dosya olduğu gibi kopyalanabilir: importları (`from .chunk_method import …`)
ve kaydı (`FIXED_WINDOW = ChunkMethod(...)`) gerçek uzatma şeklidir, kütüphane
yüzeyi ve import döngüsü muhafızlarından geçer.

Bunu üründe görmek için: `chunking/example.py`'yi kopyalayın, bölümlemeyi
değiştirin, `ChunkMethod`'u `src/amsc/chunking/registry.py` içine import edip `_BUILTIN`
demetine ekleyin, testi yazın. Başka dosya yoktur.

## Ne koşulur

```powershell
# chunk deposunda
py -3.11 -m pytest tests/unit/chunking/test_methods_registry.py   # kayıt ve tüketici zinciri
py -3.11 -m pytest                                       # tüm süit
py -3.11 -m amsc.viewer.build --output artifacts\viewer-v3\index.html   # kabuk kurulur mu

# chat_rag deposunda
python tools\promote_chunk_pin.py                        # pin + doğrulama
python -m pytest -q tests/unit/test_chunker_extension.py # uzatma yolu, uçtan uca
```

Depolar arası değişikliğin sırası (commit → push → pin → test →
reproducibility) [chat_rag/docs/testing.md](../../chat_rag/docs/testing.md)
içindedir; sıra atlanırsa hata çok sonra ve daha az açık bir yerde çıkar.

## Deep Analysis neden farklıdır

Deep Analysis bir bölümleme fonksiyonu değil, bir **orkestrasyondur**:
Standard taban çizgisi → öneri modeli → deterministik seçici → çift yönlü
doğrulayıcı → durum ve rapor → tablo zenginleştirme → deterministik geri dönüş.
`amsc.deep.pipeline` bunu koşturur, `amsc.deep.arm` paketler. Kayıtta
`deep=True`, `partition=None`, `baseline="structure-only"` olarak tanımlıdır:
her katman onu listeler ve ayırt eder, ama `methods.partition("agentic", …)`
nedenini söyleyerek reddeder. Dış arayüz tek biçimlidir; iç yapı değil.

## Kayıt neyi garanti eder

* `key` ve `kind` benzersizdir; çakışma kayıt anında `ValueError`'dır.
* Bilinmeyen bir ad `UnknownMethod` ile, bilinen adları sayarak reddedilir.
* `needs_embedder` bildirmeyen bir yöntem için sınır modeli asla yüklenmez:
  çağıran tembel bir yükleyici verir, kayıt yalnız gerekirse çağırır.
* Dondurulmuş chunk benchmark'ının üç kolu bir sözleşmedir (`benchmark_arm`);
  yeni bir yöntem benchmark **konfigürasyonunda** bir kolun `kind`'ı olarak
  kullanılabilir, ama dondurulmuş kol kümesini değiştirmez.
* Analiz kaydı ile **indeksleme** kaydı ayrıdır: burada kayıtlı bir yöntem bir
  bilgi tabanının chunker'ı olmaz (`chat_rag/components/chunker/registry.py`).
