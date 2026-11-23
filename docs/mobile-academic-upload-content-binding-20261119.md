# Native Academic upload content binding — 2026-11-19

## Web contract inspected first

The canonical web handler is `upload_study_materials` in `app/main.py`, reached from `/notes/courses/{course_id}/materials`. For idempotent single-file requests it:

- reads the upload in 1 MiB chunks and computes SHA-256 while writing the object;
- builds a payload digest over owner, course, filename, MIME, byte size and content SHA-256;
- inserts the material and owner/course/request-key receipt in the same database transaction;
- compares an existing receipt's payload digest on replay, returning 409 for a different payload and 410 when the original material was deleted;
- returns a minimal receipt without storage paths or provider identifiers.

The mobile adapter calls this same handler through `app/mobile_academic_api.py`; no separate mobile upload store or weaker idempotency rule was introduced.

## Native gap found

The durable server receipt already carried `content_sha256` and `payload_hash`, but the native client only checked that both values looked like 64-character hashes. The persisted v2 intent contained account/course/request key/name/MIME/size but no expected content digest. Recovery compared only filename, MIME and size before deleting the private cache file. Two different files with the same name and byte count could therefore pass the client-side recovery check.

The upload acknowledgement had the same gap: it validated receipt metadata but did not compare the server's content digest to the bytes selected before upload.

## Changes

- Added `academicFileHash.ts`: Expo SDK 54 `FileHandle` reads private cache files in bounded 1 MiB chunks and feeds an incremental SHA-256 hasher. A 150 MiB file is never materialized as one JS string or ArrayBuffer. Path containment, encoded traversal, file size and short-read checks fail closed; the file handle closes in `finally`.
- New uploads persist a v3 SecureStore intent containing the exact local SHA-256 before sending bytes. The server receipt must return the same digest before the local temporary file can be removed.
- Existing v2 intents remain readable. When a v2 retry has no receipt, the still-private local file is hashed and the intent is upgraded to v3 before a retry. If a receipt already exists, recovery compares the local bytes (when still present) to the durable server digest.
- A missing local file is treated as already cleaned only when the matching durable server receipt exists. A missing file without a receipt blocks retry.
- Same-name/same-size content mismatches preserve both the local file and the pending intent; they are never silently acknowledged or deleted.
- Leaving the Academic screen during a hash/retry prevents a later network upload from starting.
- Added regression coverage to `academicFileHash.cjs`, `academicFileSecurity.cjs` and `academicWorkflow.cjs`; registered the hash suite in `test:beta` and the manual Academic Security Recovery job.

## Verification boundary

The repository exposes no current workflow run or combined status for the PR head checked at the start of this review. Android CI and Security Recovery are intentionally `workflow_dispatch`-only while hosted runner allocation fails before the first step. No workflow was dispatched, to avoid restarting the notification stream. The new Node tests are committed and registered but have **not** been executed here; full TypeScript typecheck, Expo export, APK build, physical-device hashing time/battery and large-file acceptance remain open.

No new dependency, database migration, main merge or production deployment.
