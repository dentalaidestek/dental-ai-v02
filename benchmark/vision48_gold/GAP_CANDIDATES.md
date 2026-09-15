# Vision48 Gold Benchmark — remaining gap candidates

Bu belge **eğitim için değildir**. Amaç, mevcut motorları bağımsız uzman ground-truth ile ölçmek için erişilebilir veya yazarlardan istenebilir veri adaylarını kilitlemektir. Bir kaynak burada yazıyor diye `PASS` veya gold sayılmaz; görüntüler + ham etiketler elde edilip sınıf semantiği doğrulanmadan `source_catalog.py` içine exact olarak alınmaz.

## Bu turda gerçekten gold kataloğuna eklenen bağımsız kaynaklar

- **MOPG-7 v4** — 2,095 panoramik, 9,834 uzman doğrulanmış kutu; `MISSING_TOOTH` için doğrudan bağımsız aday. Crown/RCT/caries de ek dış doğrulama sağlar. Public, Mendeley: https://data.mendeley.com/datasets/r43v452t29/4
- **Dual-labeled panoramic dataset — public 500 subset** — dört doktorun polygon + FDI + durum anotasyonları; FDI `91` açıkça supernumerary. `SUPERNUMERARY_TOOTH` ve `FILLING` için bağımsız exact aday. https://www.kaggle.com/datasets/zwbzwb12341234/a-dual-labeled-dataset/data
- **PDCNN periodontitis dataset** — 1,747 yüksek çözünürlüklü panorama, profesyonel doktor anotasyonları; ayrı `via_export_coco_FI.json` furcation-involvement etiketi. `FURCATION_BONE_LOSS` için public exact aday. https://github.com/PuckBlink/PDCNN
- **CONTACT** — 1,478 mandibular üçüncü molar / inferior alveolar kanal çifti; panoramik semantic mask + CBCT-confirmed contact/no-contact, üç OMR + gerektiğinde dördüncü uzman. `MANDIBULAR_CANAL_PROXIMITY` için çok güçlü bağımsız referans; canonical kodumuz “proximity” olduğu için eşik sabitlenene kadar partial tutuldu. https://www.kaggle.com/datasets/tugcetoprak92/contact-dataset

Bu eklemeler sonrası katalog durumu: **14 exact / 9 partial-only / 25 henüz kilitlenmemiş**.

## Kalan 25 kod için araştırma sonucu

| Vision48 kodu | En iyi bulunan aday | Uzman / örnek gücü | Erişim | Karar |
|---|---|---|---|---|
| `RETAINED_PRIMARY_TOOTH` | Mixed-dentition primary-tooth segmentation çalışmaları; ayrıca retained-primary klinik kohortları | Primary tooth varlığını etiketliyor ama “retained” semantiğini doğrudan vermiyor | çoğunlukla request | **Exact değil; gap** |
| `INLAY_ONLAY` | Inlay/onlay AI veri çalışmaları bulundu | Ana veri 3D prepared-tooth/specimen; panorama değil | kod açık, uygun pano veri yok | **Gap** |
| `IMPLANT_SUPPORTED_CROWN` | Başaran et al., *Diagnostic charting of panoramic radiography* | 1,084 panorama; iki dentomaksillofasiyal radyolog; explicit implant-supported crown | ham veri public görünmüyor / author request | **Güçlü exact aday** |
| `UNDERFILLED_ROOT_CANAL` | *Artificial Intelligence Application in Assessment of Panoramic Radiographs* | 3 bağımsız diş hekimi; 109 endodontik değerlendirme, inter-rater ICC 0.924 | ham veri/labels request gerekir | **Exact ama küçük aday** |
| `OVERFILLED_ROOT_CANAL` | aynı çalışma | 3 bağımsız diş hekimi; 109 endodontik değerlendirme, inter-rater ICC 0.886; pozitif sayısı az | ham veri/labels request gerekir | **Exact ama zayıf-sayı aday** |
| `BROKEN_ENDO_INSTRUMENT` | *Detection of the separated root canal instrument on panoramic radiograph* | 915 diş: 417 separated instrument + 498 healthy RCT; iki diş hekimi; pozitifler periapikal ile doğrulanmış | ham veri request/closed | **Güçlü exact aday** |
| `APICAL_SURGERY` | Zenodo14 `APS` etiketi | Exact sınıf var fakat bu veri bizim training track’imizde | public ama **gold leakage** | **Bağımsız gap**; apicoectomy-need datasetleri prior surgery ile eşdeğer değil |
| `DEEP_CARIES` | *Deep Learning for Caries Detection and Classification* | 1,160 panorama; D1/D2/D3; 3 uzman diş hekimi + 4. uzman review; 1,635 D3 | raw labels author request | **Güçlü exact aday** |
| `RECURRENT_CARIES` | 22,999-image / 30-clinic fine-grained anomaly study | dental radiography expert; explicit `secondary caries` class | dataset public görünmüyor / author request | **Güçlü exact aday** |
| `PERIAPICAL_RADIOPACITY` | Diagnocat evaluation cohort | 3 bağımsız deneyimli diş hekimi; periapical lesions osteolytic/osteosclerotic/mixed | labels author request | **Partial/semantik doğrulama gerekli**; generic jaw radiopacity exact değildir |
| `WIDENED_PDL` | Ekert et al. apical-lesion panoramic reference | 2,001 tooth segments; 6 bağımsız examiner majority vote; ordinal `widened PDL / uncertain lesion` sınıfı | author request | **Güçlü exact-adjacent aday** |
| `LOSS_OF_LAMINA_DURA` | Pediatric furcation/lamina-dura panoramic study | 387 panorama; lamina-dura loss explicit sınıf; uzman doğrulama/consensus | raw data request | **Güçlü exact aday** |
| `CONDENSING_OSTEITIS_PATTERN` | 2025 CO vs idiopathic osteosclerosis study | 1,000 panorama; iki OMR; calibration + consensus; Cohen κ 0.93, intra ICC 0.91 | raw images/labels public görünmüyor | **Güçlü exact aday** |
| `EXTERNAL_ROOT_RESORPTION` | 22,999-image 17-anomaly panoramic dataset | explicit external root resorption; dental radiography expert | author request | **Güçlü exact aday** |
| `INTERNAL_ROOT_RESORPTION` | Retrospective panoramic RR series | 240 hastada 113 resorption; internal yalnız ~2.08% (yaklaşık 5 vaka) | raw data yok/request | **Yetersiz; gerçek gap** |
| `ROOT_DILACERATION` | *Root Dilaceration Using Deep Learning* | 636 panorama / 983 dilaceration objesi; OMR initial label + 2 hafta sonra tekrar doğrulama | raw labels public görünmüyor | **Güçlü exact aday** |
| `TOOTH_FRACTURE` | Panoramik cracked-tooth çalışmalar + blocked Kaggle31 fracture class | cracked-tooth klinik GT var ama canonical “tooth fracture” ile birebir değil; exact public sınıf mevcut training source’da | request / blocked | **Exact bağımsız gap** |
| `ROOT_FRACTURE` | Fukuda et al. vertical root fracture | 300 panorama / 330 VRF diş; fracture line iki radyolog + bir endodontist tarafından doğrulanmış | author request | **Güçlü exact aday** |
| `CALCULUS` | Başaran et al. diagnostic charting | 1,084 panorama; iki dentomaksillofasiyal radyolog; 518 calculus etiketi raporlanmış | author request | **Güçlü exact aday** |
| `MAXILLARY_SINUS_MUCOSAL_THICKENING` | 22,999-image 17-anomaly panoramic dataset | explicit maxillary-sinus mucosal thickening class; dental radiography expert | author request | **Güçlü exact aday** |
| `MAXILLARY_SINUS_OPACIFICATION` | Paired panoramic/CBCT sinus studies | CBCT/OMR consensus güçlü, fakat “global opacification” için büyük açık ham set bulamadık | request / küçük kohort | **Şimdilik gap/partial** |
| `CONDYLAR_FLATTENING` | 2025 TMJ condylar-bone-change study | 3,875 condylar panorama; flattening explicit class | raw labels + annotator protocol erişimde doğrulanmalı | **Güçlü request adayı** |
| `CONDYLAR_EROSION` | aynı 3,875-condyle çalışma | erosion explicit olarak tanımlı fakat az sayıda ve bazı deneylerde deformation grubuna birleştirilmiş | author request | **Aday; original erosion labels şart** |
| `CONDYLAR_ASYMMETRY` | 2026 mandibular asymmetry OPG landmark study | 1,038 OPG; manual landmark kıyaslarında ICC > 0.983 | author request | **Güçlü geometric partial; asymmetry eşiği kilitlenmeden exact değil** |
| `ORTHODONTIC_APPLIANCE` | Zenodo14 `ORD` + Kaggle31 bracket/wire/retainer/TAD | Exact panorama sınıfları var fakat ikisi de mevcut training/model kaynaklarımızdan | public ama **gold leakage** | **Bağımsız gap** |

## Kaynak bağlantıları / yayınlar

- Implant-supported crown + calculus: https://pubmed.ncbi.nlm.nih.gov/34611840/
- Under/overfilled canal: https://pmc.ncbi.nlm.nih.gov/articles/PMC8774336/
- Broken endodontic instrument: https://pmc.ncbi.nlm.nih.gov/articles/PMC9944016/
- Deep caries D1/D2/D3: https://pmc.ncbi.nlm.nih.gov/articles/PMC8469830/
- 17 anomalies / 22,999 panoramics: https://pmc.ncbi.nlm.nih.gov/articles/PMC8956729/
- Widened PDL / apical-lesion reference: https://pubmed.ncbi.nlm.nih.gov/31160078/
- Condensing osteitis: https://pmc.ncbi.nlm.nih.gov/articles/PMC12339992/
- Root dilaceration: https://www.mdpi.com/2076-3417/13/14/8260
- Vertical root fracture: https://pubmed.ncbi.nlm.nih.gov/31535278/
- Condylar flattening/erosion: https://www.mdpi.com/2075-4418/15/8/1022
- Mandibular asymmetry landmarks: https://pubmed.ncbi.nlm.nih.gov/40047777/
- Internal/external root resorption panoramic series: https://pmc.ncbi.nlm.nih.gov/articles/PMC6778303/

## Sonuç / sonraki güvenli adım

Şu anda **hiçbir eğitim başlatılmayacak**. Public ve semantiği yeterince temiz dört yeni kaynak kataloğa alındı. Author-request kaynakları ise erişim alınmadan gold sayılmayacak. Özellikle `INLAY_ONLAY`, `INTERNAL_ROOT_RESORPTION`, bağımsız `APICAL_SURGERY`, bağımsız exact `TOOTH_FRACTURE`, `MAXILLARY_SINUS_OPACIFICATION` ve bağımsız `ORTHODONTIC_APPLIANCE` halen gerçek veri açığıdır.
