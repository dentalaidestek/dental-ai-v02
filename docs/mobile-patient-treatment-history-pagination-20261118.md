# Native patient treatment-history pagination — 2026-11-18

## Web-first comparison

Before changing the native profile, the canonical web path was re-read:

- `app/main.py::patient_detail` loads the patient's complete treatment list ordered by `Treatment.created_at DESC`.
- `app/templates/patient_detail.html` renders the first three rows and hides later rows until `toggleTreatments()` is used.
- The native `mobile_patient_detail` endpoint previously called `.all()` for every treatment even though `NativePatientProfile` initially displayed only three. The mobile screen therefore transferred and retained the full history before the user asked to see it.

The visible web behavior remains: first three rows, then an explicit “Diğer tedavileri göster” action. Native now preserves that interaction without downloading the entire history on profile open.

## Backend contract

- `GET /api/mobile/v1/patients/{patient_id}` returns at most three treatments and `treatments_next_cursor`.
- `GET /api/mobile/v1/patients/{patient_id}/treatments?cursor=...` returns at most 20 older treatments and `next_cursor`.
- Each request re-checks `Patient.owner_user_id == authenticated user.id`. Missing and other-owner patients remain indistinguishable (404).
- Both profile and history responses use `Cache-Control: private, no-store`, `Pragma: no-cache`, and `Vary: Authorization`.
- Cursor payload binds version, authenticated owner ID, patient ID, a maximum treatment-ID snapshot, and the last `(created_at, id)` tuple. It is URL-safe base64, not an authorization token or a secret; authorization always comes from the Bearer session and owner check. It contains no patient name, phone, diagnosis, note, or treatment text.
- The maximum ID is captured on the first profile request. Every later page filters `Treatment.id <= snapshot_id`, so rows inserted after page one cannot appear midway through the same history. Stable ordering uses `created_at DESC, id DESC`; the ID tie-breaker prevents same-timestamp duplicates or gaps.
- Invalid, cross-owner, cross-patient, malformed, timezone-aware, out-of-range, or wrong-version cursors return 422. A deleted or transferred patient is checked before cursor use.

## Query performance and schema

- `Treatment` declares `ix_treatment_patient_created_id(patient_id, created_at, id)`.
- Schema revision 19 adds the index to existing PostgreSQL databases with `CREATE INDEX CONCURRENTLY`, a dedicated advisory lock, a 10-second lock timeout, and a bounded statement timeout. An invalid index left by an interrupted build is removed concurrently and retried. SQLite uses transactional `CREATE INDEX IF NOT EXISTS` for local/API tests.
- The migration validates index validity and exact column order before advancing revision 19.
- The migration code is committed only. It was **not** run against production or any connected database in this work.

## Native behavior

- The first three treatment rows render immediately.
- Older rows are requested only after the user opens the history.
- Pages append without replacing verified rows. Duplicate IDs and cursor cycles are rejected before state mutation.
- A failed page keeps both existing rows and the same cursor so the user can retry.
- Profile refresh, patient/account switch, and unmount invalidate in-flight page responses. A response from a previous patient or token cannot append to the current profile.
- Loaded pages can be collapsed locally; reopening already loaded rows does not issue another request.
- Existing treatment `edit_revision`, create/update idempotency receipts, pending-intent recovery, and 409 conflict handling remain unchanged.

## Regression coverage added

- `tests/test_mobile_patient_parity.py`: bounded first page, same-timestamp ordering, stable snapshot after a new insert, two subsequent pages, no duplicate IDs, private cache headers, cursor scope rejection, malformed cursor rejection, empty history, and other-owner 404.
- `tests/test_postgres_optimization.py`: revision-18-to-19 online index migration, index validity/columns, and updated expected current schema revision.
- `mobile/tests/patientApi.cjs`: initial-page and continuation-cursor validation, no-network rejection for invalid inputs, duplicate/malformed/cyclic/truncated page rejection.
- `mobile/tests/patientProfileUI.cjs`: first-page-only rendering, load-more/collapse, retry without data loss, duplicate-page rejection, account/patient switch with a late response, and double-tap single-flight.
- Security Recovery's native clinical job now includes `patientApi.cjs` and `patientProfileUI.cjs`. The existing Python security job already includes the patient parity and PostgreSQL optimization test files.

## Verification and limitations

The tests and migration checks are committed but were not executed in this connector runtime. The current branch has no Actions run associated with the starting HEAD. The most recent inspected Android typecheck and Security Recovery jobs ended before their first step: their job step arrays were empty, and the log endpoint returned the known `BlobNotFound 404` condition. The compiler, pytest, PostgreSQL migration, Expo export, and Gradle did not start. No source-level pass is claimed.

No automatic workflow trigger was enabled. No main merge, production migration, live deployment, APK/IPA publication, or patient-record mutation occurred.
