# Native tooth-chart history render-key privacy — 21 November 2026

## Web-first flow inspected

Re-read the canonical web chart before changing native code:

- `app/templates/tooth_chart.html`: permanent/primary dentition toggle, FDI tooth selection, tooth/surface status form, revision fields, note editor and lazy history tab.
- `app/main.py`: owner-scoped tooth chart, FDI/anatomical-surface validation, optimistic tooth/surface revisions and tooth history route.
- `app/mobile_api.py`: corresponding owner-scoped JSON mutations, anatomical-surface checks, revision checks, realtime events and cursor-paged tooth treatment history.
- Native comparison: `mobile/src/NativeToothChart.tsx`, `mobile/src/NativePatientHistory.tsx` and `mobile/src/toothSurfaceOptions.ts`.

The native chart retains the web FDI layout, permanent/primary switch, latest-analysis focus, per-tooth and per-surface state, notes, independent surface editor, analysis history and paged treatment records. No clinical behavior or data contract was changed in this work.

## Defect

The selected-tooth analysis-history child used `key={token + patientId + selectedTooth}`. The key correctly forced a remount when the session, patient or selected tooth changed, but it unnecessarily embedded the raw bearer token in React renderer identity.

This was a second native render-key privacy leak, separate from the patient-profile leak fixed in `NativePatientProfile`. It did not send the token over the network, but renderer/debug surfaces do not need the credential.

## Change

- Added the existing process-local opaque `nextSessionRenderKey()` helper to the tooth chart.
- Allocated a stable key for the current `userId + token + patientId + selectedTooth` scope; it rotates only when that scope changes, preserving the original history remount boundary.
- Replaced the raw-token JSX key with `historyRenderKey`; the token-bearing scope remains only an internal comparison value.
- Added an AST regression that locates the `NativePatientHistory` JSX node and requires the opaque key while checking that account/session/patient/tooth changes still rotate the scope identity.
- Updated the tooth-chart React test harness to resolve the existing helper so the current lifecycle suite continues to exercise the real component module.

No API, backend authorization, storage, database, image, clinical note, treatment, provider or patient record was changed.

## Validation limits

The immediately preceding parent-head CI was green (Android typecheck, session/realtime/beta regressions, Android internal APK, and all Security Recovery jobs). The profile and tooth-chart render-key changes are newer than that green head. Latest-head workflows must complete before these new regressions are called passed. The new tests are registered in `npm run test:beta`; the tooth-chart lifecycle suite is already part of that script. No local checkout was available for independent execution in this run.

No main merge, production deployment, store publication, migration or patient-data operation was performed.
