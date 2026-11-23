# Mobile patient-profile visual parity and CI diagnosis — 2026-11-21

## Web-first reference

Before editing the native profile, reviewed:
- `app/templates/patient_detail.html`: patient hero, identity, chief complaint, four quick actions, collapsible patient information, clinical-media archive, analysis history, approved voice anamnesis and treatment history.
- `app/static/style.css`: the `@media(max-width:760px)` patient-detail rules. The web mobile profile uses a compact 50 px circular avatar, separate age/phone/patient-number chips, a 4-column quick-action row with blue/purple/red/green actions, 70 px stacked action tiles, a 54 px information summary and compact 9 px page gaps.

The native profile already had the same core actions and backend-backed sections, but its quick actions used two wide navy tiles with explanatory copy, its identity metadata was split into plain lines, and the patient-information card was more spacious than the web mobile layout. The changes on this branch bring those native presentation decisions closer to the actual web mobile reference without introducing a WebView or changing the clinical data path.

## Native changes

- Four 25%-width action slots now use the web order and color sequence: tooth chart, AI analysis, appointment and treatment. Tiles keep accessible labels/hints and 70 pt touch height; the web-absent explanatory copy was removed.
- Patient hero now uses a 50 pt circular avatar, separate age/phone/patient-number chips and a compact complaint row.
- Patient-information disclosure, section spacing and card padding now follow the web mobile density more closely.
- Existing action handlers, profile edit revision checks, durable treatment/delete intents, child remount scopes, patient authorization, upload receipts and history APIs are unchanged.

## Android CI diagnosis before this fix

Inspected the completed Actions runs for starting HEAD `f48c1b39fa67508d64c971199a6ba607c0da83bd`:
- Android run [#44915086719](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44915086719): TypeScript typecheck passed; session/auth and realtime/pagination tests passed; Expo Android+iOS bundle export passed; internal Android APK assemble and artifact upload passed. The beta suite ran 974 tests: 969 passed and 5 failed.
- Security recovery run [#44915086710](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44915086710): the main Python/security/PostgreSQL job passed. Native program, social, academic and support jobs passed. Native voice (81 tests) and native clinical (267 tests) each had 5 failures.

All 15 failures shared one test-harness root cause: `mobile/tests/voiceWorkflow.cjs` evaluated `VoiceExamEntry.tsx` in VM loaders but did not map the new `./sessionRenderKey` import to the existing CommonJS bridge. The VM fallback returned a placeholder module, so the rendered tests raised `nextSessionRenderKey is not a function`. This was not an Android TypeScript compiler failure: the typecheck step was green. The workflow failure was therefore isolated to the voice component test harness and its dependent beta/clinical suites.

The code change adds the shared bridge to every voice VM loader and a regression guard requiring all six loader mappings. The patient-profile visual regression asserts the four-column layout, color order, 70 pt tiles, circular avatar and metadata pills.

## Validation boundary

These changes are committed to `feature/mobile-web-parity-20261110` and remain in PR #257. Fresh CI on the new head is the acceptance gate; no pass is claimed until those runs finish. No main merge, live deployment, migration, APK publication or real patient-data mutation was performed. Physical Android/iOS screenshots, accessibility-device checks and 60,000-user load/cost tests remain open.
