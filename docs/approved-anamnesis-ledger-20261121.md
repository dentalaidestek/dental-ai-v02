# Approved anamnesis ledger — 21 November 2026

## Canonical flow

The web clinician approval action remains the only writer: `POST /patients/{patient_id}/voice-exam/apply`. Native calls the same endpoint with its bearer session. The existing patient ownership check and `SELECT ... FOR UPDATE` patient lock run before any write. A successful approval writes, in one database transaction:

1. The existing `Analysis` row with the exact approved clinical notes.
2. The existing minimal, idempotent `VOICE_REVIEW` `WorkJob` receipt (no transcript/audio/provider payload).
3. One append-only `approvedanamnesis` row for each selected allowlisted anamnesis field, retaining `owner_user_id`, `patient_id`, `field_key`, `value`, and the original `analysis_id`.

The new table is an append-only ledger, not a mutable "current value" cache. The latest row by monotonically assigned row ID is the current approved statement for that patient/field; older approvals and their original Analysis IDs remain queryable. Patient-row locking serializes approvals for the same patient, and the unique `(analysis_id, field_key)` constraint prevents duplicate field provenance. Replaying the same request key returns the existing analysis before inserting another ledger row. The covering `(owner_user_id, patient_id, field_key, id)` index supports the profile's owner-scoped latest-value query without separate owner, patient, analysis, and timestamp indexes.

## Read behavior and privacy

`reviewed_history_payload()` now reads the indexed ledger, selecting the latest value independently for every allowlisted field. It no longer scans or limits the last 12 voice analyses. The existing JSON shape is preserved (`value`, empty `quote`, original `analysis_id`, notice and revision), so the web patient profile and native patient profile keep using the same history endpoint without separate storage contracts.

The reader first verifies that the requesting clinician owns the patient, then additionally scopes rows by both `owner_user_id` and `patient_id`. Only the seven explicit history fields are exposed. Transcripts, raw audio, provider payloads, unapproved extraction, and generic clinical notes are not copied to the ledger. Negative patient statements remain exact statements and are not converted into diagnoses or active medication claims. The normal patient-delete transaction explicitly deletes that patient's ledger rows after ownership authorization, before deleting the patient.

## Revision 21 migration and legacy backfill

`python -m app.migrate` adds `approvedanamnesis` as an additive schema revision 21. A fresh or legacy baseline is deliberately stamped revision 20 first, even when `init_db()` has already created the ledger table, so the migration cannot mistake an empty newly-created table for a completed backfill. It reads only completed `ANALYSIS / VOICE_REVIEW / DONE` WorkJobs joined to their original Analysis records and a Patient row whose owner matches the WorkJob owner. It parses the same seven allowlisted field labels, keeps each original `analysis_id`, and inserts in keyset pages of 500 with a database timestamp. Existing Analysis and WorkJob rows are never updated or deleted. The unique analysis/field constraint plus `ON CONFLICT DO NOTHING` makes retries idempotent. Revision 21 is advanced only after the backfill succeeds. A database already stamped revision 21 but missing the ledger table can still create it; startup fails closed if the ledger table or covering query index is absent.

The migration uses a transaction-scoped PostgreSQL advisory lock, bounded lock/statement timeouts, and one transaction for table creation, paged backfill and revision advancement. No production migration was run as part of this code change.

## Regression coverage added

- More than 12 later reviews do not hide an older allergy value.
- Re-approval returns the latest value while retaining earlier rows and their original Analysis IDs.
- Idempotent replay does not duplicate ledger rows.
- Migration backfills 503 records across multiple 500-row pages, excludes non-voice work, preserves owner/patient/source IDs, and is safe to retry.
- A fresh database already stamped revision 21 still creates the table.
- A PostgreSQL database-level row-lock regression holds the patient row lock, confirms a second transaction is blocked in `pg_stat_activity`, then verifies both ledger rows and original Analysis IDs survive in order. This validates the database serialization primitive; it is not an end-to-end concurrent HTTP test.
- Web-cookie and native-Bearer history reads return the same approved field contract; stale second approvals are rejected without adding a ledger row.
- Patient deletion removes ledger rows only after the existing owner authorization succeeds.
- Startup rejects a revision-21 database if the ledger table or covering lookup index is missing.

## Validation boundary

The changes are committed to `feature/mobile-web-parity-20261110` / PR #257. Security Recovery now includes `tests/test_approved_anamnesis_migration.py`. The repository's hosted Actions results must be checked against the final pushed HEAD before this work is accepted. No claim is made that production PostgreSQL migration, real-user concurrency or full CI has been executed locally. No main merge, production deploy, or patient-record mutation was performed.
