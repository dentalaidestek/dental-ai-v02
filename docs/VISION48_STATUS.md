# Dental AI Vision 48 — geliştirme dalı

Bu belge `work/vision48-3d-ready` dalının gerçek durumunu gösterir. Production deploy değildir.

## Production koruması

- `main` değiştirilmedi.
- Render servisleri `main` dalını izlediği için bu dal production'a deploy edilmez.
- PR #1 draft durumunda tutulur; 48/48 gerçek runtime kapsamı tamamlanmadan merge edilmez.

## Mevcut doğrulanmış taban korunur

Mevcut panoramik sistemde daha önce test edilmiş baseline geri sıfırlanmaz:

- **9 pinned bulgu** mevcut gerçek weight + canonical mapping ile çalışır ve daha önce doğrulanmıştır: `MISSING_TOOTH`, `IMPACTED_TOOTH`, `FILLING`, `CROWN`, `BRIDGE`, `IMPLANT`, `ROOT_CANAL_TREATED`, `CARIES`, `PERIAPICAL_RADIOLUCENCY`.
- **FDI / diş numaralandırma motoru** da daha önce test edilmiş mevcut baseline'ın parçasıdır; Vision48 genişletmesi bunu yeniden “test edilmemiş” durumuna düşürmez.
- Bu nedenle yeni Vision48 çalışmasının görevi mevcut doğrulanmış tabanı silmek veya yeniden sıfırdan kanıtlamak değil, kalan bulguları gerçek motorlarla tamamlayıp doğrulamaktır.

## 48/48 motor uygulama kapsamı

`vision_service/motors/registry48.py` ve `vision_service/pipeline.py` tarafında 48 canonical bulgunun yazılım stratejileri tanımlıdır. Pinned modeller, optional hazır modeller, TVEM kontrol motorları ve composed/CV motorları tek panoramik pipeline'da birleşir.

Her bulgunun devam yolu `vision_service/validation_matrix.py` içinde dört lane'den biriyle tanımlıdır:

- `pinned_direct`: mevcut doğrulanmış/pinned baseline,
- `ready_candidate`: hazır public checkpoint adayı var; exact-label ve gerçek runtime kontrolü sonrası kabul edilir,
- `composed_candidate`: doğrulanmış üst motorlar + FDI/anatomi/ölçüm ile deterministik çıktı; validation zayıfsa dedicated training'e düşer,
- `train_required`: yeterince spesifik hazır panoramik checkpoint henüz doğrulanmadı; dedicated eğitim gerekir.

`derived48.py` içindeki görüntü heuristikleri de doğrulanmadan hazır bulgu sayılmaz; fakat bu durum mevcut 9 bulgu ve FDI baseline'ını geriye düşürmez.

## Sabit/pinned mevcut modeller

- FDI/tooth segmentation: `YOLOv11x-seg.pt`
- Findings9: `YOLO26_Dental_Findings_9.pt`
- Impacted tooth: `OralGuard_Impacted.pt`

Bu baseline korunur; mevcut 9 bulgu gereksiz yere yeniden eğitilmez.

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

Lisans uygunluğu model varlığından ayrıdır. Liodon ve TVEM kaynakları `CC-BY-NC-4.0` olduğundan ticari production bağımlılığı olarak otomatik onaylanmaz. InsMile lisansı net doğrulanmadığı için production açısından `unknown` blocker olarak kalır.

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

## Güncel durum

- Motor stratejisi: **48/48 implementation complete**.
- Önceden doğrulanmış baseline: **9 pinned bulgu + FDI/diş numaralandırma** korunur.
- Kalan Vision48 bulgularının gerçek runtime doğrulaması tamamlanmadan panoramik sistem için `48/48 PANORAMIC PASS` denmez.
- CI contract/model-source kontrolleri yeşil tutulur.
- Production deploy **YAPILMADI**.
