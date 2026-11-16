# Native clinical-information-only analysis — 2026-11-16

## Web flow inspected first

Compared `app/templates/analysis_new.html` and `app/main.py:create_analysis` with `app/mobile_analysis_api.py:create_mobile_analysis`, `mobile/src/NativeAnalysisUpload.tsx`, and `mobile/src/analysisUpload.ts`.

The web form explicitly says that an analysis may start from clinical information without an image. The canonical handler creates an Analysis and queues `PRELIMINARY` when no ImageAsset exists; image-backed requests queue `VISION`. The native endpoint previously rejected every request with zero saved and new images, and the native start button was disabled until a picture was selected.

## Implemented on the mobile parity branch

- The existing authenticated `POST /api/mobile/v1/analyses` endpoint accepts a zero-image request only when an FDI tooth number or non-empty clinical note is supplied.
- Empty requests remain rejected before allocating an Analysis, WorkJob, or receipt.
- The same patient-owner check, per-user request key, canonical upload receipt, PostgreSQL advisory idempotency lock, and payload digest are retained. A repeated identical clinical-only request resolves to the same analysis; changing the clinical context with the same key returns 409.
- The existing canonical queue receives `PRELIMINARY` for zero assets and `VISION` for one or more assets. No fake/empty image part or ImageAsset is created for a clinical-only request.
- The native intent parser accepts zero images only with clinical context. The start button becomes enabled when a saved image, new image, FDI number, or clinical note exists.
- The UI explains that clinical-only work is a preliminary review and does not label it as image processing. The SecureStore draft/receipt recovery path remains shared with image-backed submissions.

## Regression coverage added

Backend tests cover preliminary queue selection, no ImageAsset, receipt recovery, idempotent retry, changed-context conflict, and rejection of empty context before record allocation. Native tests cover intent validation, button eligibility, clinical-only submission and absence of a synthetic multipart image part.

The tests are committed but have not been executed in a full checkout. Android typecheck, Python test execution, physical-device and production API acceptance remain open.

## CI evidence at the starting head

PR #257 head was `48bdc2ebb7d30fdcd96844161d127636ba4daaae`. Android run #2147, Security recovery #880, Admin security #764 and Expert social #760 all completed failure. The jobs exposed `steps: null`/no step records, log downloads returned Azure `BlobNotFound 404`, and artifact lists were empty. Thus `npm ci`, `tsc`, Gradle and `pytest` did not run. The available records still do not expose the exact hosted-runner/account/billing cause; repository owner inspection of Actions availability and billing is required. Do not treat these failures as source-level test failures or as a green validation.

No main merge, production deployment, APK/IPA publication, or real patient-data mutation was performed.
