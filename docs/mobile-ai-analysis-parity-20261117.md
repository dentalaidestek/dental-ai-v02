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


## 2026-11-21 — CI root causes and private image refresh

Web-first recheck: app/templates/analysis_viewer.html, vision_service/templates/radiograph_viewer.js and vision_service/templates/intraoral_viewer.js were inspected before the native viewer change. The web viewer loads the owned image and vision snapshot with cache: no-store; its parent frame is analysis/asset scoped and the native clinical image endpoint already emits private no-store headers.

At starting HEAD dda4cfd52c6a82f25985349e78b6d91840deda52:
- Android CI 44808024759: TypeScript typecheck, session/auth, realtime/pagination and the independent ARM64 APK job passed. The beta suite ran 897 tests: 874 passed, 23 failed. All 23 failures shared one harness error: unexpected import ./toothChartHistoryPresentation. toothChartLifecycle.cjs had not registered the newly added pure presentation module in its VM require map.
- Security Recovery 44808024767: five native security jobs passed. Python security had 561 passed and one failed. The route assertion counted both /patients/.../file (web) and /api/mobile/v1/patients/.../file (mobile) because it matched only a suffix; it did not identify two mobile handlers. PostgreSQL checks were skipped after that test failure.
- The failed Android workflow was not a TypeScript failure: the typecheck step was green. The Android/iOS Hermes exports also completed. The beta suite failure and the Python route-test failure are separate test-harness defects; no production authorization rule was weakened.

Corrections:
1. Registered toothChartHistoryPresentation.ts in the tooth-chart lifecycle VM harness.
2. Restricted the canonical-route assertion to the exact /api/mobile/v1 path while retaining the separate web route.
3. Exported the one canonical mobile API base and reused it for clinical image requests.
4. Added cache: reload to private clinical image sources and an account-scoped React key for profile thumbnails, so an account change remounts the image instead of reusing the previous account's rendered component.
5. Added a renderer regression for API base, forced reload, Authorization replacement and account-scoped remount.

These changes are committed; the new HEAD still requires hosted CI execution. No claim of green post-fix tests is made here. No main merge, production deploy, clinical record mutation or store publication.
