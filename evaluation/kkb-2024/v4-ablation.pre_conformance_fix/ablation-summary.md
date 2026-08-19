# V4 Core Ablation — Frozen KKB 2024 Checkpoint

- Canonical SHA256: `2776742d5bddad7dcf2a03320dca36e6b384e2ba042ab99ccdecce61612720d5`
- Gold set: 15 `HIGH` topic boundaries; `REVIEW` annotations excluded from primary metrics.
- Primary metric: one-to-one ±1 content-unit boundary matching.
- Secondary metric: exact one-to-one boundary matching.
- Parameter policy: frozen PoC values; no checkpoint tuning.

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
| A3 | 241 | 6 / 661 / 799 / 1126 | 3 (1.2448%) | 153 (63.7500%) | 18 (7.5000%) | 171 (71.2500%) |
| A4 / Full core V4 | 241 | 6 / 664 / 802 / 1126 | 3 (1.2448%) | 153 (63.7500%) | 18 (7.5000%) | 171 (71.2500%) |

## V4 provenance metrikleri

| Ablation | Semantic boundaries | Structural-assisted | Merge proposals | Accepted | Rejected | Removed |
|---|---:|---:|---:|---:|---:|---:|
| A0 / V3 | 70 | 0 | 0 | 0 | 0 | 0 |
| A1 | 70 | 0 | 0 | 0 | 0 | 0 |
| A2 | 70 | 0 | 0 | 0 | 0 | 0 |
| A3 | 69 | 0 | 11 | 3 | 8 | 3 |
| A4 / Full core V4 | 69 | 0 | 15 | 5 | 10 | 5 |

A3 rejection reasons: `semantic_cohesion_not_met=7`,
`combined_hard_cap_exceeded=1`. A4 rejection reasons:
`semantic_cohesion_not_met=7`, `combined_hard_cap_exceeded=2`,
`overlapping_proposal_conflict=1`.

Full extraction içinde 14 V4 atomic split fragment provenance kaydı vardır; bunlar 7
oversized table source unit'inden gelir. List/visual forced-split davranışı deterministic
unit testlerle kapsanır; bu dokümanda bu türlerde hard-cap aşımı oluşmamıştır.

## Yorum ve frozen success gate

- A1 threshold-relative selection tek başına iki F1 metriğinde de precision artışı sağladı,
  fakat small-chunk ve all-fallback oranlarını yükseltti.
- A2, A0 ile aynı sonucu verdi. Structural evidence bulunmasına rağmen frozen adaptive
  threshold'lar `semantic_floor=0.12` altında kaldığı için bounded formula threshold'u
  gevşetmedi; structural-assisted selected boundary oluşmadı.
- A3 üç merge kabul ederek short-chunk sayısını yarıya indirdi ve bir false-positive'i
  kaldırdı.
- A4 beş merge kabul etti; A0'a göre ±1 F1 `0.5517 → 0.5926`, exact F1
  `0.4138 → 0.4444`, small-chunk ratio `2.4590% → 1.2448%` oldu.
- Frozen success gate bütünüyle geçmedi. Primary F1 ve small-chunk koşulu geçti; ancak
  all-fallback ratio `71.1934% → 71.2500%` ve size-fallback ratio
  `63.3745% → 63.7500%` ile çok az arttı. Fallback count `173 → 171` düşse de gate oran
  üzerinden yorumlanmıştır.

İki accepted merge özellikle manuel inceleme gerektirir: kısa rapor başlığının finansal
rapor metnine bağlandığı boundary 917 ve finansal tablo bölümünün “bilanço tarihinden
sonraki olaylar” paragrafına bağlandığı boundary 1327. Structure mismatch frozen tasarım
gereği veto değildir; bu kayıtlar gold region dışında olsa da semantic-cohesion kuralının
sınırda kabul ettiği örneklerdir.
