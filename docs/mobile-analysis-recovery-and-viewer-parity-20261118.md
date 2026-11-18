# Mobile analysis recovery and viewer parity — 2026-11-18

## Web flow reviewed first

Reviewed the authenticated web analysis composer in `app/templates/analysis_new.html`, the patient gallery selection in `app/templates/patient_detail.html`, the `/analysis/new/{patient_id}` GET/POST handlers in `app/main.py`, the canonical embedded viewer wrapper in `app/templates/analysis_viewer.html`, and the radiograph/intraoral viewer templates and scripts under `vision_service/templates/`.

The native path is `NativePatientMedia → NativeAnalysisUpload → NativeDentalAI → NativeClinicalReview → NativeVisionViewer`. Existing upload receipts, four-image limit, private image assets, source revision, user-approved final review, and no-auto-write-to-tooth-chart rules were retained.

## Changes in this batch

- `NativeClinicalReview`: separated local secure-draft validation from the initial remote workspace read. A transient API/network failure now leaves the screen ready for an explicit refresh instead of setting the permanent fail-closed storage-corruption latch. Invalid/cross-account local intents still keep the screen blocked.
- `clinicalWorkflow.cjs`: added a regression for first-load 503 followed by successful refresh without remount.
- `visionModel.ts`: matched the web viewer's fallback finding description (label, FDI tooth and surface) when the inference response omits explanatory text. Descriptions and labels are bounded before rendering; malformed FDI values are not presented as tooth identifiers.
- `NativeVisionViewer`: selecting a finding scrolls the native viewer back to the image so the corresponding overlay is actually visible, matching the web viewer's image/finding interaction.
- `visionViewer.cjs`: added regressions for fallback descriptions, unlocalized findings, bounded descriptions, and image focus on selection.

## Verification and limitations

The tests are included in the existing `npm run test:beta` script. They were not executed in this connector-only run because no repository checkout/runtime is available here.

Starting branch head was `05648af5c3dc7bd680ece99b5f6edd1f2341a05c`. Its latest Android and Security Recovery workflow jobs completed with failure but exposed null step lists. Job-log downloads returned `BlobNotFound 404`; TypeScript, Node, Gradle and pytest did not start. This is not evidence of a source-code test failure and is not a green check. The exact hosted-runner/account/billing cause is not exposed by GitHub's available records.

No provider, prompt, clinical taxonomy, patient authorization, or production configuration was changed. No patient data was accessed or modified. No merge, deployment, migration, or APK/IPA publication was performed.
