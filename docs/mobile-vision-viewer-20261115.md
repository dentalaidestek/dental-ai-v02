# Native radiograph/intraoral viewer adaptation — 2026-11-15

Web source reviewed: `app/templates/analysis_viewer.html` and `vision_service/templates/radiograph_viewer.js`, `intraoral_viewer.js` at the current mobile-branch snapshot. Their embedded patient viewers read canonical stored vision JSON and draw XYXY bounding rectangles. There is no synthetic lesion segmentation added in native.

NativeVisionViewer replaces the simple image-preview modal in NativeClinicalReview. The owned asset opens with native image loading, SVG overlay, finding list/selection highlight, category filtering, fit/zoom and scroll. Native image decoded dimensions define the SVG coordinate system. Normalized rectangles scale to pixels, pixel rectangles stay in image coordinates and edges clip to bounds. Missing/invalid geometry remains list-only. Reversed/string/invalid rectangles never become invented locations. Canonical finding pools and fusion-supported low-confidence handling are preserved; invalid probability values are rejected. Grad-CAM attention is dashed and explicitly described as attention rather than a verified lesion boundary.

The additive mobile vision route delegates to the actual web `analysis_asset_vision`. Owned scope and stored-inference revision rules remain. A stale/missing snapshot reuses the canonical durable VISION job; failed work returns failure and no automatic paid retry. JSON and image requests remain authenticated/private. Native read polling pauses off-focus/background and errors provide retry. Treatment/selected-teeth and manual-note functions already live in NativeClinicalReview; the viewer does not introduce uncontrolled writes to the tooth chart.

Tests exercise normalized/pixel clipping, dedup/fusion/attention/unlocalized data, natural image/SVG geometry and selected-region highlighting, owner access, stale snapshot job reuse and failed-job behavior. Source tests do not establish device canvas/touch/rotation/color/EXIF fidelity, source-to-native screenshot equivalence, native performance or real production inference. Full original tracker/device/security/store gates remain open. No main merge, backend deployment or store publication.

Final combined checkpoint: TypeScript clean;320Node and240selectedPython passed with zero failures; Android/iOSHermes exports succeeded. The viewer portion includes five native geometry/UI tests and three canonical server snapshot/authorization/job tests. Exact source and clinical acceptance still require real Android/iOS data/device tests.


## Native viewer tabs — 2026-11-17

Re-inspected the web entry app/templates/analysis_viewer.html and both embedded viewers (radiograph_viewer.html / intraoral_viewer.html, plus their JS). The web viewer exposes three persistent actions beneath the image: **Bulgular**, **Tedavi**, and **Klinik Bilgi**. The native viewer previously exposed only the finding list; treatment selection and manual clinical information existed elsewhere on the parent review screen, so the image context was lost when using those actions.

Implemented on the existing native viewer:

- Recreated the dark navy, three-tab layout under the image, retaining native image/SVG geometry, modality asset strip, zoom/fit and finding filters.
- **Bulgular** retains canonical findings, confidence/fusion rules, attention labeling and list-only handling for missing geometry.
- **Tedavi** mirrors the web's permanent FDI selection and preselects only supported permanent-tooth findings. It calls the existing authenticated /analyses/{id}/selected-teeth adapter, which delegates to the canonical web viewer_analyze handler and its durable PRELIMINARY WorkJob. The parent screen remains the single owner of job polling and retry; no second polling loop or AI request was added.
- **Klinik Bilgi** exposes FDI tooth selection, manual finding and note inputs. It delegates to the existing parent callback, which persists the same account+analysis-scoped encrypted SecureStore intent and reconciles the exact canonical note line before clearing the editor. An uncertain result keeps the text and does not auto-resubmit. The mobile endpoint delegates to the web save_viewer_finding / save_analysis_viewer_note handlers.
- No new endpoint, database table, provider call, patient-chart auto-write or clinical taxonomy was introduced. Manual clinical notes remain explicit clinician actions.

Five React renderer regressions were added to mobile/tests/visionViewer.cjs (already included by npm run test:beta): three-tab availability, permanent FDI filtering/treatment delegation, confirmed clinical-note persistence, uncertain acknowledgement preservation, and rendering the canonical treatment result.

**Validation boundary:** these five renderer tests are committed but have not run in this environment. The current GitHub Actions runner issue prevents the repository beta suite from starting. Source inspection confirms the viewer uses only parent callbacks for writes and the existing API/job path; that is not a substitute for the React renderer, full Expo typecheck, Android/iOS device, or clinical acceptance tests.
