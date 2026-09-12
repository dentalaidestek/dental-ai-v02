# Dental AI Vision 48 — geliştirme dalı

Bu belge `work/vision48-3d-ready` dalının gerçek durumunu gösterir. Production deploy değildir.

## Production koruması

- `main` değiştirilmedi.
- Render servisleri `main` dalını izlediği için bu dal production'a deploy edilmez.
- Runtime smoke/klinik doğrulama ayrıca yapılacak.

## Durumun iki ayrı sayacı

1. **Motor yazılım kapsamı: 48/48.** `vision_service/motors/registry48.py` içindeki katalogda her canonical bulgu için gerçek bir inference stratejisi vardır; placeholder/TODO yoktur.
2. **Pinned gerçek-weight runtime tabanı: 9/48.** Şu anda repo içinde sabit weight + canonical mapping ile mevcut olan taban bulgular `MISSING_TOOTH`, `IMPACTED_TOOTH`, `FILLING`, `CROWN`, `BRIDGE`, `IMPLANT`, `ROOT_CANAL_TREATED`, `CARIES`, `PERIAPICAL_RADIOLUCENCY` bulgularıdır.

İlk sayı kod kapsamını, ikinci sayı gerçek runtime kabulünü ifade eder. 48/48 pozitif/negatif panorama smoke görülmeden `runtime_validation_complete=true` olmaz.

## 48/48 motor uygulama kapsamı

`vision_service/pipeline.py` pinned modelleri, optional hazır modelleri, TVEM kontrol/doğrulama motorlarını ve composed/CV motorlarını tek panoramik pipeline'da toplar.

Her bulgunun kabul yolu ayrıca `vision_service/validation_matrix.py` içinde dört lane'den biriyle tanımlıdır:

- `pinned_direct`: mevcut sabit checkpoint,
- `ready_candidate`: hazır public checkpoint var; exact-label + pozitif/negatif smoke sonrası kabul edilir,
- `composed_candidate`: doğrulanmış üst motorlar + FDI/anatomi/ölçüm ile deterministik çıktı; validation zayıfsa dedicated training'e düşer,
- `train_required`: yeterince spesifik hazır panoramik checkpoint henüz doğrulanmadı; dedicated eğitim gerekir.

Böylece sadece kod yazılmış olması yanlışlıkla “motor klinik olarak hazır” anlamına gelmez.

## Sabit/pinned mevcut modeller

- FDI/tooth segmentation: `YOLOv11x-seg.pt`
- Findings9: `YOLO26_Dental_Findings_9.pt`
- Impacted tooth: `OralGuard_Impacted.pt`

## Hazır optional kaynaklar

Manifest şu kaynakları destekler:

- 31-class panoramic detector/segmenter,
- Liodon compact panoramic control detector (`caries`, `periapical_lesion`, `impacted_tooth`),
- Panoramic Reader bone-loss/periapical/tooth-seg/restoration modelleri,
- TVEM 11-disease, bone-loss, mandibular-canal/maxillary-sinus ve periapical specialist checkpointleri.

TVEM exact labels kullanılır: `Deep Caries`, `Residual Root`, `Pontic`, `Mandibular Canal`, `Maxillary Sinus`, `Bone Loss`. `class_0` üzerinden hastalık adı uydurulmaz.

Liodon kontrol motoru kendi yayımlanan inference ayarlarıyla çalışır: `imgsz=640`, `conf=0.45`, `iou=0.35`. Mevcut daha güçlü pinned motorların yerine geçmez; aynı bulguda destek/provenance sağlar.

## Eğitim hattı

`training/vision48_specialists.py` GPU üzerinde tek komutla çalışacak, kesilirse `last.pt` üzerinden devam edecek şekilde hazırlandı. Mevcut dokuz pinned bulgu bu eğitim çıktılarından özellikle çıkarılmıştır.

Otomatik indirilebilen iki ana track:

- **Track A / Kaggle31:** residual root, tooth fracture, generic root-resorption helper, endo post, orthodontic appliance, primary-tooth helper, mandibular-canal helper, generic bone loss, cyst/bone-defect helper.
- **Track B / Zenodo14:** generic bone loss, residual root, furcation bone loss, apical surgery, generic root resorption, orthodontic appliance.

`training/source_catalog.py` ayrıca kalan zor sınıflar için veri kaynaklarını kilitler. RVG-18 kaynağı `Calculus` ve `Unerupted`; geniş 87-label dental source ise `SHORTENED RCT`, `ROOT CANAL BEYOND APEX`, `VERTICAL BONE LOSS`, `Calculus`, `Unerupted` gibi doğrudan ihtiyacımız olan etiketleri içerir. Bunlar erişilebilir export bulunduğunda dedicated specialist track'e alınacaktır.

Yayınlarda güçlü performans gösterip açık checkpointi bulunmayan sınıflar (ör. condensing osteitis, root dilaceration, bazı jaw-lesion ve TMJ motorları) “hazır” sayılmaz; training/validation lane'inde kalır.

## Genel AI'ya görüntü gönderilmez

`app/ai_provider.py` legacy `image_paths` parametresini kabul etse bile dış API isteğine görüntü/piksel/base64 eklemez. Dosyalar yalnız DentalAI görüntü motorlarında işlenir. Dış klinik AI'ya yalnız yapılandırılmış Vision48 JSON + klinik/RAG metni gider. CI testi external payload içinde `inline_data` bulunmadığını doğrular.

## Photo → 3D

Fotoğraf tabanlı 3D katmanı branch üzerinde ayrı tutulur ve tanısal CBCT rekonstrüksiyonu gibi sunulmaz. Amaç, ağız içi fotoğraflardan hasta sunumu için etkileşimli dental visualization üretmektir. Radyografik Vision48 motorlarının tanısal görüntü katmanıyla karıştırılmaz.

## Doğrulama ayrımı

`readiness_snapshot()` ayrı ayrı şunları raporlar:

- `implementation_complete`,
- `runtime_validation_complete`,
- `validation_lane_counts`,
- `training_required_codes`,
- `ready_candidate_codes`,
- `composed_candidate_codes`,
- indirilen/eksik optional model dosyaları.

Tek görüntü confidence değeri accuracy/mAP olarak raporlanmaz.
