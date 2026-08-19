# KKB 2024 Frozen Canonical Edge-Case Preview

Bu örnekler `data/kkb-2024.units.jsonl` içinden aynen alınmıştır. Heading type/level, section path veya metin üzerinde manuel düzeltme yapılmamıştır.

## 1. Missed heading — p-00906

- Page: 40 / right
- Canonical type: paragraph
- Section path: `**21. RISK MERKEZI HIZMETLERI VE VERI YÖNETIMI** Uluslararası standartlarda veri yönetimi`
- Text: `RİSK MERKEZİ ÜRÜN YÖNETİMİ VE GELİŞTİRME BİRİMİ`

## 2. Missed display heading — p-00929

- Page: 41 / left
- Canonical type: paragraph
- Section path: `PROJE YÖNETİMİ BİRİMİ`
- Text: `Proje yönetiminde şeffaflık`

## 3. Cross-column sentence continuation — p-00928 → p-00930

- Page: 41 / left → right
- Left ending: `...Bu çözümle,`
- Right opening: `maliyet öngörüleri ve kaynakların projelerle eşleşmesindeki sapmaların en aza indirilmesi hedeflenmektedir.`
- `p-00929` display text, canonical sequence içinde bu iki paragraph arasındadır.

## 4. False heading — h-01039

- Page: 48 / left
- Canonical type/level: heading / H2
- Text: `KKB, Genç Yetenekler Programı ile geleceğin liderlerini yetiştirmekte ve istihdama katkı sağlamaktadır.`

## 5. Text-bearing visual — v-00954

- Page: 42 / right
- Canonical type: paragraph; source `content_origin=visual`
- Preserved values include: `%11`, `%27`, `%5`, `%25`, `%60`, `111 Madde`, `%30`.
- The complete picture text is one atomic canonical unit.

## 6. FTE/TL visual — v-00958

- Page: 43 / left
- Canonical type: paragraph; source `content_origin=visual`
- Text:

  ```text
  Kazanımlar
  FTE: TL:
  313,5
  287,6
  Planlanan Planlanan (Milyon TL)
  17 FTE
  273,2
  Gerçekleşen Gerçekleşen (Milyon TL)
  8,7 FTE 313,5
  ```

## 7. CSR numeric visual — v-01197

- Page: 54 / left
- Canonical type: paragraph; source `content_origin=visual`
- Preserved values include active volunteer `204`, project count `19`, application count `283`, total added value `649.306 TL`, and `2023/2024` chart values.

## 8. Large financial table — t-01234

- Page: 61 / right
- Canonical type: table
- Character length: 4,242
- Begins with the financial statement contents table and exercises downstream hard-cap forced splitting.

## 9. Long tax paragraph — p-01770

- Page: 79 / left
- Canonical type: paragraph
- Character length: 4,663
- A long inflation-accounting/tax narrative used to exercise downstream token pressure without changing parser output.
