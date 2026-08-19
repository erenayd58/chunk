# V4 Core Ablation — Frozen KKB 2024 Checkpoint

- Canonical SHA256: `2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5`
- Gold set: 15 `HIGH` topic boundaries; `REVIEW` annotations excluded from primary metrics.
- Primary metric: one-to-one ±1 content-unit boundary matching.
- Secondary metric: exact one-to-one boundary matching.
- Parameter policy: frozen PoC values; no checkpoint tuning.
- Result status: post-conformance-fix authoritative run. Previous provisional outputs
  are preserved under `../v4-ablation.pre_conformance_fix/`.

## Boundary metrics

| Ablation | Exact P | Exact R | Exact F1 | ±1 P | ±1 R | ±1 F1 |
|---|---:|---:|---:|---:|---:|---:|
| A0 / V3 | 0.4286 | 0.4000 | 0.4138 | 0.5714 | 0.5333 | 0.5517 |
| A1 | 0.4615 | 0.4000 | 0.4286 | 0.6154 | 0.5333 | 0.5714 |
| A2 | 0.4286 | 0.4000 | 0.4138 | 0.5714 | 0.5333 | 0.5517 |
| A3 | 0.4615 | 0.4000 | 0.4286 | 0.6154 | 0.5333 | 0.5714 |
| A4 / Full core V4 | 0.5000 | 0.4000 | 0.4444 | 0.6667 | 0.5333 | 0.5926 |

A4, A0'a göre primary true-positive sayısını değiştirmeden false-positive sayısını
6'dan 4'e düşürdü. Exact false-positive sayısı 8'den 6'ya düştü.

## Chunk ve fallback metrikleri

| Ablation | Chunks | Token min/med/P90/max | `<160` | Size fallback | Hard fallback | All fallback |
|---|---:|---|---:|---:|---:|---:|
| A0 / V3 | 244 | 6 / 659.5 / 799 / 1126 | 6 (2.4590%) | 154 (63.3745%) | 19 (7.8189%) | 173 (71.1934%) |
| A1 | 246 | 6 / 660.5 / 802 / 1126 | 8 (3.2520%) | 154 (62.8571%) | 21 (8.5714%) | 175 (71.4286%) |
| A2 | 244 | 6 / 659.5 / 799 / 1126 | 6 (2.4590%) | 154 (63.3745%) | 19 (7.8189%) | 173 (71.1934%) |
| A3 | 242 | 6 / 660.5 / 799 / 1126 | 4 (1.6529%) | 153 (63.4855%) | 19 (7.8838%) | 172 (71.3693%) |
| A4 / Full core V4 | 244 | 6 / 662 / 802 / 1126 | 6 (2.4590%) | 153 (62.9630%) | 21 (8.6420%) | 174 (71.6049%) |

## V4 provenance metrikleri

| Ablation | Semantic boundaries | Structural-assisted | Merge proposals | Accepted | Rejected | Removed |
|---|---:|---:|---:|---:|---:|---:|
| A0 / V3 | 70 | 0 | 0 | 0 | 0 | 0 |
| A1 | 70 | 0 | 0 | 0 | 0 | 0 |
| A2 | 70 | 0 | 0 | 0 | 0 | 0 |
| A3 | 69 | 0 | 11 | 2 | 9 | 2 |
| A4 / Full core V4 | 69 | 0 | 15 | 2 | 13 | 2 |

A3 rejection reasons: `original_boundary_hard_limit_fallback=8`,
`semantic_cohesion_not_met=1`. A4 rejection reasons:
`original_boundary_hard_limit_fallback=12`, `semantic_cohesion_not_met=1`.

Accepted boundaries are the same in A3 and A4:

- boundary 922, original reason `size_fallback`;
- boundary 1327, original reason `adaptive_semantic_boundary`.

Accepted `hard_limit_fallback` merge count is zero.

Full extraction içinde 14 V4 atomic split fragment provenance kaydı vardır; bunlar 7
oversized table source unit'inden gelir. List/visual forced-split davranışı deterministic
unit testlerle kapsanır; bu dokümanda bu türlerde hard-cap aşımı oluşmamıştır.

## Yorum ve frozen success gate

- A1 threshold-relative selection tek başına iki F1 metriğinde de precision artışı sağladı,
  fakat small-chunk ve all-fallback oranlarını yükseltti.
- A2, A0 ile aynı sonucu verdi. Structural evidence bulunmasına rağmen frozen adaptive
  threshold'lar `semantic_floor=0.12` altında kaldığı için bounded formula threshold'u
  gevşetmedi; structural-assisted selected boundary oluşmadı.
- A3 iki merge kabul ederek short-chunk sayısını düşürdü ve bir false-positive'i
  kaldırdı.
- A4 iki merge kabul etti; A0'a göre ±1 F1 `0.5517 → 0.5926`, exact F1
  `0.4138 → 0.4444` oldu. Small-chunk ratio A0 ile aynı `2.4590%` değerindedir.
- Frozen success gate bütünüyle geçmedi. Primary F1 koşulu geçti; post-fix small-chunk
  improvement kalmadı ve all-fallback ratio `71.1934% → 71.6049%` arttı.

Boundary 1327 özellikle manuel inceleme gerektirir: finansal tablo bölümü “bilanço
tarihinden sonraki olaylar” paragrafına bağlanmıştır. Structure mismatch frozen tasarım
gereği veto değildir; bu kayıt gold region dışında olsa da semantic-cohesion kuralının
sınırda kabul ettiği bir örnektir. Provisional koşuda kabul edilen hard-limit boundaries
917, 925 ve 1307 conformance fix sonrasında deterministik olarak reddedilir.
