# Approved anamnesis ledger — 21 November 2026

## Canonical flow

The web clinician approval action remains the only writer: `POST /patients/{patient_id}/voice-exam/apply`. Native calls the same endpoint with its bearer session. The existing patient ownership check and `SELECT ... FOR UPDATE` patient lock run before any write. A successful approval writes, in one database transaction:

1. The existing `Analysis` row with the exact approved clinical notes.
2. The existing minimal, idempotent `VOICE_REVIEW` `WorkJob` receipt (no transcript/audio/provider payload).
3. One append-only `approvedanamnesis` row for each selected allowlisted anamnesis field, retaining `owner_user_id`, `patient_id`, `field_key`, `value`, and the original `analysis_id`.

The new table is an append-only ledger, not a mutable "current value" cache. The row with the greatest source `analysis_id` is the current approved statement for that patient/field; older approvals and their original Analysis IDs remain queryable. This remains correct if a legacy backfill inserts an older source analysis after a newer approval already exists. Patient-row locking serializes approvals for the same patient, and the unique `(analysis_id, field_key)` constraint prevents duplicate field provenance. Replaying the same request key returns the existing analysis before inserting another ledger row. The covering `(owner_user_id, patient_id, field_key, analysis_id)` index supports the profile's owner-scoped latest-value query without separate owner, patient, row-ID, and timestamp indexes.

## Read behavior and privacy

`reviewed_history_payload()` now reads the indexed ledger, selecting the latest value independently for every allowlisted field. It no longer scans or limits the last 12 voice analyses. The existing JSON shape is preserved (`value`, empty `quote`, original `analysis_id`, notice and revision), so the web patient profile and native patient profile keep using the same history endpoint without separate storage contracts.

The reader first verifies that the requesting clinician owns the patient, then additionally scopes rows by both `owner_user_id` and `patient_id`. Only the seven explicit history fields are exposed. Transcripts, raw audio, provider payloads, unapproved extraction, and generic clinical notes are not copied to the ledger. Negative patient statements remain exact statements and are not converted into diagnoses or active medication claims. Both web and native patient-delete paths refuse deletion while an approved anamnesis row remains. The native adapter also checks the other clinical dependent models. Neither path silently deletes the append-only ledger; full patient-data erasure remains an audited transactional workflow that must remove all dependent records together.

## Revision 21 migration and legacy backfill

`python -m app.migrate` adds `approvedanamnesis` as an additive schema revision 21. A fresh or legacy baseline is deliberately stamped revision 20 first, even when `init_db()` has already created the ledger table, so the migration cannot mistake an empty newly-created table for a completed backfill. It reads only completed `ANALYSIS / VOICE_REVIEW / DONE` WorkJobs joined to their original Analysis records and a Patient row whose owner matches the WorkJob owner. It parses the same seven allowlisted field labels, keeps each original `analysis_id`, and inserts in keyset pages of 500 with a database timestamp. Existing Analysis and WorkJob rows are never updated or deleted. The unique analysis/field constraint plus `ON CONFLICT DO NOTHING` makes retries idempotent. Revision 21 is advanced only after the backfill succeeds. A database already stamped revision 21 but missing the ledger table can still create it; startup fails closed if the ledger table or covering query index is absent.

The migration uses a transaction-scoped PostgreSQL advisory lock, bounded lock/statement timeouts, and one transaction for table creation, paged backfill and revision advancement. No production migration was run as part of this code change.

## Regression coverage added

- More than 12 later reviews do not hide an older allergy value.
- Re-approval returns the latest source Analysis while retaining earlier rows and their original Analysis IDs.
- A newer preexisting ledger approval remains current when migration later inserts an older legacy source row; ordering uses source `analysis_id`, not ledger insertion order.
- Idempotent replay does not duplicate ledger rows.
- Migration backfills 503 records across multiple 500-row pages, excludes non-voice work, preserves owner/patient/source IDs, and is safe to retry.
- A fresh database already stamped revision 21 still creates the table.
- A PostgreSQL database-level row-lock regression holds the patient row lock, confirms a second transaction is blocked in `pg_stat_activity`, then verifies both ledger rows and original Analysis IDs survive in order. This validates the database serialization primitive; it is not an end-to-end concurrent HTTP test.
- Web-cookie and native-Bearer history reads return the same approved field contract; stale second approvals are rejected without adding a ledger row.
- Web and native patient deletion both block while an approved anamnesis row remains; the native adapter also detects an orphan ledger row whose Analysis provenance is missing.
- Startup rejects a revision-21 database if the ledger table or covering lookup index is missing.

## Validation boundary

The changes are committed to `feature/mobile-web-parity-20261110` / PR #257. Security Recovery now includes `tests/test_approved_anamnesis_migration.py`. The repository's hosted Actions results must be checked against the final pushed HEAD before this work is accepted. No claim is made that production PostgreSQL migration, real-user concurrency or full CI has been executed locally. No main merge, production deploy, or patient-record mutation was performed.

## Follow-up CI diagnosis — 21 November 2026

The Android run attached to the pre-fix PR head completed successfully: TypeScript typecheck, session/auth tests, realtime/pagination tests, all 985 mobile beta regressions, Hermes exports, and the internal ARM64 APK build passed (run #4659). No Android compiler failure is present in that run.

Security Recovery run #2358 executed Python tests and reported 6 failures / 587 passes. Five were stale test contracts exposed by revision 21 and the ledger read-model transition:
- Two push-schema tests still expected the release guard to report revision 20.
- The support migration source assertion still expected revision 20 to own the final release schema.
- The web history test expected 3 rows although it explicitly approved 4 allowlisted fields.
- The native history fixture inserted legacy Analysis/WorkJob rows but did not model the revision-21 backfilled ledger rows now read by the endpoint.

Those assertions/fixtures were updated to preserve the current revision and ledger contract; no production behavior or security assertions were removed. The remaining Bearer-auth test was made hermetic by disabling its cookie stub and directly asserting the non-doctor, unverified, and expired token identities. A separate regression now proves that an Authorization header is authoritative and cannot fall back to a different valid browser-cookie user. The voice resolver was changed accordingly.

The follow-up commits are on `feature/mobile-web-parity-20261110`, current PR head: `4820fbea35ecfad43d8991ab1e32af5ce2539f23`. The first retry pair (Android #4667 / Security Recovery #2366) was cancelled before any jobs were created and provides no test result. The latest code/test head `3812ea9967abe14fd690e4f00c14b4c44e37ed2b` triggered Android #4673 and Security Recovery #2372; both were pending at the last status check. The final `4820fbea` commit only updates this document and is outside the workflows' path filters, so #4673/#2372 are the source-validation runs to await. PostgreSQL migration/concurrency acceptance remains blocked until Security Recovery reaches its PostgreSQL test step.

No production database migration, patient-data mutation, main merge, or live deployment was performed.


## Latest CI root-cause follow-up — 21 November 2026

The PR merge-head Security Recovery run #2374 executed the Python suite and reported 595 passed / 1 failed. The only failure was
`tests/test_voice_exam.py::test_native_bearer_voice_auth_rejects_unverified_expired_and_non_doctor_sessions`.
The fixture's test-only `User.email_verified_at` used `default_factory=datetime.utcnow`, unlike the production `app.main.User` model whose omitted verification timestamp is `None`. Explicitly constructing `User(..., email_verified_at=None)` therefore persisted a verified timestamp in the fixture. The failing assertion exposed a fixture modeling error, not a production authentication regression. The fixture now defaults to `None`, while its two seeded doctor accounts explicitly receive verified timestamps; the unverified-token assertion remains unchanged.

A second schema-integrity gap was found during the same review: startup and the revision-21 idempotent migration checked the covering lookup index but did not verify the unique `(analysis_id, field_key)` provenance contract. Both paths now fail closed when that named unique constraint is absent, preserving existing ledger rows instead of silently accepting duplicate provenance. Migration tests assert the constraint on a successful backfill and verify that a malformed revision-21 ledger is rejected without changing its revision or contents.

The PostgreSQL concurrency regression now additionally simulates an older legacy backfill inserted after newer approvals and a mismatched-owner row. It evaluates the same `MAX(analysis_id)` selection and owner/patient scope used by `reviewed_history_payload()`, proving that the delayed older row cannot replace the current approval and the foreign-owner row is excluded.

These fixes are committed to the feature branch. Their acceptance remains dependent on fresh Security Recovery CI reaching both the Python and PostgreSQL steps. No staging or production database was changed; no main merge or deployment was performed.
