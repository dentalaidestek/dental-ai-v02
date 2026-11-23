# Mobile CI VM dependency parity — 2026-11-22

## Web-first review

Before repairing the native regressions, re-read the canonical web patient profile and chart flows:

- `app/templates/patient_detail.html`: profile identity and four quick actions; revision-protected edit/delete; clinical archive upload, media selection, preview/delete, and cursor-based history; analysis history; approved anamnesis; treatment history.
- `app/templates/tooth_chart.html`: FDI selection, upper/lower orientation, tooth preview, anatomical surface pins, status controls and treatment history.
- `app/templates/analysis_new.html`: patient-scoped analysis, FDI tooth, clinical notes, saved-media composition, four-image limit, and byte limits.
- Native counterparts: `NativePatientProfile`, `NativePatientMedia`, `NativeToothChart`, `NativeAnalysisUpload`, `api.ts`, and `modernApi.ts`.

The native profile already carries the same major patient actions and clinical sections. The clinical-media and analysis flows are intentionally native, not WebView-based, and preserve encrypted pending uploads, stable request keys, patient/account scoping and receipt-first recovery.

## Latest-head CI diagnosis

On starting HEAD `48219d157059177871d08de55ee8f179d38da828`:

- Android run [#45013261117](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/45013261117): TypeScript typecheck **passed**; session/auth tests **passed**; realtime/pagination tests **passed**; Expo Android+iOS bundle export **passed**; internal Android APK build and artifact upload **passed**. The beta suite ran 1,014 tests: 1,002 passed and 12 failed.
- Security Recovery run [#45013261147](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/45013261147): all seven jobs passed, including Python/security, PostgreSQL migration/concurrency, web form/live voice, and native program/support/voice/academic/clinical/social regressions.

All 12 beta failures were test VM dependency-map omissions, not production TypeScript errors:
- 2 selected-media analysis regressions evaluated `modernApi.ts` without its new `./apiCompatibility` dependency.
- 6 clinical-media pagination regressions did the same.
- 4 tooth-chart focus regressions evaluated `api.ts` without its new `./apiCompatibility` dependency.

The application clients had intentionally centralized bare FastAPI 404 handling in `apiCompatibility.ts`. The affected VM loaders had not been updated to expose that shared module. No assertion was removed or weakened.

## Changes committed

- `58bcb1e` — map the shared compatibility module in the selected-media account-switch test loader.
- `ddc0928` — map the shared compatibility module in the clinical-media pagination loader.
- `a2fe629` — map the shared compatibility module in the tooth-chart focus loader.
- `ce1af68` — add direct regressions proving bare missing-route 404s are surfaced consistently by tooth-chart and clinical-media clients, while patient-scoped 404s remain distinct.

The new regression cases use the real `apiCompatibility.ts` implementation and the actual API-client functions.

## Acceptance boundary

These changes are on `feature/mobile-web-parity-20261110` / PR #257. Final-head Android and Security Recovery runs must complete before the new regressions can be marked passed. The typecheck and security results above belong to the starting head, not the new commits.

The separate source comparison in `docs/mobile-live-api-compatibility-20261122.md` remains a production blocker: the inspected `main` snapshot does not register the native analysis-upload receipt, clinical-media upload receipt, and consultation attachment/receipt routes. Those routes exist on the feature branch but cannot be used by the production APK until the backend change is reviewed, merged and deployed with explicit approval.

No main merge, live deployment, database migration, APK publication, patient-data mutation, or production storage operation was performed. Physical Android/iOS acceptance and 60,000-user load/cost testing remain open.
