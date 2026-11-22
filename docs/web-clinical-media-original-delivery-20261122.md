# Web clinical-media original delivery race — 2026-11-22

## Web-first flow inspected

Before changing the native or shared client, traced the web patient-profile gallery:

- `app/templates/patient_detail.html`: a thumbnail opens the original image through `/patients/{patient_id}/media/{media_id}/file`.
- `app/main.py::patient_media_file`: cookie-session authentication, patient/media owner checks, then object-store hydration.
- `app/main.py::patient_media_thumbnail`: the thumbnail route already rechecks patient ownership, media ownership and the exact source reference after storage hydration.
- Native comparison: `app/mobile_api.py::mobile_patient_media_file` already performs a post-hydration patient/media/source recheck and uses private no-store response headers.

## New gap

The web original-file route performed the initial ownership check, released the database session, hydrated the original from R2/local object storage, and returned the file without a second authorization check. A patient/media deletion, ownership change or file replacement during the storage wait could therefore leave a stale response eligible to serve the original.

The thumbnail route and native original-file route already had the required post-hydration fence; the web original-file route was the outlier.

## Correction

- Capture the authorized patient/media source identity before storage I/O.
- Keep R2 hydration outside the SQL connection pool.
- After hydration, reload the patient and media and require the same patient relation, file path and original filename.
- Recheck patient and media ownership for ordinary clinicians. Preserve the existing ADMIN access semantics.
- Fail closed with a private 503 response if the second database check cannot complete.
- Return explicit JPEG/PNG/WebP content types and private `no-store`, `Vary: Cookie`, `nosniff` and restrictive CSP headers for success and error responses.

No original object is deleted by the request path. Existing durable cleanup receipts remain responsible for deletion, avoiding a race with another valid reference.

## Regression coverage

`tests/test_clinical_media_original_delivery.py` covers:

- authorized inline original response and private headers;
- media deletion while object storage is hydrating;
- patient deletion while object storage is hydrating;
- patient/media owner change during hydration;
- original file-path/filename replacement during hydration;
- ADMIN compatibility;
- storage outage retry behavior;
- cross-account rejection before storage access;
- database failure during the post-hydration authorization recheck.

The file is included in the Security Recovery Python test command.

## Validation boundary

Starting HEAD `ba7389e933730fbcd30c904f9482e5c49d7b2da1` had green Android typecheck/APK and Security Recovery jobs. The new code/test HEAD is `09d63770f45767063e066faab1240fff3fdae3b8`; Android and Security Recovery runs `45035764576` and `45035764598` were created but had no job records at the last check. No test execution on the new code is claimed until those workflows start and finish.

No patient data, R2 object, schema, migration, main branch or production deployment was changed.
