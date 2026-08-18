# Chunklama PoC

Bu depo, KKB dokümanlarında konu geçişlerini LLM/API çağrısı olmadan bulmayı amaçlayan **Adaptive Multi-Signal Semantic Chunking** PoC'sini içerir.

Nihai çözüm V4'tür; depoda şu anda yalnızca **V1** uygulanmıştır:

- canonical JSONL validation,
- heading exclusion/attachment,
- embedding tokenizer'ından bağımsız `TokenCounter`,
- E5 `query: ` prefix'i ve uzun metinler için fragment pooling,
- cache'li semantic-boundary embedding,
- komşu `1↔1` cosine semantic shift,
- sabit threshold ve interval boundary selection,
- tam render edilmiş metin üzerinde configured-token-counter hard cap,
- açıklanabilir chunk/boundary provenance.

## Kurulum

```powershell
py -3.11 -m pip install -e ".[dev]"
```

Gerçek `multilingual-e5-base` modelini kullanmak için:

```powershell
py -3.11 -m pip install -e ".[model]"
```

## Kullanım

```powershell
py -3.11 -m amsc.cli validate `
  --input tests/fixtures/sample.units.jsonl

py -3.11 -m amsc.cli chunk `
  --input data/kkb-2024.units.jsonl `
  --config configs/v1.yaml `
  --output artifacts/kkb-2024-v1
```

`chunk` komutu model dosyalarını ilk kullanımda yerel ortama indirir. PDF parsing bu projenin kapsamında değildir; komut hazır canonical IDP/JSONL çıktısı bekler.

## Token limiti notu

V1'de `hard_max_tokens=1126`, varsayılan `tiktoken:cl100k_base` sayacına göre uygulanır. KKB production limitinin hangi tokenizer'a göre tanımlandığı bilinmediğinden bu, **production-tokenizer uyumluluk garantisi değildir**. Çıktı bu durumu `hard_cap_semantics=configured_poc_counter_only` alanıyla açıkça taşır.

`160/700/900`, `fixed_threshold=0.20` ve `0.80/0.20` seçim ağırlıkları optimize edilmiş değerler değil, PoC başlangıç parametreleridir.

## Dokümanlar

- [Bağlam ve kararlar](docs/kararlar-ve-baglam.md)
- [Seçilen çözüm](docs/secilen-cozum.md)
- [V1 implementasyon planı ve mimarisi](docs/implementasyon-plani.md)

## Test

```powershell
py -3.11 -m pytest
```

Testler model indirmeden deterministic backend/tokenizer doubles kullanır. Gerçek `cl100k_base` sayacı ayrıca unit test kapsamındadır.

