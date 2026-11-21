# Account erasure: guest analysis cleanup and clinical retention

Date: 2026-11-20  
Branch: `feature/mobile-web-parity-20261110`  
PR: #257 · Issue: #258

## Web/native entry flow

The web self-service route `POST /account/delete` and the admin account-erasure route both call `begin_account_erasure`. The native `POST /api/mobile/v1/account/delete` adapter invokes the same guarded `delete_own_account` handler; it does not maintain a second deletion implementation.

## Data-scope decision

| Data | Account-erasure treatment | Reason |
|---|---|---|
| `GuestAnalysis` | Delete rows owned by the erased account | Ephemeral, non-patient-linked analysis |
| `GuestImageAsset` | Delete rows and queue generated object keys | Private guest uploads must not remain after account erasure |
| Guest `WorkJob` | Delete job rows | Prevent a guest worker from publishing after erasure |
| Other account `WorkJob` rows | Cancel queued/running work; clear `payload_json`; clear only allowlisted result references | Stop provider work and remove transient prompt/transcript payloads |
| Private AI result objects | Queue through existing `WorkGarbage`; collector rechecks live references | A result still referenced by a patient analysis is retained |
| `Patient`, `Analysis`, `ImageAsset`, `PatientMedia`, `Treatment`, tooth status and patient voice/clinical history | Preserve; do not blanket-delete | These can be third-party patient records with independent care, dispute and legal-retention duties |
| `AgreementAcceptance` and security/audit evidence | Preserve under the existing retention policy | Evidence of consent, account action and security events |

This is a deliberate separation between erasing the clinician's account/temporary guest workspace and deleting third-party patient records. It is not a legal opinion or a declaration that every retained record has a finalized retention period. A documented legal basis, retention schedule and patient-rights workflow are still required.

## Implementation

1. `erase_account_ai_data` removes the account's guest analyses and image rows in the same database transaction as account erasure.
2. It deletes guest work jobs and cancels queued/running work for the account. Other work-job receipts remain but their transient payload JSON is cleared.
3. Guest upload keys are accepted only when they match the server-generated `uploads/guest_analysis_<id>_<32-hex>.(jpg|jpeg|png|webp)` layout. AI result references must remain under the relative `uploads/ai_results/` prefix and cannot contain traversal or backslash segments.
4. The existing `WorkGarbage` table and `work_worker.collect_garbage` loop perform remote deletion. No new table or migration was introduced.
5. The collector checks `GuestImageAsset.file_path` and live `Analysis/GuestAnalysis.result_path` references before deleting. A still-referenced patient result is preserved.
6. Re-queuing advances the receipt attempt generation. The collector's conditional delete prevents an older in-flight collection attempt from dropping a receipt that account erasure has re-armed.
7. The guest upload finalization path takes a PostgreSQL row lock on the same `User` row that account erasure locks. If the account was erased while files were being written, the upload transaction rolls back and queues the now-orphaned generated image keys in a separate transaction.

## Regression coverage added

- Erasure removes only the target account's guest rows and guest work jobs.
- Other users' guest rows/jobs remain untouched.
- Patient-linked patient, analysis, analysis-image and archive-media rows remain.
- Queued/running patient work is cancelled and transient payload JSON is cleared.
- Patient result references are queued but preserved by the collector while the analysis row still references them.
- Guest image and result objects are removed after their metadata rows are gone.
- Path allowlists reject traversal, absolute paths, backslashes, uppercase UUIDs and unsupported extensions.
- Guest upload finalization and account erasure share a PostgreSQL row-lock boundary.
- Existing patient-media cleanup tests now verify that re-queuing increments the collector fence generation.

## Remaining acceptance gates

- Run `tests/test_account_erasure_cleanup.py`, `tests/test_patient_media_cleanup.py` and `tests/test_account_actions.py` against the real SQLite/FastAPI test harness and PostgreSQL CI service.
- Confirm the fresh branch-scoped Android and Security Recovery workflows receive hosted runners. The previous jobs had `runner_id=0`, empty `runner_name`, zero steps and missing log blobs; that is a pre-step runner-allocation failure, not a demonstrated TypeScript/pytest failure.
- Profile photos, membership documents and expert credential documents still use the coordinator's existing best-effort storage cleanup path; they are not yet covered by the new durable guest-object queue. Pending expert-title-change documents also need an explicit erasure-scope review.
- Audit legacy orphan `GuestImageAsset` rows without a parent `GuestAnalysis`; the asset table has no owner column, so ownership cannot be safely inferred from the asset row alone.
- Obtain a documented retention decision before changing patient-linked clinical records or media.

No production database, object store, deployment, APK publication or `main` merge was performed.
