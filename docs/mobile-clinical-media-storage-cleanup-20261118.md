# Durable clinical-media object cleanup — 2026-11-18

## Web-first finding

Reviewed the canonical gallery in `app/templates/patient_detail.html`, the web delete handlers in `app/main.py`, and the native gallery plus bearer API in `mobile/src/NativePatientMedia.tsx`, `mobile/src/modernApi.ts`, and `app/mobile_api.py`.

The database row was deleted before remote object deletion. If R2 deletion failed after the commit, the web route could return an error with the row already gone; retrying then had no file reference to clean. The native single-delete route logged the failure but explicitly left orphan reconciliation to operators. Delete-all also loaded every media row and synchronously deleted every object in the request, with no durable retry record.

## Changes

- Reuse the existing `WorkGarbage` table and `work_worker` maintenance path; no schema migration or new service.
- Add a strict allow-list for the two server-generated patient-media object-key layouts: legacy web `uploads/patient_<id>_<uuid>.<image>` and native `uploads/patient-media/patient_<id>_<uuid>.<image>`.
- Enqueue the opaque storage key in the same database transaction that deletes its `PatientMedia` row. A rollback therefore leaves both the row and the absence of a cleanup receipt consistent.
- Extend the existing garbage collector to delete only a patient-media object that matches the allow-list and is no longer referenced by any live `PatientMedia.file_path`.
- Failed R2 deletes retain the durable queue row and retry after five minutes. A repeated delete of an already absent row remains an idempotent success.
- Web delete-all now walks 100-row chunks while holding the patient row lock, flushing and expunging each chunk to bound ORM memory. Upload and delete paths use the same patient lock on PostgreSQL.
- Unrecognized legacy paths retain the previous synchronous deletion fallback rather than being admitted to a broader object-key namespace.

## Privacy and scale

The cleanup queue stores only the opaque server-generated storage reference; it does not store patient name, filename metadata, notes, image bytes, or clinical content. The object is not deleted if a live media row still points to it. Remote object I/O is removed from the normal supported delete request path, and cleanup is retried by the existing worker. No new polling loop, provider call, external service, or migration was introduced.

## Regression coverage

Added `tests/test_patient_media_cleanup.py` for strict path admission, deduplicated queue insertion, transaction rollback, worker deletion, live-reference protection, delayed retry after storage failure, and web/native route wiring. The Security Recovery workflow includes the new test and `app/work_jobs.py`.

The tests are committed but were not executed in this GitHub-connector run. The starting-head Android and Security jobs had null step lists and null log URLs; a typecheck job-log fetch returned `BlobNotFound 404`. No TypeScript, pytest, Gradle, or PostgreSQL run is claimed.

No main merge, production deploy, migration, APK/IPA publication, or patient-record mutation.


## Native response validation follow-up

The native delete transport previously accepted any JSON object returned with HTTP 200. It now requires `ok === true`, the exact requested `media_id`, and correctly typed optional `already_deleted` / `storage_cleanup_pending` receipt fields before the gallery clears its uncertain-delete state. Two renderer/transport regressions were added to the existing `clinicalMediaRecovery.cjs` file, which is already part of `npm run test:beta`. They are committed but remain unexecuted while Actions jobs terminate before steps.
