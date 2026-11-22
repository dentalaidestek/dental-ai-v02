# Klinik medya — R2 bağlantı ve metadata iyileştirmesi (2026-11-18)

## Web akışı önce incelendi

Referanslar:
- app/templates/patient_detail.html: Klinik Arşiv upload formu, galeri, preview, delete ve AI için seçili medya akışı
- app/main.py: web upload, file response, single-delete ve delete-all handlers
- app/mobile_api.py: native media list/upload/receipt/file/delete/analyze routes
- mobile/src/NativePatientMedia.tsx, mobile/src/api.ts, mobile/src/modernApi.ts: native picker, encrypted draft, gallery pagination, authenticated file reads

## Değişiklikler

1. Native upload artık dosyayı doğrulayıp hash/fingerprint oluşturduktan sonra kısa bir owner/replay preflight yapıyor. R2 persistence run_in_threadpool üzerinden SQL transaction dışında gerçekleşiyor. Sonra hasta satırı kilitleniyor; receipt ve batch quota yeniden doğrulanıyor; media row, receipt ve realtime event tek transaction'da kaydediliyor.
2. Aynı request key ile eşzamanlı upload yarışı final transaction'da tekrar kontrol ediliyor. Başka istek önce commit etmişse ikinci R2 objesi silinerek aynı receipt yanıtı döndürülüyor.
3. Native file download önce owner/patient/media yetkisini kısa DB oturumunda kontrol edip yalnızca storage reference ve filename kopyalıyor. R2 hydration DB oturumu kapandıktan sonra threadpool'da yapılıyor. Dosya yanıtı private, no-store kalıyor.
4. Web ve native upload formlarına isteğe bağlı tek FDI diş numarası ve 2.000 karakter klinik not eklendi. Native taslak bu metadata'yı şifreli medya dosyalarıyla aynı user/patient scope'unda saklıyor ve uygulama yeniden açıldığında geri yüklüyor. AI analizinde kullanılan çoklu diş girdileri ayrı state olarak korunuyor.
5. Native API multipart upload sözleşmesi FDI ve note alanlarını backend'e gönderiyor.

## Ölçek ve güvenlik

- Native liste API'si cursor tabanlı, en fazla 40 kayıtlık sayfa döndürüyor; client before cursor, duplicate ID ve sayfa sırası doğrulaması yapıyor.
- Upload başına en fazla 12 dosya, dosya başına 12 MiB ve batch başına 96 MiB sınırları korunuyor.
- Upload receipt idempotency, HMAC fingerprint, patient row lock ve batch quota final transaction içinde korunuyor.
- Liste, upload receipt ve file response private/no-store sözleşmesini koruyor. Aktif route kaydı ayrıca `tests/test_mobile_route_registry.py` ile doğrulanıyor.
- R2 network I/O artık upload/download sırasında SQL bağlantısı veya patient row lock tutmuyor.

## Bilinen açıklar

- Web ve native galeriler için özel thumbnail endpoint/derivative storage artık mevcut. 2026-11-22 incelemesinde cleanup allow-list'inin yalnızca orijinal dosya anahtarlarını kabul ettiği ve `.thumb` türevlerini reddettiği bulundu; bu, türev silme işlemini senkron fallback'e bırakıyordu. Allow-list şimdi yalnızca sunucunun deterministik `.thumb` adını da kabul ediyor; türevler aynı durable cleanup worker ve retry yolunu kullanıyor.
- R2 timeout/partial-write cleanup, PostgreSQL yarış testleri, browser/device E2E ve gerçek R2 entegrasyon testi bu ortamda çalıştırılmadı.
- 60.000 kullanıcı kapasitesi kanıtlanmadı; bu değişiklik yalnızca DB bağlantı/lock tutma süresini azaltır.

## Eklenen testler

- tests/test_production_optimization.py: mobile upload sırasında R2 persist işlemi DB connection tutmamalı ve event loop dışı thread'de çalışmalı.
- tests/test_production_optimization.py: mobile file download sırasında R2 hydration DB connection tutmamalı, authenticated FileResponse private/no-store kalmalı.
- mobile/tests/session.cjs: multipart upload FDI ve note alanlarını gönderir.
- mobile/tests/clinicalMediaDraft.cjs: metadata'nın native pending draft'ta korunması ve restore edilmesi kontrol edilir.

Test kaynakları eklendi; bu çalışma ortamında pytest, Node suite, TypeScript, Android build veya gerçek R2/DB yük testi çalıştırılmadı. CI sonucu ayrıca raporlanacaktır.

## 2026-11-22 follow-up — mobile gallery cache privacy and beta test root causes

### Starting-head CI (2068c4158dba3a152c06e86ac4fd402c7199b354)

- Android run #4699: TypeScript typecheck, session/auth, realtime/pagination and Hermes exports succeeded; Android APK assembly/artifact upload succeeded. The beta suite reported 986 passed / 2 failed.
- Security Recovery #2398: all seven jobs completed successfully, including Python security/PostgreSQL migration and the native voice, academic, support, clinical, program and social suites.
- The two beta failures were test-source assumptions, not a TypeScript or tooth-chart runtime failure:
  1. The lower-jaw test searched for the UMD global assignment inside tooth_chart.html, although the assignment belongs to the separately loaded static/tooth-chart/surface-options.js. The test now evaluates that exact helper in a browser-like VM and checks all 52 valid FDI values against the native visual model.
  2. The surface-state test required a local variable named pin; the actual handler correctly iterates .surface-pin elements as b. Replaced the brittle name match with a behavioral test that executes the actual setSurface function against DOM test doubles and verifies chip/pin state plus clearing.
- These are corrections to test scope and execution; no production tooth-chart behavior was weakened.

### New clinical-media privacy issue

app/main.py mounts `mobile_api.router` first, then calls `remove_shadowed_routes((mobile_router, mobile_analysis_router), mobile_modern_router)`. The registry removes colliding method/path pairs from the v3 candidate router; it does not remove the earlier primary handlers.

The active route map is therefore:
- GET `/api/mobile/v1/patients/{patient_id}/media`: primary `app.mobile_api.mobile_patient_media`, which applies `_mobile_private_no_store(response)` and owner-scoped queries.
- POST `/api/mobile/v1/patients/{patient_id}/media`: primary receipt-aware `app.mobile_api.mobile_patient_media_upload`; the simpler v3 duplicate is pruned.
- GET `.../media/{media_id}/file`: primary `app.mobile_api.mobile_patient_media_file`, including post-R2-hydration owner/source revalidation.
- GET `.../media/{media_id}/thumbnail` and GET `.../media/{media_id}`: unique v3 routes, retained with private/no-store headers and ownership checks.

The v3 duplicate list route retains the same headers as defensive parity if route registration changes, but it is not the active list handler today. A runtime route-registration regression now checks the actual FastAPI app route table. The owner-scoped patient and media checks remain unchanged.

### Native response minimization

modernApi.getMedia() previously spread the full server object into the native gallery model. It now constructs an explicit allowlist of display fields and rebuilds original/thumbnail URLs from the canonical API base and validated patient/media IDs. Unexpected fields such as owner_user_id, file_path, storage_key, and server-supplied external URLs cannot propagate into the gallery model.

Added regressions for:
- the canonical v3 list and metadata handlers' no-store headers and owner checks, including route-deduplication order;
- browser UMD helper publication and all 52 FDI lower-jaw mappings;
- actual surface chip/pin aria-pressed behavior and clear-state reset;
- native media response allowlisting and same-origin URL reconstruction.

### Commits

- b224702 — test lower-jaw preview through the loaded browser helper
- 4182106 — execute web surface selection behavior in the parity test
- 1ad3832 — private/no-store headers on active native media list and metadata handlers
- b697caf — backend regression for route selection and private response headers
- 3a31838 — allowlist native media fields and rebuild private URLs
- 0d002f9 — native response allowlisting and URL-isolation regression

### Validation boundary

The fixes above are committed, but their new-head CI has not yet completed. The green Security Recovery #2398 and the Android typecheck/APK results belong to starting head 2068c41, not the new commits. No new pass is claimed until the new branch-head Android and Security runs finish. No patient data, database schema, R2 object, main branch, production deployment or staging database was changed.



## 2026-11-22 correction — durable thumbnail object keys

The cleanup worker's allow-list previously accepted the original patient-media key but rejected the deterministic `.thumb.jpg` derivative. The rejected derivative used the synchronous fallback after the metadata commit, so an R2 outage could leave it without a durable retry. The allow-list and worker regressions now cover both original and thumbnail keys, and the native delete handler is exercised against a SQLite transaction fixture to prove both receipts are committed together.

The earlier route note in this document is also corrected: method/path collisions are removed from the v3 candidate router, while the earlier `mobile_api` route remains active. The primary list route already sets private/no-store headers; the unique v3 metadata and thumbnail routes retain their own private headers and owner checks.
