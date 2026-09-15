# Vision48 Gold Benchmark v1

Amaç: **mevcut motorların hangisinin güçlü/zayıf olduğunu ölçmek**. Bu klasör eğitim yapmaz; eğitim verisi üretmez; ağırlık değiştirmez.

## Güvenlik kuralı

- `main`, production ve mevcut model ağırlıkları değiştirilmez.
- Gold veriler eğitimden fiziksel/mantıksal olarak ayrı tutulur.
- DENTEX ve OralXrays-9, Liodon/YOLO26 ile eğitim çakışması nedeniyle gold'a alınmaz.
- `kaggle31` ve `zenodo14` mevcut training katalogunda bulunduğu için aynı hedeflerde bağımsız gold olarak kullanılmaz.
- Bir dataset bir sınıfı etiketlemiyorsa, o sınıfta “yok” kabul edilmez.
- Generic etiketler spesifik Vision48 subtype'a çevrilmez.

## İlk kaynaklar

1. **InReDD-PAN924** — en değerli genel gold adayımız. 924 panoramik; üç dentomaksillofasiyal radyolog, yaklaşık 10 yıllık deneyim, iki okuyucu + üçüncü okuyucuyla zorunlu konsensus. FDI ve tooth-level condition etiketleri var. Erişim için PhysioNet credential + DUA + yazar onayı gerekiyor.
2. **Hanoi periapical** — 3,926 orijinal pozitif panoramik; üç deneyimli diş hekimi; lezyon kutuları ve PAI sınıfları. Sadece orijinal görüntüler benchmarka girer, augmentation kopyaları girmez.
3. **BoneLoss-PAN769** — periodontal bone-loss geometrisi için uzman landmark referansı; erişim kısıtlı.
4. **ToothPix 8655** — 20 dental imaging uzmanı tarafından pixel-level anotasyon; DUA ile kısıtlı erişim; geniş dış doğrulama adayı.
5. **Tufts 1000** — uzman teeth/abnormality anotasyonları; tam label sözlüğü görülmeden canonical eşleme yapılmaz.
6. **DentalOPG-1550** — ikincil/image-level tarama kaynağı; lokalizasyon gold'u sayılması için released annotation formatı doğrulanmalı.

> Not: MOPG-7'nin 3 ve 4 sürümleri 15 Eylül 2026 itibarıyla Mendeley sayfasında “author request” ile kaldırılmış göründüğü için v1 gold bağımlılığı yapılmadı.

## Normalized gold satırı

Her satır JSONL:

```json
{
  "image_id": "source:123",
  "source": "inredd_pan924",
  "image_path": "/gold/images/123.jpg",
  "annotations": [
    {
      "finding_code": "CARIES",
      "bbox_xyxy": [100, 200, 160, 270],
      "raw_label": "C",
      "annotation_quality": "forced_consensus_radiologists"
    }
  ],
  "exhaustive_codes": ["CARIES", "CROWN"]
}
```

`exhaustive_codes` kritik: sadece o datasetin gerçekten eksiksiz etiketlediği sınıflarda unmatched prediction `FP` sayılır. Böylece kısmi anotasyonlu veri yanlış şekilde motoru cezalandırmaz.

## Kullanım

InReDD dosyaları erişildikten sonra:

```bash
python benchmark/vision48_gold/normalize_gold.py inredd \
  --coco /data/inredd/mouth_and_teeth_labels.json \
  --images /data/inredd/images \
  --out /gold/inredd.jsonl
```

Hanoi:

```bash
python benchmark/vision48_gold/normalize_gold.py hanoi \
  --xml /data/hanoi/ImageAnnots \
  --images "/data/hanoi/Original JPG Images" \
  --out /gold/hanoi.jsonl
```

Mevcut motorların prediction JSONL çıktısı hazır olunca:

```bash
python benchmark/vision48_gold/evaluate_existing.py \
  --gold /gold/inredd.jsonl \
  --pred /gold/predictions_inredd.jsonl \
  --conf 0.50 \
  --iou 0.25 \
  --out /gold/report_inredd.json
```

Çıktı her canonical bulgu için TP/FP/FN, precision, recall ve F1 verir. Bu rapor **eğitim öncelik sırasını** belirlemek için kullanılır; model otomatik olarak değiştirilmez.

## V1 kapsam gerçeği

48 sınıfın tamamında bağımsız, uzman etiketli ve erişilebilir gold veri henüz yok. `source_catalog.py` her sınıfı `exact / partial / gap` olarak ayırır. Gap olan sınıfa “iyi” ya da “kötü” etiketi verilmez; veri bulunana veya uzman doğrulaması yapılana kadar `UNMEASURED` kalır.
