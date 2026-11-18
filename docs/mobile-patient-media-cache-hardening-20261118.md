# Native patient media cache hardening — 2026-11-18

## Web-first comparison

Reviewed `app/templates/patient_detail.html` first. The web patient gallery exposes clinical photo/radiograph thumbnails, notes, tooth association, upload dates, selection for analysis, and deletion. The native gallery uses the owner-scoped paginated endpoint `GET /api/mobile/v1/patients/{patient_id}/media`, with separate authenticated upload-receipt and image-file endpoints.

The native listing already checked both `Patient.owner_user_id` and `PatientMedia.owner_user_id`, used a bounded `limit + 1` query, and returned a descending ID cursor. However, unlike the patient-detail and treatment-history endpoints, it did not set `Cache-Control: private, no-store`, `Pragma: no-cache`, or `Vary: Authorization`. The receipt and file endpoints set only `Cache-Control`, leaving the authorization variance and legacy no-cache directives inconsistent. Upload acknowledgements and idempotent replay responses had the same partial policy.

## Changes

- The paginated clinical media listing now calls the existing `_mobile_private_no_store` helper.
- Upload status/receipt JSON responses use the same helper.
- Authenticated clinical image `FileResponse` objects use the same helper.
- New upload acknowledgements and both idempotent replay paths use the same helper.
- No new cache, storage, authentication, or database dependency was introduced.
- Existing owner checks, page limits, cursor semantics, upload receipts, image sanitization, and durable object cleanup remain unchanged.

The shared helper emits `Cache-Control: private, no-store`, `Pragma: no-cache`, and appends `Authorization` to `Vary` without removing existing variance values.

## Regression coverage

Added `test_mobile_patient_media_responses_are_private_and_owner_scoped` to `tests/test_mobile_patient_parity.py`. It covers:

- A synthetic owner-scoped clinical image upload and its private response headers.
- Same-key upload replay and private response headers.
- First and subsequent media pages, including cache headers.
- Upload receipt lookup and cache headers.
- Authenticated image bytes and cache headers.
- 404 behavior for a second account attempting to list, inspect a receipt, or fetch the image.

The existing Security Recovery Python job already includes `tests/test_mobile_patient_parity.py`; no workflow trigger was changed.

## Validation and limits

GitHub source review confirmed that the new regression file is already in the Security Recovery pytest command. The updated Python/React Native test suites were not executed in this run. No current-head Actions run or combined status check was available after these commits, so no CI pass is claimed. The historical Android/runner failures remain pre-step execution failures; they do not establish a TypeScript or pytest source failure.

No patient records, media objects, or production database rows were changed. No migration, main merge, live deploy, APK/IPA publication, or workflow dispatch was performed.
