# Yeni bir parçalama yöntemi eklemek

Bir parçalama yönteminin kimliği tek yerde tanımlıdır: `src/amsc/methods.py`.
Konsolun gönderdiği tel adı (`structure-only`), paketlenmiş `mapping.json`'ın
bildirdiği motor türü (`structure_first`), her ekranda görünen ürün adı
(`Standard`), tek cümlelik özet ve yeteneklerin (embedder gerekir mi, modele
danışır mı, benchmark kolu mu) hepsi oradaki bir `ChunkMethod` kaydıdır.
Viewer v3 builder'ı, Viewer okuyucusu (`amsc.viewer_corpus`), chunk benchmark'ı,
ilişki türeticisi ve chat_rag konsolu listelerini bu kayıttan okur. Yeni bir
yöntemin başka hiçbir dosyaya adının yazılması gerekmez -- Viewer'a özel bir
liste de yoktur; sınırın tamamı `docs/viewer-architecture.md`'de.

## Üç adım

1. **Bölümleme fonksiyonunu yazın.** Girdi canonical birimler, çıktı yapısal
   satır şeması: `chunk_id`, `text`, `unit_ids`, `token_count`, `pages`,
   `section_paths`, `heading`, `split_strategies`. İmza:

   ```python
   def partition_x(units, *, counter, budget, boundary_embedder=None,
                   respect_semantic_roles=False, **options) -> PartitionResult
   ```

   `budget` paylaşılan token bütçesidir (`min_tokens`, `target_tokens`,
   `soft_max_tokens`, `hard_max_tokens`); her yöntem aynı bütçeyle koşar ki
   karşılaştırma yalnız sınırların nereye düştüğünü karşılaştırsın.
   `src/amsc/example_chunker.py` eksiksiz, en küçük örnektir — kopyalayın.

2. **Kaydedin.** `src/amsc/methods.py` içindeki `_BUILTIN` demetine bir
   `ChunkMethod` ekleyin:

   ```python
   ChunkMethod(
       key="fixed-window",            # tel adı / Viewer kol adı
       kind="fixed_window",           # motor türü; benzersiz olmalı
       label="Sabit Pencere",         # ürün adı, her yerde bu
       summary="Ardışık birimleri sabit pencerelerde paketler.",
       partition=partition_fixed_window,
       needs_embedder=False,          # True ise `boundary_embedder` verilir
       options={"max_units": 3},      # canlı koşunun varsayılanları
   )
   ```

3. **Test edin.** `tests/unit/test_methods_registry.py` içindeki
   `test_the_example_partition_is_predictable` örnektir: elle hesaplanabilir
   bir girdi, beklenen `unit_ids` listesi.

Bu üç dosyadan başka hiçbir yere dokunulmaz. Konsol (chat_rag) kütüphaneyi
sabitlenmiş bir commit'ten kurar; yöntemin üründe görünmesi için chunk
commit'lendikten sonra `chat_rag/requirements.txt` içindeki `amsc-poc` pin'i
o commit'e güncellenir — konsol tarafında başka değişiklik yoktur.

## Uçtan uca: kayıttan sonra ne oluyor?

Üç adım bittiğinde yöntem **kendiliğinden** her katmanda görünür. Her satır,
o katmanın adı nereden okuduğunu söyler — hiçbirine elle yazılmaz:

| Katman | Nasıl öğreniyor | Sonuç |
|---|---|---|
| Kütüphane | `methods.partition(key, …)` | yöntem canonical birimler üzerinde koşar |
| Konsol arka ucu (`chat_rag`) | `components/viewer/methods.py`, `amsc.methods`'i okur ve yalnız *bu makinede çalışabilir mi*, sıra ve varsayılan bilgisini ekler | `GET /api/demo/methods` yöntemi (ya da neden çalışamadığını) döner |
| Konsol ön yüzü | yükleme formu yöntem listesini aynı uçtan çeker | yükleme sırasında seçilebilir olur |
| Paketleyici | `components/viewer/analysis.py` seçilen her yöntemi tek canonical üzerinde koşturur | `artifacts/viewer-live/<doc>/variants/<key>/` |
| Viewer v3 | `viewer_v3` builder'ı `methodOrder` / `methodLabels` / `methodMeta`'yı kayıttan üretir; sayfa davranışı ada değil `methodMeta` bayraklarına (`deep`, `baseline`) bakar | kolon olarak seçilebilir, kendi rengiyle çizilir |
| Viewer okuyucusu | `amsc.viewer_corpus` kolu `kind`'ıyla kabul eder | payload'da kol olarak taşınır |
| Benchmark | benchmark konfigürasyonunda bir kolun `kind`'ı olarak yazılabilir | dondurulmuş kol kümesi değişmeden karşılaştırmaya girer |
| Debug / karşılaştırma | Viewer'ın Debug sekmesi ve ayrışma gezinmesi kolları genel olarak işler | sınırların nerede ayrıştığı görünür |

Bu zincirin tamamı tek testle tutulur:
`tests/unit/test_methods_registry.py::test_a_registered_method_reaches_every_consumer_with_no_other_edit`.
Bir tüketici kaydı okumayı bırakırsa orada kırılır.

Viewer tarafının ayrıntısı — hangi dosyanın neyi yazdığı, paketleme yaşam
döngüsü, başarısız bir paketin nasıl teşhis edileceği —
[viewer-architecture.md](viewer-architecture.md) içindedir; burada
tekrarlanmaz.

## En küçük örnek

`src/amsc/example_chunker.py` çalışan, eksiksiz ve **kayıtlı olmayan** bir
yöntemdir: kopyalanmak için vardır ve beşinci bir ürün yöntemi bırakmadan
uzatma yolunun kanıtlanmasını sağlar. Bölümleme, başlıkları geçmeden ardışık
birimleri paylaşılan hedefe kadar paketler; elle hesaplanabilecek kadar
naiftir, bu yüzden testi beklenen `unit_ids` listesini doğrudan yazar.

Kaydı da aynı dosyada hazır durur:

```python
FIXED_WINDOW = ChunkMethod(
    key="fixed-window",
    kind="fixed_window",
    label="Sabit Pencere",
    summary="Ardışık birimleri sabit sayıda pencereler halinde paketler; başlıkları geçmez.",
    partition=partition_fixed_window,
    options={"max_units": 3},
)
```

Bunu üründe görmek için: `example_chunker.py`'yi kopyalayın, bölümlemeyi
değiştirin, `ChunkMethod`'u `amsc/methods.py` içindeki `_BUILTIN` demetine
ekleyin, testi yazın. Başka dosya yoktur.

## Ne koşulur

```powershell
# chunk deposunda
py -3.11 -m pytest tests/unit/test_methods_registry.py   # kayıt ve tüketici zinciri
py -3.11 -m pytest                                       # tüm süit
py -3.11 -m amsc.viewer_v3 --output artifacts\viewer-v3\index.html   # kabuk kurulur mu
```

Sonra konsol tarafı — ama yalnız pin bump'tan sonra, çünkü `chat_rag`
kütüphaneyi sabitlenmiş bir commit'ten kurar. Depolar arası değişikliğin
sırası (commit → push → pin → test → reproducibility)
[chat_rag/docs/testing.md](../../chat_rag/docs/testing.md) içindedir; sıra
atlanırsa hata çok sonra ve daha az açık bir yerde çıkar.

## Deep Analysis neden farklıdır

Deep Analysis bir bölümleme fonksiyonu değil, bir **orkestrasyondur**:
Standard taban çizgisi → öneri modeli → deterministik seçici → çift yönlü
doğrulayıcı → durum ve rapor → tablo zenginleştirme → deterministik geri dönüş.
`amsc.deep_pipeline` bunu koşturur, `amsc.deep_arm` paketler. Kayıtta
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
