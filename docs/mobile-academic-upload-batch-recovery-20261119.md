# Academic AI native multi-file upload recovery — 2026-11-19

Branch: `feature/mobile-web-parity-20261110` · PR #257 (Draft) · issue #258.

## Web flow inspected first

- `app/templates/notes_course.html` exposes one file input with `multiple`, PDF/JPG/PNG/WEBP, and a 150 MB per-file limit.
- `app/main.py:upload_study_materials` accepts a bounded batch (the backend's configured maximum), streams each file in 1 MiB chunks, validates its signature, and writes the material records.
- The native adapter `app/mobile_academic_api.py:upload_materials` deliberately accepts one file per idempotent request. It delegates to the same canonical web handler and returns an owner/course/request-key-scoped receipt containing the content SHA-256 and payload digest.
- The earlier native screen copied all selected assets, then hashed and uploaded them one at a time while persisting only one SecureStore intent.

## Root cause

If the app was killed or the second file failed, later files selected in the same multi-select operation had already been copied into the private cache but had no durable request intent. Only the currently processed file could be reconciled after restart. This differed from the web page's single multi-file selection and made native batch recovery incomplete.

## Changes

- Added `academicUploadQueue.ts`: a versioned queue scoped to the authenticated user and course, capped at 12 entries, rejecting duplicate names/URIs/request keys and preventing a request key from being rebound to a different file identity or digest.
- The full selected batch is written before the first hash or network upload. The queue uses the existing `chunkedDraftStore` wrapper rather than placing a potentially large manifest in one SecureStore value.
- Each file retains its own stable request key. Files are hashed in bounded 1 MiB chunks, upgraded from legacy v2 to content-bound v3, and uploaded sequentially through the canonical adapter.
- A local cache file is removed only after the matching server receipt, course, request key, name, MIME, size and content digest are validated. Uncertain results retain the current and remaining queue entries for receipt reconciliation.
- On restore, every queued item is checked against its durable server receipt before it is considered complete. The previous single-item SecureStore key is migrated into the queue before the legacy key is deleted; a v3 digest is never downgraded by an old v2 key.
- Freshly selected files skip an unnecessary pre-upload receipt lookup. Retry/restore paths still reconcile first, avoiding duplicate uploads without adding one extra API request to every new file.
- Picker URIs are verified to be inside the app-private cache before any intent is persisted. Empty files and mismatched MIME/extension are rejected before upload.

## Regression coverage

Added `mobile/tests/academicUploadQueue.cjs` with 13 Node tests covering account/course binding, malformed manifests, queue limits, duplicate entries, v2/v3 upgrades, immutable request identity, legacy migration, sequential multi-file persistence, fresh-upload request count and TypeScript parser diagnostics. Registered in `npm run test:beta`.

## Verification boundary

The 13 tests are committed and registered but were **not executed** in this connector-only run. Full `npm run typecheck`, `npm run test:beta`, Expo export, Android build, real API receipt reconciliation, app-process-death and 150 MB Android/iOS device tests remain open. The current PR head has no associated workflow run or combined status; Android and Security Recovery are manual-only while the hosted runner failures are unresolved. No CI dispatch was made.

No provider, clinical taxonomy, AI prompt, database schema, dependency or backend route was changed. No patient record was written. No main merge or production deployment.
