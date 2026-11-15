# Native mixed clinical-media analysis — 2026-11-16

## Web flow inspected first

- `app/main.py:new_analysis` accepts preselected `media_id` / `media_ids`, checks patient ownership and loads the saved clinical media.
- `app/templates/analysis_new.html` is the web composition surface.
- `app/main.py:create_analysis` accepts `existing_media_id(s)` and new `images` in one multipart request, checks ownership for every saved item, and enforces a four-image combined limit before queuing the canonical VISION job.
- The previous native split was not equivalent: `NativePatientMedia` called the saved-media-only route while `NativeAnalysisUpload` uploaded new files only.

## Native and API change

The patient gallery now opens the same native analysis composer used for new uploads. It carries the selected saved-media IDs into the upload intent, shows their previews, permits additional camera/gallery images, preserves FDI/clinical context, and enforces a combined maximum of four.

The existing `POST /api/mobile/v1/analyses` endpoint now accepts optional `existing_media_ids` alongside new multipart `images`. It:
- validates a strict, unique saved-media ID list;
- checks that every saved item belongs to the requested patient and current owner (ADMIN retains the existing web exception);
- materializes saved files privately, verifies extension, actual image format, byte size and pixel bounds;
- stages all saved and new files before creating the durable VISION job;
- records one analysis with one receipt and one realtime event;
- includes selected IDs in the idempotency digest, while keeping the historical new-file-only digest unchanged for pending uploads from older app versions.

The patient-gallery composer uses a separate SecureStore intent namespace from the Dental AI tab, preventing two mounted screens from competing over one pending upload. Existing new-only drafts keep their old key and digest.

## Regression coverage added

- Mixed saved + new media creates one analysis, two assets, one VISION job and one receipt.
- Saved-media-only analysis is accepted.
- Reusing the same request key with changed saved-media IDs returns conflict.
- Foreign, missing, duplicate, malformed and over-limit saved IDs are rejected.
- A corrupt saved image rejects the whole batch before any file is published.
- Native intent parsing accepts legacy new-only drafts and rejects duplicate/invalid saved IDs or a combined count above four.
- Native multipart includes saved IDs and new files together.
- Gallery selection opens the unified composer and carries the signed-in user and selected patient; switching account/patient closes it.

Tests are committed but **not executed** in this runtime. No result is marked green.

## CI diagnosis

Before this change, raw GitHub job records for the Android and security runs showed `runner_id=0`, an empty `runner_name`, and `steps=[]`; the jobs started and failed within roughly 1–2 seconds. Log downloads returned `BlobNotFound 404`. This is a pre-runner-allocation failure, not evidence of a TypeScript or pytest failure. The workflow trigger now includes `app/mobile_analysis_api.py` so this API's security regressions are selected when it changes. The underlying hosted-runner/account/billing/availability reason is not exposed by the accessible GitHub records and requires repository/organization owner inspection.

## Not yet accepted

- Android typecheck, security pytest, APK build and all new tests must run on a provisioned runner.
- Verify mixed upload on physical Android and iOS devices, including cancellation, process death, slow network, storage/R2 failure and lost response recovery.
- Confirm production R2 behavior and inference queue capacity under concurrency.
- No main merge, live deployment, APK/IPA publication or real patient-data test was performed.
