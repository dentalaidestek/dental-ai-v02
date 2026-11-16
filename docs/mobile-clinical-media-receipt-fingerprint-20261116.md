# Native clinical-media receipt fingerprint hardening — 2026-11-16

## Web-first comparison

Before editing native or backend code, compared:

- `app/templates/patient_detail.html`: the web patient profile's clinical archive, PHOTO/RADIOGRAPH selection, multi-file upload, gallery, first-four selection, selected-image AI analysis, individual deletion and delete-all confirmation.
- `app/main.py`: canonical web upload, ownership checks, private image delivery and deletion behavior.
- `mobile/src/NativePatientMedia.tsx`, `clinicalMediaVault.ts` and `clinicalMediaBatch.ts`: native encrypted local vault, persisted upload intent, stable per-file request keys, batch identity, sequential upload, status reconciliation, byte progress, gallery/zoom, owned deletion and saved+new AI composition.
- `app/mobile_api.py`: native per-file upload receipts, owner/patient scope, batch quota, replay and status endpoints.

The native archive already had durable local upload intents, encrypted local files, stable request keys, server receipts, process-restart reconciliation and byte-level progress. The tracker had not reflected that implementation, so its remaining-work row is corrected below. Device acceptance is still open.

## New privacy finding

The native upload receipt stored `WorkJob.source_hash` as an unkeyed SHA-256 over the sanitized image digest and upload metadata. It did not store the image itself, but a database reader with a candidate clinical image could calculate the same digest offline; equal content could also be correlated across owners/patients.

## Changes

- Added `app/patient_media_receipts.py` with a dedicated `PATIENT_MEDIA_RECEIPT_KEY` loader requiring exactly 32 random bytes encoded as 64 hexadecimal characters. It never falls back to a general application/session secret.
- New receipt fingerprints are HMAC-SHA256 with a versioned domain string and both authenticated owner ID and patient ID in the MAC input. The HMAC output remains a 64-character digest, so no database schema change is needed.
- New receipt payloads carry `fingerprint_version: 1`. The canonical legacy digest exists only transiently in memory and is HMAC-wrapped before it is persisted.
- Existing legacy receipts are upgraded in the same transaction on an authenticated upload replay or upload-status lookup. A replay with different content is rejected before the legacy row is changed. A status lookup can key an old digest without loading or rewriting the clinical image.
- Scope mismatch, malformed receipt payload, unsupported version, boolean-as-version tampering and changed-content reuse fail closed.
- Missing key configuration returns HTTP 503 before the image is copied or persisted. The mobile draft remains on device for later reconciliation.
- Added pure helper tests and route-level regressions for keyed storage, missing-key fail-closed behavior and lazy legacy upgrade. Added the helper suite to Security recovery CI.
- No raw image bytes, patient notes, tokens or HMAC key are written to logs. No new provider call, database table, schema migration or production data mutation was introduced.

Legacy receipts that are never replayed or status-checked retain their previous unkeyed digest until they are next accessed. No bulk database scan was added: a repeated full scan would be an avoidable cost at the 60,000-user target. This is a lazy in-place upgrade, not a claim that every historical row has already been migrated.

## Deployment prerequisite

`render.yaml` now declares `PATIENT_MEDIA_RECEIPT_KEY` as `sync: false`. Before deploying this branch, the repository owner must configure a stable, independently generated 32-byte random value (64 hex characters) in the Render service environment. Do not reuse `VOICE_ASR_RECEIPT_KEY`, an account secret, a password or a source-controlled value. Keep the key stable while any version-1 receipts need replay. It was not configured or changed by this work, and no deploy was performed.

## Verification and limits

- The exact helper logic was copied to an isolated scratch harness and its eight committed helper scenarios passed: key validation, HMAC stability/key separation/owner-patient scoping, legacy upgrade, replay, changed-content conflict, status-only migration, scope mismatch, version-type tampering and corrupt payload rejection.
- The new repository tests are committed and registered, but the complete repository Python/security suite and Android typecheck have not run.
- Current-head Android and Security recovery jobs are still failing before the first runner step; the latest rerun has `runner_id=0`, empty runner name, `steps=[]` and no downloadable log blob. This is not a Python assertion or TypeScript compiler diagnostic.
- Android/iOS physical-device upload, camera, process-death, large-file, offline/reconnect and gallery screenshot acceptance remain open.

No merge to main, production deployment, APK/IPA publication or patient-record mutation occurred.
