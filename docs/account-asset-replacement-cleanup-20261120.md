# Account asset replacement cleanup — 2026-11-20

## Web-first flow reviewed

Before editing, the canonical web upload/update handlers were traced:

- `/account/profile-photo` → `account_profile_photo`
- `/expert-support/profile` → `expert_support_profile_save`
- `/account/professional-title/document` → `professional_title_document_upload`

The native professional adapter in `app/mobile_professional_api.py` delegates document and expert-profile writes to those same web handlers. The existing durable collector is `WorkGarbage` in `app/work_jobs.py`; it accepts only server-generated account-asset key layouts and checks User, ExpertProfile, ExpertTitleChange and MembershipVerification references before deleting.

## Gap found

The account-erasure path already queued current profile/credential objects durably, but replacing an existing profile photo or credential document only changed the metadata pointer. Profile photos used a best-effort direct delete after commit; credential/title-document replacements did not enqueue the superseded object. A storage failure could therefore leave private identity documents in R2 indefinitely.

The expert profile form also wrote a replacement credential before validating ORCID. An invalid ORCID could return HTTP 400 after the new object had already been written.

## Changes

- Added `enqueue_replaced_account_asset_cleanup(session, previous, current)`. It is a no-op for empty or same-path values and delegates to the existing strict allowlist.
- Profile-photo and credential/title-document replacements enqueue the old reference in the same SQL transaction that switches the metadata pointer.
- The profile-photo post-commit helper no longer directly deletes current-format generated keys; those are collected only through the durable receipt. Unknown legacy profile-photo keys retain the old best-effort fallback.
- New account objects whose metadata transaction fails are queued for cleanup in a fresh short transaction. They are not directly deleted because profile-photo keys are content-addressed and may still be referenced by the current account.
- Expert credential bytes are staged in memory and written only after the ORCID validation succeeds.
- The mobile professional API needs no parallel implementation because it continues to delegate to the canonical web handlers.

No schema or migration change was needed. Patient, Analysis, ImageAsset, PatientMedia, Treatment and tooth records are untouched.

## Regression coverage added

`tests/test_account_erasure_cleanup.py` now includes:

1. Only a different, allowlisted previous object is queued.
2. Replaced profile photo, expert credential and title-change document objects are collected after the metadata switches, while new paths remain referenced and intact.
3. Web-handler source contract checks for transactional queue insertion, failed-upload cleanup and ORCID-before-storage ordering.

The test file is already included in the Python Security Recovery command in `.github/workflows/security-recovery.yml`.

## Remaining limits

- The new pytest cases have been committed but not executed in this run; the latest known PostgreSQL/Security Recovery run still had a planner-index assertion failure, and current HEAD has no published status checks.
- Unsupported legacy credential/title paths are deliberately not admitted to the generic cleanup allowlist. They need a separate migration/repair review rather than broadening deletion patterns.
- Rejected membership verification rows continue to retain their document reference as review history. Their retention/purge policy is a separate legal/product decision; this change does not erase that history.
- No physical device, browser acceptance or 60,000-user load test was run.

No main merge, production deployment, migration, APK/IPA publication or patient-record mutation was performed.
