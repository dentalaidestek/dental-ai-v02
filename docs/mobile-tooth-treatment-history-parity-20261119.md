# Mobile tooth-chart treatment-history parity — 2026-11-19

## Web flow inspected first

- `app/templates/tooth_chart.html` opens the selected FDI tooth, provides the treatment-history tab, and calls `GET /patients/{patient_id}/teeth/{tooth_number}/history`.
- `app/main.py` checks the patient owner (or ADMIN on the web route) and returns that tooth's surface observations, completed treatments, and analyses.
- The web treatment-history response is currently unbounded.

## Gap found in the native flow

The mobile patient-detail API deliberately returns only the three newest patient treatments plus a continuation cursor. That is appropriate for the profile's lightweight initial response. `NativeToothChart` previously filtered only that three-row response for the selected tooth, so older treatments for a tooth could disappear even though the web history showed them. `NativePatientHistory` is the paged analysis-history view; it does not fill in the missing treatment rows.

## Change

Added `GET /api/mobile/v1/patients/{patient_id}/teeth/{tooth_number}/treatments`:

- verifies patient ownership and valid FDI tooth number;
- returns at most 20 treatment records per page;
- sets private/no-store response headers;
- binds continuation cursors to user, patient, and tooth;
- freezes the first page's maximum treatment ID so records inserted later do not shift the active pagination snapshot;
- keeps the existing patient-wide treatment endpoint and its cursor contract unchanged.

The native API rejects malformed pages, duplicate IDs, cross-tooth records, invalid revisions, and cyclic/truncated cursors. The tooth chart now loads this page only when the clinician opens that tooth's treatment-history tab, offers older pages on demand, retries failed reads, refreshes after a successful treatment mutation, and discards late responses after switching teeth or accounts.

## Regression coverage added

- `tests/test_mobile_patient_parity.py`: 20+5 pagination, concurrent insert snapshot isolation, cross-tooth and cross-patient cursor rejection, owner denial, invalid FDI.
- `mobile/tests/patientApi.cjs`: endpoint path, credentials omission, cursor and response validation, cross-tooth response rejection.
- `mobile/tests/toothChartLifecycle.cjs`: page append and late-response isolation after switching FDI teeth.

These tests are registered in the existing `test:beta` and security-recovery workflows through their current test files; no new workflow or CI trigger was added.

## Verification boundary

At the starting head, the latest Android run inspected was `44273348890` (2026-11-18). Its `apk` job had `runner_id=0`, empty `runner_name`, and `steps=[]`; its log endpoint returned `BlobNotFound 404`. The current branch workflows `mobile-android.yml` and `security-recovery.yml` are manual-only while hosted runners are investigated. No workflow was dispatched in this change, so no full TypeScript, Android build, Python security suite, or device test is claimed.

Run locally after pulling this branch:

```bash
cd mobile
npm test
```

Run the backend regression from the repository root:

```bash
python -m pytest tests/test_mobile_patient_parity.py -q
```

No migration is introduced. The treatment model already has patient/created/id and tooth-number indexes; a dedicated patient+tooth+created index should be considered only after measuring a representative PostgreSQL query plan. This change is bounded to 20 rows per request but is not a 60,000-user load-test result.

No main merge, production deploy, migration, or clinical-record mutation was performed.
