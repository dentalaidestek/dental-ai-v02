# Native tooth chart parity — 2026-11-17

## Web flow inspected first

The reference is `app/templates/tooth_chart.html` on `feature/mobile-web-parity-20261110`.

The actual web flow:
- Renders permanent FDI teeth and switches to primary FDI teeth in-place.
- Selects the latest eligible analysis tooth when the page opens; primary FDI numbers switch the chart to the primary dentition.
- Opens a tooth detail sheet with status, surfaces, clinical note, treatment history and a separate notes tab.
- Loads the history lazily when the history tab is opened. The web response contains surface statuses, treatment records and analysis history.
- Escapes values before rendering history content and ignores a delayed history response if the clinician has selected another tooth.

The native implementation was inspected in `NativeToothChart.tsx`, `NativeToothVisual.tsx`, `api.ts`, and `NativePatientHistory.tsx`.

## New parity gaps found

1. Permanent native teeth used the shared enamel atlas, but primary native teeth used three hand-authored SVG strings. Those strings declared gradient IDs such as `primary-incisor-enamel` while their paths referenced the non-existent `primary-enamel` ID. In addition to the broken paint reference, this meant the primary tooth silhouette was not the same visual source as the web chart.
2. The native history tab showed analysis history and treatment rows, but did not show the selected tooth's surface status records. The web lazy-history response includes those records and their update timestamps.

## Changes

- Native permanent and primary teeth now use the same bundled four-column enamel atlas and FDI-to-column mapping as the web chart. Implant artwork and status overlays remain native and local; no network image or AI call was added.
- The mobile `PatientDetail.surfaces` type now includes optional `updated_at`, and `getPatient` rejects a non-string timestamp instead of silently accepting a malformed contract.
- The native tooth history tab now displays the selected tooth's surface, status, note and update timestamp before the analysis history and separate treatment records. It uses the web history labels (including Bukkal / Vestibül, Lingual / Palatinal and Kanal Tedavisi) and the same day/month/year + hour/minute timestamp precision.
- Added FDI atlas mapping tests, an end-to-end native component regression for surface history, and a backend contract test for owner-scoped surface timestamps.

## Verification and limitations

- Added `mobile/tests/toothVisual.cjs` to `npm run test:beta`.
- Added a component regression to `mobile/tests/toothChartLifecycle.cjs`.
- Added an API contract regression to `tests/test_mobile_patient_parity.py`.
- These tests are committed but were not executed in this run because the current GitHub Actions jobs fail before any runner step is recorded. This document does not claim a TypeScript, Node, pytest, APK or device-test pass.
- No schema migration was needed: the mobile patient detail endpoint already returns `ToothSurfaceStatus.updated_at`.
- No main merge, production deploy, patient-record mutation, or APK/IPA publication was performed.
