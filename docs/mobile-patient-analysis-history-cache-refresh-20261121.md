# Native patient analysis history — private image and refresh parity — 2026-11-21

## Web flow inspected first

Before editing the native history screen, reviewed:
- `app/templates/patient_detail.html`: analysis-history section, cursor-based history paging and detail-modal lifecycle.
- `app/templates/patient_analysis_history_items.html`: web analysis/voice-review labels, clinical-image and radiograph grouping, legacy radiograph fallback, and the full-result link.
- `app/templates/analysis_viewer.html`: authenticated asset retrieval uses a no-store fetch before passing image data to the viewer.
- Native comparison: `NativePatientHistory.tsx`, `analysisApi.ts`, `clinicalMediaPresentation.ts`, `NativeVisionViewer.tsx`.

The native history modal used authenticated bearer headers but omitted the existing native private-image revalidation policy. Its asset image components also had no non-secret session-scoped identity. Separately, a history refresh arriving during an in-flight page request was dropped by the request lock. The screen also invoked its initial loader from both the scope effect and the initial focused effect.

## Changes on the PR branch

1. Added `patientAnalysisHistoryImages.ts`:
   - Generates opaque per-component image scopes; the scope/key never contains a bearer token.
   - Validates positive analysis/asset IDs.
   - Builds only canonical mobile analysis asset or legacy-radiograph paths.
   - Supplies the Authorization header and `cache: 'reload'` so the native image pipeline revalidates the private endpoint.
2. Updated `NativePatientHistory.tsx`:
   - Applies a session-scoped React identity and test ID to every clinical image, radiograph and legacy radiograph.
   - Uses the same API_BASE as the mobile API rather than duplicating the production URL in the component.
3. Fixed history refresh lifecycle:
   - A first-page refresh arriving during an active request is coalesced and runs once after the current request settles.
   - Pagination requests do not accidentally queue another first-page read.
   - Initial focus no longer duplicates the scope-initialization read.
   - A previously retained realtime event is not replayed as a fresh event on mount; new matching patient events still refresh the history.

## Regression coverage

Updated `mobile/tests/patientAnalysisHistory.cjs` to cover:
- Private asset and legacy radiograph URLs, bearer header, and cache revalidation.
- Opaque image identity changes across token/session changes without exposing the token in the key.
- Invalid IDs, malformed scope and whitespace-containing token rejection.
- Exactly one initial read, a matching realtime event queued during an in-flight request, and rejection of an unrelated patient's event.

The test file is already part of `npm run test:beta`; no extra test runner or package dependency was introduced.

## CI evidence at the starting head

Starting head: `9e79933b29a7356e8477f84e603daa0aa35029db`.

- Android workflow [44891469638](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44891469638): TypeScript typecheck, session/auth tests, realtime/pagination tests, beta regressions, Android/iOS JS export and internal Android APK all completed successfully.
- Security Recovery [44891469566](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44891469566): Python security/identity, PostgreSQL migration/concurrency, form duplicate-submit guard and native Academic, Social, Program, Voice, Clinical and Support regression jobs all completed successfully.
- The GitHub check-run API showed nine successful checks. The legacy combined commit-status endpoint remained `pending` with no status entries; this is not reported as an additional green status.

The new commits require a fresh latest-head run before the new image/refresh regressions can be called CI-passing. No local full Expo/device run is claimed.

## Remaining acceptance

- Android/iOS physical-device verification of authenticated image cache revalidation, account switching, background/foreground and revoked-access behavior.
- Full patient-detail screenshot/touch parity against the responsive web page.
- Full end-to-end workflow and 60,000-user capacity tests remain separate gates.

No patient record, production database, migration, provider prompt, clinical taxonomy, main branch, deployment, APK/IPA publication or store release was changed.
