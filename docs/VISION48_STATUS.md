# Dental AI Vision 48 — çalışma dalı durumu

Bu belge production iddiası değildir. `work/vision48-3d-ready` dalındaki gerçek entegrasyon durumunu gösterir.

## Production'a dokunmama kuralı

- Bu dal `main` değildir.
- Render servisleri `main` dalını otomatik deploy ediyor; bu çalışma dalı Render'a deploy edilmez.
- 48/48 gerçek test edilmeden `main` ile birleştirilmeyecek.

## Şu anda gerçek weight ile yapılandırılmış motorlar

1. `motor1_fdi` — `YOLOv11x-seg.pt` — FDI diş tespiti/segmentasyon desteği.
2. `findings9` — `YOLO26_Dental_Findings_9.pt` — 8 canonical bulgu eşlemesi.
3. `impacted_tooth` — `OralGuard_Impacted.pt` — `IMPACTED_TOOTH`.

Canonical bulgu olarak yapılandırılmış toplam: **9 / 48**.

Bunlar: `MISSING_TOOTH`, `FILLING`, `CROWN`, `BRIDGE`, `IMPLANT`, `ROOT_CANAL_TREATED`, `CARIES`, `PERIAPICAL_RADIOLUCENCY`, `IMPACTED_TOOTH`.

## Katı doğrulama kuralı

Bir bulgu yalnız katalogda adı bulunuyor diye hazır sayılmaz. Aşağıdaki dört koşul birlikte sağlanmadan 48/48 PASS verilmez:

1. gerçek checkpoint/weight,
2. doğrulanmış raw-label -> canonical mapping,
3. en az bir pozitif inference smoke testi,
4. en az bir negatif/yanlış-pozitif kontrolü.

Tek görüntüdeki confidence değeri accuracy/mAP olarak raporlanmaz.

## Mimari karar

Panoramik görüntü yalnız özel görüntü motorlarına gider. Genel LLM sağlayıcısına röntgen/piksel gönderilmez. LLM daha sonra yalnız yapılandırılmış motor çıktısı ve metinsel klinik bilgiyle çalışır.

## Sonraki motor kabul havuzu

TVEM/MaskDINO, DENTEX tabanlı hazır checkpointler ve diğer açık dental checkpointler aday havuzudur. Generic bone-loss, mandibular-canal veya sinus anatomisi tek başına daha spesifik canonical hastalık bulgusuna doğrudan eşlenmez.
