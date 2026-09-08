# Yeni bir parçalama yöntemi eklemek

**Yeni bir chunker = `src/amsc/chunking/plugins/` altına bir `.py` dosyası.**
Başka hiçbir dosyaya dokunulmaz: import eklenmez, liste güncellenmez, config
yazılmaz. `amsc.chunking.discovery` bu dizini import eder ve içinde bildirilen
her `ChunkMethod`'u kaydeder; Viewer, konsol, paketleyici ve benchmark
listelerini o kayıttan okur.

Bir yöntemin kimliği tek bir `ChunkMethod` kaydıdır: konsolun gönderdiği tel
adı (`structure-only`), paketlenmiş `mapping.json`'ın bildirdiği motor türü
(`structure_first`), her ekranda görünen ürün adı (`Standard`), tek cümlelik
özet, satırlarının hangi alanları taşıdığı (`Capability`) ve yetenekler
(embedder gerekir mi, modele danışır mı, benchmark kolu mu).

## İki adım

1. **Dosyayı yazın.** `src/amsc/chunking/plugins/<yöntem>.py`:

   ```python
   # src/amsc/chunking/plugins/semantic_v2.py
   from ..contract import Capability, Chunk, chunker

   @chunker(
       key="semantic-v2",              # tel adı / Viewer kol adı
       label="Semantic V2",            # ürün adı, her yerde bu
       summary="Anlam kaymasının en yüksek olduğu yerden keser.",
       capabilities=[Capability.PAGES, Capability.HEADINGS],   # isteğe bağlı
   )
   def semantic_v2(units, *, counter, budget, **options):
       for parca in ...:
           yield Chunk(text=parca.metin, unit_ids=[u.unit_id for u in parca.birimler])
   ```

2. **Test yazın.** `tests/unit/chunking/` altında.

`kind` yazılmazsa anahtardan türetilir (`semantic-v2` → `semantic_v2`).

## Sözleşme: ne vermek zorundasınız, ne türetilir

Sözleşmenin tamamı [`chunking/contract.py`](../src/amsc/chunking/contract.py)
içindedir. Daha önce sekiz anahtarlı bir sözlük elle kurulurdu ve bu
zorunluluk hiçbir yerde yazılı değildi — üç ayrı tüketicinin `row[...]`
okumasından ibaretti. Artık üç grup var.

**Çekirdek — sizin verdiğiniz.** Her parça için iki şey: **metin** ve metnin
**nereden geldiği**. Köken (provenance) tahmin edilmez, çünkü tahmin edilecek
tek yöntem metni aramaktır ve doküman aynı paragrafı tekrarladığı anda yanlış
paragrafa bağlanır. İki köken biçimi:

| Biçim | Ne yazarsınız | Ne zaman |
|---|---|---|
| `unit_ids=[...]` | paketlediğiniz canonical birimlerin id'leri | birimler üzerinde çalışan yöntemler |
| `span=(start, end)` | size verilen **render** içindeki karakter aralığı | render üzerinde çalışan yöntemler (`Capability.OFFSETS`) |

Satırın çekirdek dört alanı — `chunk_id`, `text`, `unit_ids`, `token_count` —
her yöntemde vardır; her tüketicinin `row[...]` ile okuduğu tam olarak bunlardır.

**Türetilen — çerçevenin hesapladığı.** `chunk_id` (doküman + yöntemin infix'i),
`token_count` (paylaşılan sayaç), `span`den `unit_ids`, ve aşağıdaki her
yetenek alanı: `pages`, `section_paths`, `heading`, `split_strategies`,
`char_start`/`char_end`. `span` → birim çözümü **aritmetiktir**: render'ın
kendi span'leriyle kesişim alınır — `amsc.chunking.mapping`'in `offset`
basamağının aynısı. Hiçbir yerde metin araması yoktur.

**Yetenekler — bildirdiğiniz.** `capabilities` satırlarınızın hangi isteğe
bağlı alanları taşıdığını söyler:

| Capability | Satıra koyduğu alan |
|---|---|
| `PAGES` | `pages` |
| `HEADINGS` | `heading` |
| `HIERARCHY` | `section_paths` |
| `PROVENANCE` | `split_strategies` |
| `OFFSETS` | `char_start`, `char_end` (+ `document` size verilir) |
| `SEMANTIC_SCORES` | `scores` |
| `CUSTOM_METADATA` | yönteme özel ne varsa, olduğu gibi |

Hiçbir şey yazmazsanız varsayılan dördü alırsınız (`PAGES`, `HEADINGS`,
`HIERARCHY`, `PROVENANCE`) — yani yapısal ailenin hep ürettiği satır. Bildirmek
iş değildir: alanlar zaten verdiğiniz kökenden türetilir.

**Bir yeteneği bildirmemek bir eksiklik değildir.** İsteğe bağlı alanların her
tüketicisi onları savunmacı okur (`row.get(...)`), ve
`test_chunk_contract.py::test_a_minimal_methods_rows_are_read_by_every_consumer`
bunu bağlar. Başka bir chunker `pages` üretiyor diye sizinkinin de üretmesi
gerekmez.

**Kendi alanlarınız korunur.** `CUSTOM_METADATA` bildirip `Chunk(...,
extra={"benim_skorum": 0.4})` yazın; alan satıra olduğu gibi geçer. Bildirmeden
yazarsanız sınırda hata alırsınız — bu, uzatma ile sızıntı arasındaki farktır.

## Çerçeve size ne verir

Partition **yalnız adını yazdığınız** şeyleri alır:

| Ad | Nedir |
|---|---|
| `counter` | paylaşılan token sayacı |
| `budget` | paylaşılan bütçe (`min_tokens`, `target_tokens`, `soft_max_tokens`, `hard_max_tokens`) |
| `boundary_embedder` | `needs_embedder=True` ise cümle gömme modeli |
| `respect_semantic_roles` | bölüm makinesi bayrağı |
| `document` | `Capability.OFFSETS` bildirenlere: render edilmiş doküman ve her birimin karakter aralığı |
| yöntemin `options` anahtarları | canlı koşunun varsayılanları |

`def chunk(units, *, counter)` eksiksiz bir partition'dır; okumadığınız bir
bütçe size verilmez. `**options` yazarsanız hepsini alırsınız.

Her yöntem aynı bütçeyle koşar ki karşılaştırma yalnız sınırların nereye
düştüğünü karşılaştırsın.

## Hata nerede çıkar

Sözleşmeyi karşılamayan bir satır `amsc.chunking.registry.partition` içinde,
yöntemi ve parçayı adıyla söyleyen bir `ContractError` ile düşer — üç tüketici
sonra bir `KeyError` olarak değil. Kökensiz parça, tanınmayan bir `unit_id`,
bildirilmemiş bir alan, çakışan `chunk_id`: hepsi orada.

Kontrol **her yöntem için** koşar; dondurulmuş üç motor da kendi
bildirimlerine karşı doğrulanır, yani bir motorun şekli sessizce kayamaz.

## Uçtan uca: kayıttan sonra ne oluyor?

Dosya yazıldığında yöntem **kendiliğinden** her katmanda görünür. Her satır,
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

Dosya olduğu gibi kopyalanabilir: importu (`from .contract import Chunk,
chunker`) ve bildirimi gerçek uzatma şeklidir, kütüphane yüzeyi ve import
döngüsü muhafızlarından geçer.

Bunu üründe görmek için: `chunking/example.py`'yi
`src/amsc/chunking/plugins/` altına kopyalayın, bölümlemeyi değiştirin, testi
yazın. Başka dosya yoktur. (Şablonun kendisi dizinin *dışında* durur; kayıtlı
olmayan bir örnek olarak, beşinci bir ürün yöntemi bırakmadan uzatma yolunun
test edilebilmesi için.)

## Ne koşulur

```powershell
# chunk deposunda
py -3.11 -m pytest tests/unit/chunking/test_chunk_contract.py     # keşif ve sözleşme
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
