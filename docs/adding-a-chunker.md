# Yeni bir parçalama yöntemi eklemek

Bir parçalama yönteminin kimliği tek yerde tanımlıdır: `src/amsc/methods.py`.
Konsolun gönderdiği tel adı (`structure-only`), paketlenmiş `mapping.json`'ın
bildirdiği motor türü (`structure_first`), her ekranda görünen ürün adı
(`Standard`), tek cümlelik özet ve yeteneklerin (embedder gerekir mi, modele
danışır mı, benchmark kolu mu) hepsi oradaki bir `ChunkMethod` kaydıdır.
Viewer v3 builder'ı, Viewer v2 okuyucusu, chunk benchmark'ı, ilişki türeticisi
ve chat_rag konsolu listelerini bu kayıttan okur. Yeni bir yöntemin başka hiçbir
dosyaya adının yazılması gerekmez.

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
