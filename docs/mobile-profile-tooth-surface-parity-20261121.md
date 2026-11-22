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


## 2026-11-21 follow-up — server-side anatomical FDI surface validation

### Web-first trace

Re-read `app/templates/tooth_chart.html` and `static/tooth-chart/surface-options.js`, then traced the web POST handler in `app/main.py`, the native single-surface and multi-surface handlers in `app/mobile_api.py`, and the shared observation upsert module.

The browser and native selectors already exposed the correct five surfaces per tooth, but both backend write boundaries only checked whether a surface name belonged to the six-value enum. A direct or stale client could therefore persist OCCLUSAL on an anterior tooth or INCISAL on a posterior tooth. The UI was correct; the server-side clinical data contract was incomplete.

### Fix

- Added one shared FDI validator and anatomical surface applicability contract in `app/tooth_surface_status.py`.
- Permanent and primary FDI teeth 1–3 in each quadrant accept INCISAL; units 4–8 (permanent) and 4–5 (primary) accept OCCLUSAL. MESIAL, DISTAL, BUCCAL and LINGUAL remain available for both.
- The web form handler now rejects an impossible surface before opening the write transaction.
- Native single-surface and whole-tooth multi-surface endpoints apply the same shared rule before querying or mutating records.
- The existing mobile FDI helper now delegates to the shared validator instead of maintaining a second implementation.
- No migration or destructive cleanup was added; existing legacy observations are not rewritten.

### Regression coverage

`tests/test_tooth_surface_status.py` now exhaustively checks all 52 valid permanent/primary FDI identifiers, invalid identifiers, anterior/posterior applicability, web rejection, native single-surface rejection, native multi-surface rejection, and valid INCISAL/OCCLUSAL writes. It verifies that only the two anatomically valid synthetic observations reach the database.

The new tests are included in the existing Security Recovery pytest command through `tests/test_tooth_surface_status.py`. They are committed but await the current-head GitHub Actions result. No real patient records were used.
## 2026-11-22 follow-up — web/native tooth preview orientation and surface accessibility

### Web-first trace
Re-read the web patient-detail quick action and the full tooth_chart.html selection path (renderSurfaceOptions, selectTooth, setSurface). Compared the web preview with NativeToothVisual and toothVisualModel for permanent and primary FDI teeth.

### Findings and changes
1. The native preview rotates lower-jaw teeth using the FDI quadrant. The web chart rotated the lower-jaw tooth inside the chart rows, but selectTooth() copied only the tooth markup into the separate preview panel. The preview lost its lower-jaw context and therefore displayed quadrants 3/4/7/8 in the upper-jaw orientation. The shared browser FDI helper now exposes a validated lower-jaw classifier; the selected web preview preserves the 180-degree enamel-atlas and SVG orientation, matching native.
2. The web preview's M/D/L/B pins were labelled only by single letters for assistive technology, while native buttons announce the complete surface. All five web pins now have descriptive accessible labels; the top pin updates between occlusal and incisal with the selected tooth.
3. Web surface chips and pins exposed visual selected/active classes but not aria-pressed. They now publish explicit single-selection state; clearing the surface resets every pin/chip to false.

### Regression coverage
- All 52 valid permanent/primary FDI teeth compare the web lower-jaw classifier against native toothVisualModel().lower; invalid FDI values remain false.
- The web selected-preview class and CSS rotation are asserted alongside native wrapper rotation.
- All five surface pins must carry descriptive labels; the dynamic incisal/occlusal label is checked.
- Surface chips and pins must expose matching aria-pressed state.
- The test remains in the existing npm run test:beta list (webToothSurfaceParity.cjs); no runner contract was removed.

### CI root cause at starting head
At starting HEAD 1449bb4509e970b6a07c6c456e73d5649c3c876b, Android run #4692 completed successfully (TypeScript, session/auth, realtime/pagination, 985 beta regressions, Hermes exports and internal APK build). Security run #2391 executed 604 Python tests with one failure. The failure was an internally inconsistent test regex in test_startup_rejects_wrong_approved_anamnesis_index_columns: it expected the word exact before the stable phrase approved anamnesis query index, while the actual startup message deliberately preserves that phrase and appends the exact column contract. The assertion now matches the stable phrase and separately asserts exact owner/patient/field/source columns; the stored-row preservation assertion remains.

### Validation boundary
The above code and regressions are committed on the feature branch. Their new-head CI has not yet been observed, so no pass is claimed for the updated lower-preview/accessibility tests or the corrected Python assertion. No patient data, schema, migration, clinical API, production database, main branch or deployment was changed.