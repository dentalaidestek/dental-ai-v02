# Native tooth-chart treatment mutation parity — 2026-11-16

## Web flow reviewed first

Reviewed the canonical web tooth-chart page in `app/templates/tooth_chart.html`, its lazy treatment-history request (`/patients/{patient_id}/teeth/{tooth_number}/history`), the existing mobile patient-detail payload in `app/mobile_api.py`, and the native chart in `mobile/src/NativeToothChart.tsx`. The web page keeps tooth selection, FDI identity, surface/status editing and treatment history separate; the native screen also exposes treatment create/update from its tooth-history tab.

## Reproduced source-level defect

The shared mobile API deliberately requires:
- `createTreatment(token, patientId, payload, requestKey)`
- `updateTreatment(token, patientId, treatmentId, payload, requestKey, expectedRevision)`

`NativePatientProfile` already persists a validated mutation intent in SecureStore before sending the request, then reuses the same key after an uncertain response. `NativeToothChart` bypassed that contract and called create with three arguments and update with four. Those call sites do not satisfy the current TypeScript signatures (TS2554-style argument-count errors); at runtime, the shared validator also rejects a missing request key. The update form additionally discarded the treatment's `edit_revision`.

This is a concrete source-level Android typecheck defect discovered even though the latest GitHub jobs had not reached the compiler.

## Changes on the PR branch

- `mobile/App.tsx` passes the authenticated `userId` into `NativeToothChart`.
- `NativeToothChart` uses the same `dai.treatment.{userId}.{patientId}` SecureStore scope and `chunkedDraftStore` as the patient profile. The intent is account- and patient-bound and parsed with `parseTreatmentMutationIntent` before use.
- A new intent is durably stored before any treatment mutation request. Create sends its stable request key; update sends both the stable request key and the selected record's 64-character `edit_revision`.
- An uncertain response keeps the exact intent and exposes an explicit **Bekleyen Tedaviyi Doğrula** action. Reopening the screen restores each treatment field individually and reuses the same key; it does not silently create a second treatment.
- A missing/invalid treatment revision blocks update before network access. Definitive 400/422 validation rejection clears the rejected intent while preserving editable fields; stale-revision 409 clears the obsolete edit and reloads current history; 403/404 clears the stale form.
- Patient/account scope is included in the screen's request-generation checks so a late response from a previous account cannot update the current chart.

No new endpoint, provider call, database table, polling loop or clinical-data log was added. The existing owner-scoped mobile treatment endpoints and durable server receipts remain authoritative.

## Regression coverage added

Five cases were added to `mobile/tests/toothChartLifecycle.cjs`:
1. Store the create intent before the request and reuse the exact request key after remount.
2. Send the selected treatment's edit revision with the update request.
3. Clear a definitive 422 intent and allow a corrected retry with a new key.
4. Refuse to update a legacy treatment that has no valid server revision.
5. Do not read or delete another authenticated user's pending treatment draft.

The file is already included in `mobile/package.json` under `test:beta`.

## Verification boundary

The code and tests are committed to `feature/mobile-web-parity-20261110`; starting HEAD `91abd3d`, the branch advanced by 11 commits to `d3c6c5c`. They have **not** been reported green. Current-head Android PR #2335 (`43811247198`), Android push #2334 (`43811241117`), Android test APK #285 (`43811241121`), Security recovery #974 (`43811247103`), Admin security #858 (`43811247100`) and Expert social #854 (`43811247129`) all failed before steps. The raw job records show `runner_id=0`, empty runner name/group, `labels=[ubuntu-latest]`, `steps=[]`, and 2–3 second completion. All eight job-log downloads returned `BlobNotFound 404`. Consequently no `npm ci`, `tsc`, Node regression suite, pytest, Gradle build or device test ran. This confirms that GitHub did not assign a runner; the exact account/billing/hosted-runner entitlement cause remains outside the available repository records and needs repository-owner inspection.

No main merge, live deployment, APK/IPA publication or real patient-record mutation was performed.
