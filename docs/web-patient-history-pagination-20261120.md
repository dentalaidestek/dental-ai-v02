# Web patient history paging — 20 November 2026

## Web flow inspected first

Re-read the live branch versions of `app/templates/patient_detail.html` and `app/main.py::patient_detail`, plus the current mobile patient-history API and native history screen.

The web profile previously loaded every `Analysis` and `Treatment` for the patient, then loaded every `ImageAsset` and every matching completed voice-review `WorkJob` for the full analysis history. The native history screen already used bounded cursor pages. The treatment UI showed the first three rows and expanded the remaining rows in place.

## Change

- Added `app/patient_history_pagination.py`: strict, bounded base64url cursor containing the exact `(created_at, id)` boundary; invalid/oversized cursors are rejected.
- The initial web profile now reads at most 20 analyses plus one look-ahead row and at most 20 treatments plus one look-ahead row. Sorting is deterministic by `created_at DESC, id DESC`.
- `ImageAsset` and completed voice-review `WorkJob` queries now run only for the 20 visible analyses.
- Added cookie-session routes:
  - `GET /patients/{patient_id}/history/analyses/page`
  - `GET /patients/{patient_id}/history/treatments/page`
- Both routes re-check the selected patient in the same database session, preserve the web admin-selected-patient rule, repeat owner predicates for non-admin queries, and return `private, no-store`, `Vary: Cookie`, `Pragma: no-cache`, and `nosniff`.
- The routes return autoescaped server-rendered Jinja partials. Analysis detail modals, image/radiograph groups, result links, and completed voice-review labels remain identical to the first page.
- Treatment rows retain the first-three collapsed view. Expanding before or after loading another page keeps the user's state; appended rows are hidden when collapsed and visible when expanded.
- No bearer-token mobile API is reused for the web session. No schema, migration, clinical write path, provider call, or storage behavior changed.

## Regression coverage

- `tests/test_patient_history_pagination.py`: cursor validation, equal-timestamp ID tie-break, bounded initial profile, 25-row continuation, a newer concurrent insert not shifting the current cursor walk, voice-review DONE vs RUNNING labeling, analysis assets, collapsed/expanded treatment pages, private headers, invalid cursor and another-account denial.
- `mobile/tests/patientHistoryWebPaging.cjs`: source-contract guards for bounded queries, owner-scoped cookie routes, private headers, partial contents, treatment collapse state, and same-origin page loading.
- The Node regression is registered in `npm run test:beta` and the manual Security Recovery native-clinical job. The Python integration test is registered in the manual Security Recovery pytest command.

## Validation and limits

- GitHub read-back source-contract checks: **15/15 passed**.
- Isolated cursor helper behavior checks: **8/8 passed** (round-trip, timezone normalization, malformed/oversized cursor, look-ahead boundary and invalid page size).
- Jinja parser checks for both partial structures: **2/2 passed**.
- The committed FastAPI/SQLModel integration test and Node test runner were not executed against a repository checkout in this runtime. SQLModel and the app's locked dependencies are not installed here.
- Full Expo typecheck, `npm test`, Android Gradle/device build, full Python security suite, browser interaction, PostgreSQL query-plan and 60,000-account load tests remain unverified.
- The analysis table currently has a patient index but no verified composite `(patient_id, created_at, id)` index in this code path. No production migration was introduced; query-plan evidence should determine whether an additive index is needed later.

## CI and deployment boundary

Both `.github/workflows/mobile-android.yml` and `.github/workflows/security-recovery.yml` are explicitly `workflow_dispatch`-only while hosted runner jobs have been failing before their first step. The Security Recovery workflow now includes the new patient-history regressions, but no run was dispatched in this work. This is a runner/CI execution limitation, not a source-test pass or source-test failure.

No main merge, production deploy, migration, APK/IPA publication, or patient-record mutation.
