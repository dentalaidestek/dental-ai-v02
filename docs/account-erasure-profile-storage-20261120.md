# Account-erasure object cleanup — 2026-11-20

## Scope

Account erasure now hands only server-generated profile and identity-document objects to the existing durable `WorkGarbage` collector. The database metadata is cleared/deleted and the cleanup receipt is inserted in the same transaction. No new table or migration is required.

Accepted object-key shapes are intentionally narrow:

- `uploads/profile_photos/user_{id}_{random-token-16}.jpg`
- `uploads/expert_credentials/user_{id}/credential_{uuid}.{pdf,jpg,jpeg,png}`
- `uploads/expert_title_changes/user_{id}/title_{uuid}.{pdf,jpg,jpeg,png}`
- `uploads/membership_documents/user_{id}/{uuid}.{pdf,jpg,jpeg,png}`

The collector re-checks User.profile_photo_path, ExpertProfile.credential_document_path, ExpertTitleChange.credential_document_path and MembershipVerification.document_path before deleting. If any record still references an object, the receipt is retired without deleting the object. This protects shared/reused paths and concurrent ownership changes.

R2 failures retain the receipt and use bounded exponential retry delays (5, 10, 20 … up to 360 minutes); a later worker invocation can finish the deletion. Existing attempt-count fencing protects a re-queued receipt from an older collector. Unknown legacy paths remain on the prior caller fallback and are not admitted into the generic worker allowlist.

## Replacement lifecycle

The web account, expert-profile and pending-title document handlers now enqueue a superseded allowlisted reference in the same database transaction that switches its metadata pointer. New uploads whose metadata transaction fails are also handed to the durable collector rather than being deleted directly. The collector re-checks all supported references before deleting and retains the receipt on R2 failure.

Profile-photo keys now use a fresh random 16-hex token per upload instead of a content hash. This prevents a later upload of identical image bytes from reusing a path already queued for deletion, which would otherwise create a check/delete race between PostgreSQL and R2. Existing hash-based keys remain accepted by the strict cleanup allowlist for backward compatibility.

Rejected membership verification rows continue to retain their document reference as review history; this change does not define a retention or purge policy for those rows.

## Data-retention boundary

- Patient, Analysis, ImageAsset, PatientMedia, Treatment and tooth records are not removed by clinician account erasure.
- Guest AI data and academic material deletion continue through their existing dedicated cleanup flows.
- Expert title-change audit rows remain, but their private credential path/name/MIME are cleared.
- Membership verification rows are removed and their uploaded documents are queued.
- No identity document bytes, patient data, email, password, token or raw path is written to logs.

## Regression coverage

`tests/test_account_erasure_cleanup.py` covers account metadata scrubbing, all four asset classes, strict path allowlisting, R2 failure/retry, still-referenced object protection, transactional replacement receipts and unique profile-photo keys.

`tests/test_postgres_optimization.py` now keeps terminal reminder history in the due-time range, making the (status, run_at) index selective in the synthetic 60k-account query-plan test instead of asserting a composite index while every reminder row had the same PENDING status.

These are source changes on the mobile parity branch. CI must execute them before acceptance. No main merge, production deployment, migration, or store publication was performed.
