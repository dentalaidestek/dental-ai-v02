# Native patient history — stable cursor and treatment presentation

Date: 2026-11-20  
Branch: `feature/mobile-web-parity-20261110` · PR #257 · Issue #258

## Web-first review

Before editing, the current branch's web flow was re-read:

- `app/templates/patient_detail.html`: patient history section order, first-three treatment collapse, "Diğer tedavileri göster", "Daha fazla tedavi yükle", and status text.
- `app/templates/patient_treatment_history_items.html`: treatment name, FDI tooth, date, material, result and doctor note.
- `app/patient_history_web.py` and `app/patient_history_pagination.py`: authenticated cookie route, patient-owner recheck, bounded page size 20, descending `(created_at, id)` cursor.
- `app/mobile_analysis_api.py`: patient-scoped analysis history supports `stable_order=true` and opaque `before_cursor`, while retaining the old numeric `before` contract.
- `mobile/src/NativePatientHistory.tsx`, `modernApi.ts`, `NativePatientProfile.tsx` and the existing treatment mutation receipt flow.

## New gaps found

1. The web analysis history uses `created_at DESC, id DESC`; native still called the legacy numeric-ID endpoint. Backfilled/imported analyses can therefore appear in a different order on web and mobile even though the backend already exposes the stable cursor contract.
2. The native treatment history showed all fields but rendered them as divider-only rows rather than the web's grouped history cards.
3. The per-row native "Düzenle" action did not use the same durable mutation gate as the treatment form. During a pending/uncertain receipt it could still open and change the visible target while the encrypted pending intent remained authoritative. The edit is now disabled until the intent, profile and delete gates are clear.

## Changes

### Analysis history

- Added `getPatientAnalysisHistoryPage`, which requests the web-aligned `stable_order=true` cursor and validates patient/FDI scope, duplicate IDs, page bounds, cursor shape and cursor progression.
- Native `NativePatientHistory` now stores the opaque cursor and retries the same continuation cursor without resetting loaded history.
- Kept the existing `getAnalysisHistory` numeric API for older call sites.
- Added a bounded legacy-server fallback: only the first page may fall back when an older server omits the stable cursor field or returns `next_cursor: null` alongside a valid numeric `next_before`; once a stable cursor has been issued, the server must continue it.
- Kept the same patient and tooth filters on every page.

### Treatment history

- Added a presentation helper for FDI tooth, date and material labels.
- Native treatment rows now use bordered cards, grouped metadata chips and separate result/doctor-note panels in the same content order as the web partial.
- Preserved the native edit capability, but it is now disabled while a profile/treatment mutation is busy or uncertain, while the encrypted treatment intent is pending/unreadable, or while the patient-delete gate is unresolved.
- Existing idempotency key, expected revision, snapshot cursor, first-three collapse, retry and patient/account-scope behavior remain unchanged.

## Regression coverage

- `mobile/tests/patientAnalysisHistoryCursor.cjs`: stable cursor request/continuation, patient/FDI isolation, duplicate IDs, malformed/looping cursor rejection, and legacy numeric fallback.
- `mobile/tests/patientHistoryRetry.cjs`: retry the same opaque cursor after a failed continuation without losing first-page rows.
- `mobile/tests/patientAnalysisHistory.cjs`: renderer now stubs the stable page API.
- `mobile/tests/patientTreatmentPresentation.cjs`: treatment metadata labels, all edit-gate blockers, and native card/source contract.
- Both new tests are registered in `npm run test:beta` and the `native-clinical-security` Security Recovery job.

## Validation performed in this run

- Exact stable-cursor helper copied from the current branch was checked with TypeScript strict compilation in an isolated harness.
- Isolated Node cursor harness: 7 assertions passed (stable first/next page, patient scope rejection, legacy fallback).
- Exact treatment presentation helper was checked with TypeScript strict compilation in an isolated harness.
- Isolated Node treatment helper: 13 assertions passed.
- GitHub read-back confirmed the new client API, native call site, test files and both test registrations on the branch.

These are isolated helper checks, not execution of the committed repository test files. The full `npm test`, Expo project typecheck, Android Gradle/APK and device tests were not run because this runtime has no repository checkout or installed project dependencies.

## CI and unresolved test evidence

A concurrent manual backend adjustment in `app/mobile_analysis_api.py` was detected after the initial branch read and preserved. It keeps the stable cursor route's negative numeric `before` validation explicit; this file was not overwritten by the native changes.

At current HEAD `754d2be90ac0576b3f639b40db5e57e5f580b822`:

- Combined commit statuses: 0.
- PR-triggered workflow runs: 0.
- Android run `43772807470`: typecheck and beta-apk jobs are marked failed, but their job records have `steps: null`; TypeScript and Gradle did not start.
- Security run `43772807464`: security job is marked failed with `steps: null`; pytest did not start.
- Both workflows remain manual-only. No workflow dispatch action is available in this connection; automatic triggers were not re-enabled.

The independent technical audit at this branch reports the last local mobile suite as 931/935 and `tests/test_mobile_patient_parity.py` as 27 pass / 13 fail, with those 13 attributed to patient-history cursor contracts. The actual pytest failure trace is not stored in the audit file and could not be reproduced without the repository test environment. The stable native client mismatch found here is fixed at source level, but the 13 Python integration failures are **not claimed fixed** until the full test output is available and the suite is rerun.

## Safety

No main merge, rebase, production deploy, migration, APK/IPA publication, provider call or production patient-data mutation was performed.


## Same-scope refresh regression — 2026-11-20

A further web/native behavior difference was found after the card and cursor work: the native profile's generic `load()` callback reset `allTreatments` to false on every successful refresh. A `TREATMENT_CREATED` / `TREATMENT_UPDATED` realtime event, pull-to-refresh, or a successful profile refresh therefore collapsed a history the clinician had explicitly expanded. The web page's append flow preserves `data-expanded` while loading later pages.

The native refresh now preserves expansion only when the account, session token and patient scope are unchanged. A scope change still collapses the previous patient's history; the existing effect also clears cursor, page IDs and in-flight page requests on scope change. The first-page refresh still resets the page cursor and dedupe set, so expanded mode can continue from the refreshed first-page boundary without retaining stale appended rows.

Regression coverage: `mobile/tests/patientTreatmentHistoryExpansion.cjs`, registered in `npm run test:beta` and the Security Recovery `native-clinical-security` job. The test covers same-scope refresh, account/session/patient changes, and the component's scope-reset contract.

Validation boundary: source changes and GitHub read-back are confirmed. The committed Node test, full Expo typecheck and Android build were not executed in this runtime; current-head GitHub Actions still has no run/status result. No merge, deploy, migration or patient-data mutation.
