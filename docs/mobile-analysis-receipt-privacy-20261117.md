# Native AI-analysis receipt privacy — 2026-11-17

## Web-first review

Before editing, compared the PR-base web flow on `feature/mobile-beta-20261110`:

- `app/templates/analysis_new.html`: the compose page exposes anonymous patient ID, age and chief complaint, plus FDI/clinical notes and up to four selected/new images.
- `app/templates/analysis_viewer.html`: the viewer uses same-origin, analysis-scoped asset and vision endpoints; clinical note and treatment actions remain explicit clinician actions.
- `app/mobile_analysis_api.py`: the native detail response and upload receipt implementation.
- `mobile/src/analysisApi.ts`, `NativeDentalAI.tsx` and `NativeAnalysisUpload.tsx`: native detail parsing, restored patient selection and upload/recovery.

## New privacy findings

1. The mobile analysis-detail response reused a broad patient serializer that included first name, last name, phone, birth date and creation timestamp. The native analysis screen only needs the same limited context shown by the web compose page: internal patient ID for scope checks, anonymous ID, age and chief complaint. Sending direct identifiers to the native analysis screen was unnecessary data exposure.
2. `UPLOAD_RECEIPT.source_hash` stored the raw SHA-256 of a payload containing image-byte digests and clinical context. A database reader with a candidate image/context could perform offline comparisons. The patient-gallery receipt path already uses a keyed fingerprint, so the analysis receipt path had a weaker privacy contract.

## Changes

- The analysis workspace now returns only `id`, `anonymous_id`, `age` and `chief_complaint`. Profile names/contact/birth-date remain in the patient-profile API, not the analysis workspace.
- Native `MobileAnalysis.patient` is now typed as the minimal summary. The response parser rejects any extra patient keys, including direct identifiers. Restored patient choices fall back to anonymous ID; names from the normal patient list still render normally.
- New analysis upload receipts store HMAC-SHA256 fingerprints, not raw SHA-256 digests. The existing dedicated `PATIENT_MEDIA_RECEIPT_KEY` is reused with a distinct `dental-ai:analysis-upload:v1` domain and authenticated owner/patient scope. No application/session-secret fallback is used.
- Existing legacy receipts are upgraded lazily on authenticated receipt lookup or same-key replay. The legacy digest is checked on replay before the row is changed. A status lookup can key the stored legacy digest without loading or rewriting image bytes.
- Missing/invalid key returns 503 before allocating an Analysis row, publishing an image or enqueueing a VISION/PRELIMINARY job. Same-key changed payload remains 409.
- Security recovery now watches `app/analysis_upload_receipts.py`; the existing upload-receipt and viewer Python test modules remain in its pytest command.
- No new table, migration, AI provider call, image re-upload, polling loop, raw-image log or patient-profile mutation was introduced.

## Regression coverage added

Python:
- Newly created receipt stores the owner/patient-scoped HMAC and a version marker, not the legacy digest.
- Owner and patient scope change the fingerprint.
- Legacy receipt is upgraded by status lookup and then replays the same analysis.
- Missing key fails closed before Analysis/ImageAsset/receipt allocation.
- Tampered keyed fingerprint rejects replay without a second analysis.
- Analysis detail returns only the four approved patient-summary fields.

Native:
- Analysis detail rejects direct patient identifiers even when patient ID matches.
- Minimal summary accepts age zero and complaint.
- Restored analysis selection uses anonymous ID while normal patient-list names remain usable.

The new native cases are in `mobile/tests/analysisApi.cjs`, already registered in `npm run test:beta`. Python cases are in `tests/test_mobile_analysis_upload_receipt.py` and `tests/test_mobile_vision_viewer.py`, already included by Security recovery.

## Configuration and release gates

`PATIENT_MEDIA_RECEIPT_KEY` must be configured as a stable 32-byte / 64-hex-character secret before deploying this branch. `render.yaml` already declares the variable as `sync: false`; the secret value is intentionally not stored in Git. The previous PR note says the actual secret had not yet been configured. No live deploy was attempted.

Legacy analysis receipt rows are upgraded only when their owner performs a receipt lookup or same-key replay; this is not a full historical backfill. No periodic table scan was added, preserving the 60k-user cost target.

## Validation boundary

The new tests are committed but have not been executed as repository integration suites in this run. The latest inspected PR-head Android, Security, Admin, Expert Social and Voice workflows all failed before runner allocation: every job had an empty step list, logs returned `BlobNotFound 404`, and artifact lists were empty. Therefore `npm ci`, repository TypeScript, Node beta tests, pytest, Gradle and Expo export did not start. No green CI is claimed.

No main merge, production deploy, APK/IPA publication or clinical record mutation.
