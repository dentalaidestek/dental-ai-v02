# Mobile AI analysis parity and privacy — 2026-11-17

Branch: `feature/mobile-web-parity-20261110`  
PR: #257 (base: `feature/mobile-beta-20261110`)  
Issue: #258

## Web-first review

Inspected the branch's current web flow before changing native behavior:

- `app/templates/analysis_new.html`: anonymous patient context, FDI and clinical notes, saved media plus new files, four-image total, 15 MiB per new file and 48 MiB batch guard.
- `app/templates/analysis_viewer.html`: modality-only asset strip, canonical radiograph/intraoral embedded viewer, same-origin asset and vision routes, retry and clinician-owned manual-note/treatment actions.
- `app/templates/result.html`: preliminary/final/NEEDS_INFO states and clinician decision boundary.
- `app/mobile_analysis_api.py` and `app/mobile_clinical_api.py`: owner checks, upload receipt, clinical workspace and durable job metadata.
- `NativeAnalysisUpload`, `NativeClinicalReview`, `NativeVisionViewer` and their API adapters.

## New gaps corrected

1. The analysis-detail native parser previously checked only asset IDs. It did not reject extra asset keys such as `file_path`, unsafe original filenames, more than four assets, or unapproved analysis/job fields. The parser now enforces the backend's minimal response contract, safe filename shape, modality token, unique IDs and the four-image cap. Internal job error codes are no longer serialized to the mobile detail response.
2. The clinical viewer's native thumbnail cards displayed original upload filenames, while the web analysis viewer labels the asset strip by modality. The clinical mobile API now returns only asset ID, modality, vision availability and the same-analysis relative URL. Native labels use Turkish modality names (Panoramik, Bitewing, Periapikal, Ağız içi) and do not receive original filenames or storage paths.
3. The mixed saved-plus-new analysis byte-budget rejection used a stale “80 MiB” message even though the shared backend constant and accepted contract are 48 MiB. The response now reports 48 MiB.

## Regression coverage added

Native:
- Reject analysis-level storage references, asset `file_path`, unsafe filenames, over-limit asset lists and internal job error fields.
- Accept only safe PRELIMINARY/FINAL job metadata.
- Accept modality-only clinical assets and reject filename/path fields.
- Render modality labels instead of uploaded filenames.

Python:
- Clinical workspace asset response excludes original filename and storage path.
- Analysis detail job response excludes internal `error_code`.
- Mixed saved/new byte-budget error matches the 48 MiB contract before allocating an Analysis or ImageAsset row.

Tests are committed but require a runner to execute. No test pass is claimed in this report.

## CI evidence at starting HEAD

At `2b9875076decf4e636f7baeacdcba22ec6c5d173`, Android run `44133525110` had typecheck job `134217312303` and APK job `134217311837`; Security run `44133525334` had job `134217338763`. All jobs returned no steps and no log URL; log retrieval returned `BlobNotFound 404`. Workflow definitions use `ubuntu-latest` and contain normal checkout/install/typecheck or pytest steps. The jobs therefore failed before those steps ran; this is not evidence of a TypeScript or pytest source failure. The exact GitHub hosted-runner/account cause is not exposed by the available records.

No main merge, production deploy, migration, APK/IPA publication or clinical record mutation.
