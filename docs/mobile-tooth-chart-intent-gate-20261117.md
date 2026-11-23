# Native tooth chart intent recovery safety — 17 November 2026

PR #257 / issue #258. Web reference was inspected first from `feature/mobile-beta-20261110`:
- `app/templates/tooth_chart.html`: FDI permanent/primary chart, tooth selection, surface pins, status controls, clinical note, and the separate treatment-history pane.
- `app/main.py`: web tooth-status form validates FDI/status/surface and persists the observation. The web handler also creates a Treatment row for selected non-healthy statuses.
- `mobile/src/NativeToothChart.tsx`, `NativeToothVisual.tsx`, and the native API routes were compared against those flows.

## New gap

The native chart already restores a durable treatment mutation intent from SecureStore and shows a “Bekleyen Tedaviyi Doğrula” action. It disabled tooth selection and panel close while that intent was pending, but status buttons, surface selection/editing, clinical note input, and the general tooth save action remained interactive. More importantly, the chart was interactive during the first render while SecureStore restoration was still pending. A clinician could therefore issue another tooth/surface write before the app knew whether a prior treatment create/update had reached the server.

## Changes

1. Added `toothChartClinicalMutationBlocked`: tooth/surface writes stay locked until treatment-intent restore completes successfully and no corrupt, uncertain, or pending intent remains.
2. Added handler-level guards to both tooth status/note save and independent surface save.
3. Disabled tooth selection, dentition switching, status controls, surface pins, surface selectors, notes, surface editor, and save controls while the gate is closed.
4. Disabled new treatment form editing while restore is pending/blocked; the existing exact-key “Bekleyen Tedaviyi Doğrula” action remains available for a valid pending intent.
5. Added a visible restoring/corrupt-intent message rather than leaving the screen looking interactive.
6. Added patient-ID checks to chart load, realtime/AppState refresh, post-write refresh, and treatment conflict refresh before accepting a PatientDetail response.

The native backend intentionally treats tooth status as an observation, not proof that a procedure was completed; treatment rows are created separately through the idempotent treatment API. This differs from the legacy web form's automatic Treatment row creation for non-healthy statuses, but avoids falsely documenting caries/implant/extraction status as a completed procedure. The native screen already explains this distinction; no automatic treatment insertion was added.

## Regression coverage

- Added pure gate tests for not-ready, blocked, uncertain and pending states.
- Added a deferred SecureStore restore test proving the chart remains read-only until the lookup completes.
- Extended the pending-treatment renderer test to assert tooth status, surface pin, clinical note and save controls remain disabled.
- Added a wrong-patient response regression and a Python security source invariant in the existing mobile patient parity workflow.

## Validation and limitations

- The pure helper was checked using Node 22 and the globally installed TypeScript transpiler.
- New test snippets were syntax-checked with `node --check`; the Python regression snippet passed AST parsing.
- Full `toothChartLifecycle.cjs`, React renderer, project TypeScript 5.9.2, backend pytest, Expo export and APK build were not run because the local runtime lacks the mobile dependency set and GitHub Actions jobs never reached a step.
- Latest CI still has `steps=[]` and typecheck/security logs return Azure `BlobNotFound 404`; no compiler, Gradle or pytest process started.

No patient record was changed. No main merge, live deploy, APK/IPA publication or clinical-data mutation.

Final implementation review: the Notes tab, independent treatment-history edit button, treatment name/material/date/note/result fields, and every tooth/surface editor control are now disabled under the same gate; treatment form values remain controlled while disabled. The handler-level gate also protects direct invocation. Patient-ID equality is checked on both initial and refresh reads and on all four post-write/conflict refresh paths. The modified TSX control fragments transpiled successfully with the global TypeScript compiler.
