# Dental AI Vision 48 — geliştirme dalı

Bu belge `work/vision48-3d-ready` dalının gerçek durumunu gösterir. Production deploy değildir.

## Production koruması

- `main` değiştirilmedi.
- Render servisleri `main` dalını izlediği için bu dal production'a deploy edilmez.
- Runtime smoke/klinik doğrulama ayrıca yapılacak.

## 48/48 motor uygulama kapsamı

`vision_service/motors/registry48.py` içinde katalogdaki **48 bulgunun tamamı** için bir inference stratejisi tanımlıdır. `vision_service/pipeline.py` pinned modelleri, optional hazır modelleri, TVEM kontrol modellerini ve composed/CV motorlarını tek panoramik pipeline'da toplar.

Stratejiler üç türdür: hazır/doğrudan checkpoint, birden fazla motor çıktısını birleştiren composed motor ve FDI/anatomi + görüntü geometrisinden türetilen CV motoru. Hiçbir katalog kaydı placeholder/TODO olarak bırakılmaz.

Bu **48/48 yazılım motor kapsamıdır**; gerçek panoramik pozitif/negatif smoke doğrulaması ayrı aşamadır ve sonuçlar görülmeden klinik başarı iddiası yapılmaz.

## Sabit/pinned mevcut modeller

- FDI/tooth segmentation: `YOLOv11x-seg.pt`
- Findings9: `YOLO26_Dental_Findings_9.pt`
- Impacted tooth: `OralGuard_Impacted.pt`

## Hazır optional kaynaklar

Manifest şunları destekler:

- 31-class panoramic detector/segmenter,
- Panoramic Reader bone-loss/periapical/tooth-seg/restoration modelleri,
- TVEM 11-disease, bone-loss, mandibular-canal/maxillary-sinus ve periapical specialist checkpointleri.

TVEM exact labels kullanılır: `Deep Caries`, `Residual Root`, `Pontic`, `Mandibular Canal`, `Maxillary Sinus`, `Bone Loss`. `class_0` üzerinden hastalık adı uydurulmaz.

## Genel AI'ya görüntü gönderilmez

`app/ai_provider.py` artık legacy `image_paths` parametresini kabul etse bile dış API isteğine hiçbir görüntü/piksel/base64 eklemez. Dosyalar yalnız yerel DentalAI görüntü motorlarında işlenir. Dış klinik AI'ya yalnız yapılandırılmış Vision48 JSON + klinik/RAG metni gider. CI testi external payload içinde `inline_data` bulunmadığını doğrular.

## Doğrulama ayrımı

`readiness_snapshot()` iki farklı durumu raporlar:

- `implementation_complete`: 48 motorun kod/strateji kapsamı,
- `runtime_validation_complete`: gerçek pozitif/negatif panoramik smoke testleri.

Tek görüntü confidence değeri accuracy/mAP olarak raporlanmaz.
