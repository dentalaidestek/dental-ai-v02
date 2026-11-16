# Mobile AI analysis parity — 2026-11-16

Branch: `feature/mobile-web-parity-20261110`  
PR: #257 (base remains `feature/mobile-beta-20261110`)  
Issue: #258

## Web flow inspected

- `app/templates/analysis_new.html`: anonymous patient ID, age label, chief complaint, optional FDI/clinical note, saved media plus new files, four-image cap, 15 MiB per new file and 48 MiB total new-file bytes.
- `app/templates/analysis_viewer.html`: asset strip, modality-aware viewer selection, per-asset vision endpoints, retry and clinical-note/manual-finding/treatment-analysis actions.
- `app/templates/result.html`: preliminary/final result sections and clinician-owned decision boundary.

## Native changes

- `NativeAnalysisUpload` receives the already-loaded patient summary and renders the same anonymous ID / age / chief complaint context. It does not request patient data again and does not display name, phone or national ID.
- Patient summary is passed from both `NativeDentalAI` and the patient-profile media composer using already-loaded records.
- Upload UI reports workflow phase and multipart byte progress. The 100% message explicitly distinguishes transfer completion from server receipt confirmation.
- Cancellation still aborts only the active transfer. The durable intent and request key remain available for receipt reconciliation; a second analysis is not created blindly.
- Saved media count remains part of the four-image cap, while the 48 MiB limit is correctly described as applying to new uploaded files only. Saved media IDs are sent as references, not re-uploaded bytes.
- The result summary repeats anonymous patient ID, age and complaint from the returned analysis patient object.
- Native vision viewer now has a modality-labelled asset strip matching the web viewer, using the already-authorized asset list returned by the clinical workspace; switching assets does not fetch another patient or asset list.
- Pending vision-result polling uses bounded exponential backoff (10s, 20s, then at most 30s) and pauses while busy, unfocused or backgrounded.

## Regression coverage added

- Patient identity/age/complaint display, including age zero and missing-value fallbacks; no patient name disclosure.
- Multipart byte-progress callback reports loaded and total bytes.
- Cancelled transfer keeps the durable upload intent and exposes same-key retry/reconciliation.
- Pending vision polling backs off and does not overlap requests.
- Viewer asset switching and modality labels.

The tests are registered in the existing `test:beta` and viewer test files. They are committed but were not executed in this run because GitHub Actions jobs failed before runner assignment; no test pass is claimed.

## CI evidence

At HEAD `ffb422ca101b5419296961745a65cc3a15ed059e`, GitHub Actions runs fail in 2–3 seconds with empty `steps`, `runner_id: 0`, empty `runner_name`, and no downloadable job log (`BlobNotFound`). The Android typecheck/APK and regression commands therefore did not start. This is runner provisioning/assignment evidence, not a TypeScript or test assertion failure. The exact account/billing/hosted-runner cause is not exposed by these records.

No main merge, production deploy, database migration, or APK/IPA publication was performed.
