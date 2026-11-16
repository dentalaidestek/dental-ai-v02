# Clinical image upload byte contract — 2026-11-16

This contract is shared by the web UI, Android client, web handlers and native API adapters. All values are binary MiB (1 MiB = 1,048,576 bytes). The backend is authoritative.

| Flow | File count | Per file | File bytes per request/batch |
|---|---:|---:|---:|
| Patient clinical archive | 12 | 12 MiB | 96 MiB |
| One AI analysis | 4 total (saved + new) | 15 MiB | 48 MiB |

## Admission layers

1. The ASGI `RequestLimits` middleware applies route-specific raw HTTP body limits before FastAPI/Starlette multipart parsing. The limits include multipart framing and fields, with a 256 KiB framing allowance, and remain capped by the existing global `DENTAL_MAX_REQUEST_BYTES`.
2. Backend upload helpers read Starlette's parser-calculated `UploadFile.size` (or seek the underlying spooled file) and reject empty, per-file or aggregate overflow before creating an Analysis row or copying clinical bytes. Client `Content-Length`, picker metadata and filenames are not trusted.
3. Bounded copy loops count bytes again while staging. Existing private PatientMedia paths are stat-checked and copied through the same bounded helper; saved + new images share the 48 MiB analysis-work budget.
4. Pillow sanitization retains the 40,000,000 pixel ceiling. File signature/format validation, patient ownership checks, opaque storage names, private storage and no-store access behavior remain in force.
5. Android checks source file sizes before encrypting analysis media, checks decrypted plaintext sizes again before multipart upload, and retains encrypted patient-scoped local drafts. Archive uploads remain sequential single-file HTTP requests, each capped at 12 MiB plus multipart overhead. Every request now carries a random `batch_id` persisted in the SecureStore pending intent and a stable per-file `request_key`. The backend requires both, locks the owned patient row, sums actual streamed byte counts from that batch's committed `PATIENT_MEDIA_RECEIPT` rows, and enforces the same 12-file / 96 MiB aggregate before persisting the next object. Receipt replay is checked first, so retrying an already committed file does not increment the batch quota. The quota is scoped by authenticated owner, patient and opaque batch ID; malformed stored receipt data fails closed. No new table or migration is required because the existing receipt `result_ref` stores the batch ID and its payload stores the original streamed byte count. Legacy receipts remain replayable; older pending drafts receive and persist a batch ID once when reopened. This requires the matching backend and native client to be deployed together; no production deployment has been performed.
6. Mobile archive hashing is incremental; it no longer calls `read_bytes()` to materialize a full clinical image in Python memory.

## Why AI analysis is 15/48 MiB

The former web 25 MiB and native 15 MiB mismatch is resolved downward to 15 MiB. The native encrypted-file implementation currently performs Base64 and AEAD operations on complete file buffers; increasing it to 25 MiB would materially raise peak memory on lower-end devices. A 48 MiB aggregate budget bounds disk staging and downstream decode work while allowing four 12 MiB images or mixed smaller images. The pixel ceiling separately limits decoded-image CPU/RAM cost.

## Verification

- Backend regression file: `tests/test_upload_limits.py`.
- Native regressions: `mobile/tests/uploadLimits.cjs`, `mobile/tests/clinicalMediaPicker.cjs`, `mobile/tests/clinicalMediaBatch.cjs` and the extended `mobile/tests/session.cjs`.
- Cross-request server quota regressions: `tests/test_mobile_patient_parity.py` (`mobile_patient_media_batch`).
- Run backend tests with `pytest -q tests/test_upload_limits.py tests/test_mobile_patient_parity.py -k 'mobile_patient_media_batch or native_uploads_return_confirmed_success'`.
- Run native tests with `cd mobile && npm run typecheck && node --test tests/uploadLimits.cjs tests/clinicalMediaPicker.cjs tests/clinicalMediaBatch.cjs tests/session.cjs`.
- CI/runner results must be checked against the final branch HEAD; no test is considered passed merely because it was committed.
