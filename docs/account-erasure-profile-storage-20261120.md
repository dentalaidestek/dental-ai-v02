# Account-erasure object cleanup — 2026-11-20

## Scope

Account erasure now hands only server-generated profile and identity-document objects to the existing durable `WorkGarbage` collector. The database metadata is cleared/deleted and the cleanup receipt is inserted in the same transaction. No new table or migration is required.

Accepted object-key shapes are intentionally narrow:

- `uploads/profile_photos/user_{id}_{sha256-prefix-16}.jpg`
- `uploads/expert_credentials/user_{id}/credential_{uuid}.{pdf,jpg,jpeg,png}`
- `uploads/expert_title_changes/user_{id}/title_{uuid}.{pdf,jpg,jpeg,png}`
- `uploads/membership_documents/user_{id}/{uuid}.{pdf,jpg,jpeg,png}`

The collector re-checks User.profile_photo_path, ExpertProfile.credential_document_path, ExpertTitleChange.credential_document_path and MembershipVerification.document_path before deleting. If any record still references an object, the receipt is retired without deleting the object. This protects shared/reused paths and concurrent ownership changes.

R2 failures retain the receipt and use bounded exponential retry delays (5, 10, 20 … up to 360 minutes); a later worker invocation can finish the deletion. Existing attempt-count fencing protects a re-queued receipt from an older collector. Unknown legacy paths remain on the prior caller fallback and are not admitted into the generic worker allowlist.

## Data-retention boundary

- Patient, Analysis, ImageAsset, PatientMedia, Treatment and tooth records are not removed by clinician account erasure.
- Guest AI data and academic material deletion continue through their existing dedicated cleanup flows.
- Expert title-change audit rows remain, but their private credential path/name/MIME are cleared.
- Membership verification rows are removed and their uploaded documents are queued.
- No identity document bytes, patient data, email, password, token or raw path is written to logs.

## Regression coverage

`tests/test_account_erasure_cleanup.py` now covers account metadata scrubbing, all four asset classes, strict path allowlisting, R2 failure/retry across collector invocations and still-referenced object protection.

`tests/test_postgres_optimization.py` now keeps terminal reminder history in the due-time range, making the (status, run_at) index selective in the synthetic 60k-account query-plan test instead of asserting a composite index while every reminder row had the same PENDING status.

These are source changes on the mobile parity branch. CI must execute them before acceptance. No main merge, production deployment, migration, or store publication was performed.
