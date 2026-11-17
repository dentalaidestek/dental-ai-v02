# Clinical media delete and encrypted-draft recovery — 2026-11-17

## Web-first comparison

Re-read the web patient gallery in `app/templates/patient_detail.html`, its preview/delete controls, and the owner-scoped handlers in `app/main.py`. The web gallery posts a delete form and then redirects back to the patient page. Native uses authenticated `DELETE /api/mobile/v1/patients/{patient_id}/media/{media_id}` and keeps the gallery open.

That difference exposed a native-only failure mode: the database delete can commit, the response can be lost, and a retry previously returned 404 because the row was already gone. The native component treated the outcome as uncertain and permanently disabled destructive actions for that mounted gallery.

## Changes

- The mobile delete route now verifies patient ownership first, then returns an idempotent `already_deleted: true` success when the same owner-scoped media row is already absent. A media row that exists under another patient or owner still returns 404. Storage deletion is not repeated for an already-removed row. The replay reports `storage_cleanup_pending: null`, not `false`: after the row is gone the endpoint cannot infer whether an earlier object-store cleanup failed, so it does not claim that orphan cleanup completed.
- The native gallery retains the exact uncertain delete target (one media ID or delete-all) and exposes **Silme durumunu güvenle doğrula**. It replays only the previously confirmed action; the server's idempotent response reconciles a lost delete response. A successful replay clears the uncertainty state and refreshes the gallery.
- Found a second crash window in explicit draft clearing: encrypted vault files were deleted before the SecureStore intent. If the process died or SecureStore failed between those operations, the durable intent could point to missing encrypted files. Added `clearClinicalMediaDraft`: remove the durable intent first, then best-effort scoped orphan cleanup. If cleanup fails, the existing next-visit reconciliation removes the orphan; if intent deletion fails, encrypted files remain intact.
- No new database columns, migration, provider, or storage service were added.

## Regression coverage

- Backend: first delete, same-request replay after the row is gone, no duplicate object deletion, cross-patient media rejection, and cross-owner 404.
- Native: a simulated response loss after the first delete, then a second same-target request returning `already_deleted`; the recovery action disappears after success.
- Draft lifecycle: cleanup occurs only after the durable intent is deleted; intent failure preserves encrypted files; orphan cleanup failure does not restore a cleared intent.
- Registered the new draft lifecycle test in `npm run test:beta`.

The Node/pytest test sources were added but have not been executed in this connector-only run. GitHub Actions at the starting PR head failed before runner steps; see the run IDs in the PR continuation comment. Do not interpret those pre-step failures as source-test failures or passes.

## Remaining acceptance

- Run `npm ci`, `npm run typecheck`, the beta Node suite, and the focused Python patient-media parity test when a runner is available.
- Verify delete response loss and app termination on physical Android/iOS devices.
- Storage cleanup failures after a committed database delete are logged as pending cleanup; a durable object-cleanup worker remains a separate operational follow-up.
- Existing archived originals may still carry metadata until separately reviewed; no bulk rewrite was performed.

No main merge, production deploy, migration, APK/IPA publication, or patient-record mutation was performed.
