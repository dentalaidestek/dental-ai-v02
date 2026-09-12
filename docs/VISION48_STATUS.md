# Dental AI Vision 48 — geliştirme dalı

Bu belge `work/vision48-3d-ready` dalının gerçek durumunu gösterir. Production deploy değildir.

## Production koruması

- `main` değiştirilmedi.
- Render servisleri `main` dalını izlediği için bu dal production'a deploy edilmez.
- PR #1 draft durumunda tutulur; 48/48 gerçek runtime PASS tamamlanmadan merge edilmez.
- Runtime/klinik doğrulama yazılım kapsamından ayrı tutulur.

## Durumun üç ayrı sayacı

1. **Motor yazılım kapsamı: 48/48.** `vision_service/motors/registry48.py` içindeki katalogda her canonical bulgu için bir inference stratejisi vardır; placeholder/TODO yoktur.
2. **Pinned gerçek-weight runtime availability: 9/48.** Repo içinde sabit weight + canonical mapping ile yapılandırılmış taban bulgular `MISSING_TOOTH`, `IMPACTED_TOOTH`, `FILLING`, `CROWN`, `BRIDGE`, `IMPLANT`, `ROOT_CANAL_TREATED`, `CARIES`, `PERIAPICAL_RADIOLUCENCY` bulgularıdır. Bu yalnız modelin çalıştırılabilir biçimde mevcut olduğunu söyler.
3. **Evidence-backed runtime PASS: 0/48.** `vision_service/runtime_validation.py` içindeki kanıt defterinde gerçek pozitif panorama + negatif/false-positive kontrolü + exact mapping + threshold + gerekiyorsa FDI lokalizasyonu + fail-isolation kanıtı olmadan hiçbir bulgu PASS sayılmaz.

Bu üç sayı birbirinin yerine kullanılmaz. Model dosyasının diskte bulunması, import edilmesi veya tek başına confidence üretmesi klinik/runtime PASS değildir. 48/48 kanıt tamamlanmadan `runtime_validation_complete=true` olmaz.

## 48/48 motor uygulama kapsamı

`vision_service/pipeline.py` pinned modelleri, optional hazır modelleri, TVEM kontrol motorlarını ve composed/CV motorlarını tek panoramik pipeline'da toplar.

Her bulgunun kabul yolu ayrıca `vision_service/validation_matrix.py` içinde dört lane'den biriyle tanımlıdır:

- `pinned_direct`: mevcut sabit checkpoint,
- `ready_candidate`: hazır public checkpoint adayı var; exact-label + gerçek pozitif/negatif panorama testi sonrası kabul edilir,
- `composed_candidate`: doğrulanmış üst motorlar + FDI/anatomi/ölçüm ile deterministik çıktı; validation zayıfsa dedicated training'e düşer,
- `train_required`: yeterince spesifik hazır panoramik checkpoint henüz doğrulanmadı; dedicated eğitim gerekir.

Böylece yalnız kod yazılmış olması yanlışlıkla “motor klinik olarak hazır” anlamına gelmez. `derived48.py` içindeki görüntü heuristikleri de aynı katı runtime PASS sözleşmesine tabidir.

## Sabit/pinned mevcut modeller

- FDI/tooth segmentation: `YOLOv11x-seg.pt`
- Findings9: `YOLO26_Dental_Findings_9.pt`
- Impacted tooth: `OralGuard_Impacted.pt`

Bu ağırlıkların varlığı 9 bulguyu otomatik PASS yapmaz; gerçek test fixture kanıtı ayrıca kaydedilir.

## Hazır optional kaynaklar

Manifest şu kaynakları destekler:

- 31-class panoramic detector/segmenter (`yolo31`),
- InsMile 12-class panoramic control/helper detector (`insmile12`),
- Liodon compact panoramic control detector (`caries`, `periapical_lesion`, `impacted_tooth`),
- Panoramic Reader periapical/tooth-seg/restoration modelleri,
- TVEM 11-disease, generic bone-loss, mandibular-canal/maxillary-sinus ve periapical specialist checkpointleri.

Daha önce bone-loss sanılan Panoramic Reader ONNX'i 32 FDI diş sınıfı çıktığı için **bone-loss motoru olarak kullanılmaz**.

TVEM exact labels kullanılır: `Deep Caries`, `Residual Root`, `Pontic`, `Mandibular Canal`, `Maxillary Sinus`, `Bone Loss`. `class_0`, `unknown` veya tahmine dayalı raw label üzerinden canonical hastalık üretilmez.

InsMile exact doğrudan mapping yalnız semantiği net eşleşen sınıflarla sınırlıdır: `Caries`, `Periapical Lesion`, `Retained Root`/`Root Piece`, `Impacted Tooth`. `Bone Loss`, `Root Resorption`, `Cyst` ve belirsiz `Fracture` gibi sınıflar spesifik canonical subtype'a yükseltilmez; helper/candidate olarak kalır.

Liodon kontrol motoru kendi yayımlanan inference ayarlarıyla çalışır: `imgsz=640`, `conf=0.45`, `iou=0.35`. Mevcut pinned motorların yerine geçmez; aynı bulguda destek/provenance sağlar.

## Weight bütünlüğü ve lisans

`vision_service/model_sources.py` bilinen kaynaklarda exact revision ve mümkün olduğunda SHA256 sabitler. SHA256 kayıtlı kaynak indirilirken hash doğrulanır; uyuşmayan dosya kabul edilmez.

Doğrulanmış örnekler:

- Liodon ONNX revision + SHA256,
- Panoramic Reader periapical ONNX revision + SHA256,
- InsMile `best.pt` revision + SHA256,
- TVEM bone-loss, canal/sinus ve periapical3 revision + SHA256.

Lisans uygunluğu model varlığından ayrıdır. Liodon ve TVEM kaynakları `CC-BY-NC-4.0` olduğundan ticari production bağımlılığı olarak otomatik onaylanmaz. InsMile lisansı net doğrulanmadığı için production açısından `unknown` blocker olarak kalır. `readiness_snapshot()` bu optional production-license blocker listesini açıkça raporlar.

## Eğitim hattı

`training/vision48_specialists.py` GPU üzerinde çalışacak, kesilirse `last.pt` üzerinden devam edecek ve workspace'i kalıcı Google Drive alanına yazacak şekilde hazırlanmıştır. Varsayılan workspace `/content/drive/MyDrive/DentalAI_Vision48_Training` olur. Mevcut dokuz pinned bulgu eğitim çıktılarından özellikle çıkarılmıştır.

Otomatik indirilebilen iki ana track:

- **Track A / Kaggle31:** residual root, tooth fracture, generic root-resorption helper, endo post, orthodontic appliance, primary-tooth helper, mandibular-canal helper, generic bone loss, cyst/bone-defect helper.
- **Track B / Zenodo14:** generic bone loss, residual root, furcation bone loss, apical surgery, generic root resorption, orthodontic appliance.

`training/source_catalog.py` ayrıca kalan zor sınıflar için veri/hosted-model araştırma kaynaklarını kilitler. RVG-18 ve geniş Caries87 kaynaklarının yanında unerupted/root-resorption, lamina-dura/PDL/furcation ve TMJ morphology adayları kataloglanmıştır. Bu adayların `hosted_model_or_export_required` olması otomatik eğitim veya PASS anlamına gelmez.

Generic dataset etiketi exact subtype üretmek için kullanılmaz. Örneğin generic/root-apex resorption verisi `EXTERNAL_ROOT_RESORPTION` veya `INTERNAL_ROOT_RESORPTION` olarak otomatik etiketlenmez; TMJ `FLATTENED` benzeri bir raw label doğrulanmadan `CONDYLAR_FLATTENING` yapılmaz.

Yayınlarda güçlü performans gösterip açık checkpointi bulunmayan sınıflar (ör. condensing osteitis, root dilaceration, bazı jaw-lesion ve TMJ motorları) “hazır” sayılmaz; training/validation lane'inde kalır.

## Genel AI'ya görüntü gönderilmez

`app/ai_provider.py` legacy `image_paths` parametresini kabul etse bile dış API isteğine görüntü/piksel/base64 eklemez. Dosyalar yalnız DentalAI görüntü motorlarında işlenir. Dış klinik AI'ya yalnız yapılandırılmış Vision48 JSON + klinik/RAG metni gider. CI testi external payload içinde `inline_data` bulunmadığını doğrular.

## Photo → 3D

Fotoğraf tabanlı 3D katmanı branch üzerinde ayrı tutulur ve tanısal CBCT rekonstrüksiyonu gibi sunulmaz. Amaç, ağız içi fotoğraflardan hasta sunumu için etkileşimli dental visualization üretmektir. Radyografik Vision48 motorlarının tanısal görüntü katmanıyla karıştırılmaz.

## Doğrulama ayrımı

`readiness_snapshot()` ayrı ayrı şunları raporlar:

- `implementation_complete`,
- `runtime_available_baseline_total`,
- `runtime_validation_pass_total`,
- `runtime_validation_pending_total`,
- `runtime_validation_complete`,
- `validation_lane_counts`,
- `training_required_codes`,
- `ready_candidate_codes`,
- `composed_candidate_codes`,
- indirilen/eksik optional model dosyaları,
- optional production-license blocker listesi.

Tek görüntü confidence değeri accuracy veya mAP olarak raporlanmaz.

## Güncel bitirme durumu

- Motor stratejisi: **48/48 implementation complete**.
- Kanıtlı runtime PASS: **0/48**; repo içinde gerçek pozitif/negatif panorama fixture seti henüz yoktur.
- CI contract/model-source kontrolleri yeşildir.
- Production deploy **YAPILMADI**.
- `48/48 PANORAMIC PASS` ifadesi bu kanıt defteri gerçekten 48 PASS olmadan kullanılmayacaktır.
