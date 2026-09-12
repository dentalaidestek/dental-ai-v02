# Dental AI Vision 48 — geliştirme dalı

Bu belge `work/vision48-3d-ready` dalının gerçek durumunu gösterir. Production deploy değildir.

## Production koruması

- `main` değiştirilmedi.
- Render servisleri `main` dalını izlediği için bu dal production'a deploy edilmez.
- Runtime smoke/klinik doğrulama ayrıca yapılacak.

## 48/48 motor uygulama kapsamı

`vision_service/motors/registry48.py` içinde katalogdaki **48 bulgunun tamamı** için çalışan bir inference stratejisi tanımlıdır. Stratejiler üç türdür:

1. hazır/doğrudan checkpoint,
2. birden fazla motor çıktısını birleştiren composed motor,
3. FDI/anatomi + görüntü geometrisinden türetilen CV motoru.

Hiçbir katalog kaydı placeholder/TODO olarak bırakılmaz. Bu, 48 bulgunun yazılım motorunun hazır olduğu anlamına gelir; **48/48 klinik doğrulama yapıldığı anlamına gelmez**.

## Sabit/pinned mevcut modeller

- FDI/tooth segmentation: `YOLOv11x-seg.pt`
- Findings9: `YOLO26_Dental_Findings_9.pt`
- Impacted tooth: `OralGuard_Impacted.pt`

Bu üç kaynakla doğrudan baseline canonical kapsama 9 bulgudur.

## Hazır optional model kaynakları

Manifest ayrıca şunları hazırlar:

- 31-class panoramic detector/segmenter,
- Panoramic Reader bone-loss/periapical/tooth-seg/restoration modelleri,
- TVEM 11-disease, bone-loss, mandibular-canal/maxillary-sinus ve periapical specialist checkpointleri.

TVEM label adları OPGAgent kategori dosyalarındaki gerçek isimlerle eşlenir; `class_0` tahmini üzerinden hastalık adı uydurulmaz.

## Motor kompozisyonları

Örnekler:

- `IMPACTED_THIRD_MOLAR` = impacted detector + FDI third-molar konumu,
- `IMPLANT_SUPPORTED_CROWN` = implant + crown/abutment mekansal eşleşmesi,
- `RECURRENT_CARIES` = caries + restoration margin ilişkisi,
- `MANDIBULAR_CANAL_PROXIMITY` = kanal anatomisi + kök/diş mesafesi,
- periodontal alt tipler = generic bone-loss + crest/defect/furcation geometrisi,
- internal/external resorption = generic resorption + root contour/lumen geometry,
- sinus bulguları = sinus maskesi + iç opasite/basal bant analizi,
- condyle bulguları = bilateral superior contour/shape analizi.

## Doğrulama ayrımı

`readiness_snapshot()` iki ayrı kavramı raporlar:

- `implementation_complete`: 48 motorun kod/strateji kapsamı,
- `runtime_validation_complete`: gerçek pozitif/negatif panoramik smoke testleri.

Böylece katalogda isim olması veya tek görüntüde yüksek confidence görülmesi 48/48 PASS diye raporlanamaz.

## Genel AI kuralı

Panoramik pikseli GPT/Gemini/başka genel multimodal modele gönderilmeyecek. Genel AI yalnız özel görüntü motorlarının yapılandırılmış çıktısı + FDI/ölçüm + klinik metin alacak.
