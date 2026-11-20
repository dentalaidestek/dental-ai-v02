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

## 2026-11-20 — Native thumbnail generation race and private error responses

Starting source: branch commit `2bcea7bf98605198a1bf0a440607b582767154a8`. Before editing, the associated Android run #4302 and Security Recovery #2000 were inspected at job/step level. Android typecheck, session/auth, realtime/pagination, beta regressions, Expo Android/iOS export and internal ARM64 APK all completed successfully. The five native security jobs and Python security/identity plus PostgreSQL migration/concurrency steps also completed successfully. These results belong to the starting commit, not the follow-up commits below.

Web-first comparison re-read `patient_detail.html`, the cookie-authenticated `/patients/{patient_id}/media/{media_id}/thumbnail` handler, the private derivative generator and the native `modernApi.getMedia` / `NativePatientMedia` consumers. The native thumbnail route is registered from `mobile_modern_api_v3.py`; duplicate media list/file routes are filtered in `main.py`, while this unique thumbnail route remains mounted.

A race remained in the native thumbnail route:
- If the patient was deleted or reassigned during R2 hydration, the post-generation `_user_owned_patient` call raised before the newly generated derivative could be removed.
- If a media row kept the same ID and owner but its `file_path` changed during generation, the old derivative could still pass the recheck.
- Error responses from this route did not consistently carry the private/no-store policy, even though successful JPEG responses did.

The route now re-reads the patient and media without raising during the verification phase and requires the exact original `file_path` to remain unchanged. A stale derivative is removed before returning 404. If cleanup or the verification read fails, the route returns a generic private 503 with `Retry-After: 2`; it never serves the derivative. Missing, unsupported and storage-error responses now use the same `Cache-Control: private, no-store`, `Pragma: no-cache`, `Vary: Authorization` and `nosniff` policy. Storage keys and exception messages are not returned to the client.

Regression coverage:
- `tests/test_mobile_patient_parity.py`: source replacement, media deletion, patient reassignment, private success, cross-account denial and generic 404/415/503 failure responses.
- `mobile/tests/patientMediaRoute.cjs`: source contract for exact owner/source recheck, orphan cleanup, private error headers and native thumbnail-vs-original URL usage. This test is already part of `npm run test:beta`.
- Existing upload receipt, pagination, original-file access and owner-isolation behavior is unchanged.

Commits in this follow-up: `1b53aeb` (route hardening), `9dcfc8b` (generation race regressions), `405ec49` (private success/error regressions), `1811a9f` (native/web source contract), plus this evidence update. The new Python and Node tests are committed but have not yet been executed on the new head. No result from #4302/#2000 is being presented as validation of these follow-up commits.

No patient records or media objects were changed. No schema migration, main merge, production deploy, APK/IPA publication or workflow dispatch was performed.
