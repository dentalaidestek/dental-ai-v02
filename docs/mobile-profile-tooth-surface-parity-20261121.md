# Mobile patient profile and tooth-surface parity — 2026-11-21

## Web flows reviewed first

- `app/templates/patient_detail.html`: patient identity, age and anonymous number, quick actions, collapsed patient-information form, seven editable fields, destructive delete guard, clinical-media and history placement.
- `app/templates/tooth_chart.html`: FDI tooth selection, preview tooth, five surface pins, anatomical anterior/posterior mapping, status controls and `setSurface(v)` selection semantics.
- Native counterparts: `NativePatientProfile.tsx`, `patientProfilePresentation.ts`, `api.ts`, `NativeToothChart.tsx`, `toothSurfaceOptions.ts`.

## Findings fixed

1. Native patient detail allowed `edit_revision` to be absent at the API type boundary. The screen could therefore send a PUT without `expected_revision`; the server deliberately treats that field as optional for compatibility, which would turn a missing revision into a blind update. Native profile editing now fails closed, displays a refresh action and never sends the update without a 64-character server revision. The API wrapper also requires the revision and validates the returned patient ID and new revision receipt.
2. After a 409 revision conflict, the save control remained enabled. Repeated taps could resend the same known-stale revision until the clinician manually merged. The save action is now disabled and guarded until the three-way merge refreshes the current server snapshot.
3. Native surface chips and preview pins toggled an active surface off, while web `setSurface(v)` always selects the tapped surface. Switching from the independent surface editor could also leave its old visual highlight ahead of the pin selection. A shared FDI-aware selection helper now maps the fixed web occlusal pin to incisal on anterior teeth, keeps one explicit selection, clears the independent editor when entering general tooth editing, and makes the preview reflect the active independent editor when that mode is open.

## Regression coverage added

- Missing/malformed patient edit revision is rejected before network mutation.
- A 409 cannot be resubmitted before the three-way merge.
- Edit API success receipts must contain the expected patient ID and a valid new revision.
- Web/native anterior and posterior pin mapping, invalid FDI handling and single-selection semantics.
- Native chart source contract ensures pin/chip selection clears stale editor state.

The existing `test:beta` command already includes `patientProfileUI.cjs`, `patientApi.cjs` and `webToothSurfaceParity.cjs`; no new test runner wiring is required.

## Safety and remaining acceptance

No patient record, production database, migration, provider prompt, clinical taxonomy, main branch, deployment or store release was changed. The branch remains a draft PR. New GitHub Actions results and Android device screenshots/touch tests are required before calling the UI accepted. This change does not claim 60,000-user capacity; load testing remains a separate staging gate.
