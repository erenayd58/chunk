# Viewer v2 — Chunking + RAG PoC ürünü

Viewer v2, bu repodaki chunking araştırmasını tek bir sunulabilir üründe toplar:
dört chunking yöntemi, aynı sayfanın yöntemler arasında karşılaştırması, her sınırın
insan diliyle nedeni, gerçek bir "dokümana sor" deneyimi, mühendislik için karar izi
ve ölçümler. Tek bir HTML dosyasıdır; yalnız canlı sohbet için yerel sunucu gerekir.

## Sekmeler

| Sekme | Soru | İçerik |
|---|---|---|
| **Sunum** | Ne yaptık, fark ne? | Markdown / Hybrid / Structure-Only (Standard) / Agentic Chunker (Deep Analysis) kartları; Standard → Deep sonuç şeridi (chunk, koku, regresyon, LLM çağrısı, süre, Hit@5); sayfa okuyucu — tek kol ya da iki kolun aynı sayfada yan yana karşılaştırması; her chunk şeridinde sınır nedeni ve Deep kararı ("kalite kuralı sınırı taşıdı: lead-in devamıyla kaldı", "LLM önerisi doğrulandı", "verifier reddetti", "temsil tavanı") |
| **Sorgu** | Kullanınca nasıl çalışıyor? | *Dokümana Sor*: doküman + yöntem seç, doğal dilde sor → dense + BM25 (RRF) retrieval → aynı bölümün devam parçalarıyla bağlam → kaynaklı cevap; kaynak kartları (başlık, bölüm, sayfa, yöntem, kullanıldı mı), karta tıklayınca chunk metni ve "Sunum'da göster"; "Tüm yöntemlerle karşılaştır" aynı soruyu dört yöntemle koşar. *Gold sorgular*: frozen benchmark'ın sorgu-bazlı görünümü (çevrimdışı) |
| **Debug** | Sistem bu kararı neden verdi? | Canonical unit'ler (tip, rol, seviye, section path), her koldaki chunk/fragment/offset/method eşlemesi, parser bulguları, hard cap üstü unit'ler (temsil tavanı), unit inspector'da bölümün Deep karar izi (Standard → deterministik → final kesimler, kaldırılan kokular, LLM önerileri ve verifier kararları); bölüm kararları tablosu (durum filtresiyle) |
| **Benchmark** | Ölçümlerde sonuç ne? | Frozen benchmark v5 (üç kol) değişmeden; ayrı **Deep Analysis paneli**: koku tablosu (S→D, Δ), chunk_quality tablosu, retrieval (frozen değer kopya, Deep yeniden skorlandı), sınır kökeni, LLM çağrısı/verifier/fallback, süre, token ve maliyet tahmini, dürüst yorum; dokümanlar arası sözleşme tablosu |

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
py -3.11 -m amsc.viewer_server --viewer artifacts/viewer-v2/index.html --config configs/rag-poc.yaml --warm
# → http://127.0.0.1:8765/
```

`index.html` dosya olarak açıldığında Sunum / Debug / Benchmark / gold sorgular çalışır;
Sorgu sekmesi sunucu yoksa bunu açıkça söyler ve komutu gösterir.

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
