# Native analysis receipt-first recovery — 2026-11-19

## Web and backend flow checked first

Reviewed the authenticated web composer in `app/templates/analysis_new.html`, the analysis viewer wrapper in `app/templates/analysis_viewer.html`, the radiograph viewer script in `vision_service/templates/radiograph_viewer.js`, and the native flow `NativeAnalysisUpload → NativeDentalAI → NativeClinicalReview → NativeVisionViewer`.

The native upload path already supports up to four combined existing/new images, FDI tooth context, bounded clinical notes, encrypted local image drafts, a stable request key, a server-side idempotency receipt, cancellation with uncertain-outcome preservation, and reopening the existing analysis without creating a second upload. The native viewer already loads authorized assets with bearer headers, uses modality-aware finding parsing, keeps unlocalized findings in the list without inventing a box, and exposes findings/treatment/clinical-info tabs.

## New recovery defect

The upload success path removes encrypted local image files and then deletes the SecureStore intent. A process death between those two operations leaves a durable intent whose encrypted files may already be gone, while the server has a valid upload receipt and analysis. The old restore order called `ensureEncryptedAnalysisImages` before querying the server receipt. If the encrypted files had already been removed, restore failed closed and hid an analysis that was already safely persisted server-side.

## Fix

`NativeAnalysisUpload` now queries the authenticated, owner/patient-scoped upload receipt immediately after parsing the durable intent and before validating, migrating, decrypting, or deleting any local image. When a valid receipt exists, it retries idempotent local cleanup, removes the intent, and opens the already-created analysis. If receipt lookup is unavailable, the local files and durable intent remain untouched; no new upload starts. If no receipt exists, the previous encrypted-file migration and explicit same-key retry flow continues unchanged.

The backend receipt endpoint and HMAC fingerprinting were not changed. Patient ownership, existing-media patient scoping, request-key binding, image limits, and no-auto-write-to-tooth-chart behavior remain unchanged.

## Regression coverage added

- Server receipt exists but encrypted local images were already removed: restore opens the existing analysis without a second upload.
- Receipt lookup returns a transient 503: the intent remains durable and local image validation/cleanup is not started.
- Existing failed-cleanup and same-key retry regressions remain in the test file.

Tests are registered through the existing `npm run test:beta` script. This connector-only session did not execute the React Native renderer suite, full typecheck, Expo export, Android Gradle build, or physical-device flow. Source changes and test registrations are committed, but no test pass is claimed for those unexecuted commands.

## Scope and safety

No provider, prompt, clinical taxonomy, database schema, API route, production setting, or patient record was changed. No main merge or production deploy was performed.
