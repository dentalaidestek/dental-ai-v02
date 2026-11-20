# Native patient history parity — 2026-11-20

## Web-first reference

Inspected before the native change:
- `app/templates/patient_detail.html`: patient-scoped history sections, explicit "Detay" action, "Daha fazla analiz yükle" continuation and treatment-history expand/collapse.
- `app/templates/patient_analysis_history_items.html`: analysis/voice-review title, tooth, timestamp, status, explicit detail action, separate clinical-image and radiograph groups, legacy radiograph fallback and result link.
- `app/patient_history_web.py`: cookie-session routes, patient-owner recheck, stable descending (created_at, id) cursor, private/no-store response.
- `mobile/src/NativePatientHistory.tsx` and `mobile/src/modernApi.ts`: native patient/tooth-scoped cursor and protected detail/assets.

## Gaps fixed

1. Native history rows were bare divider-only pressable text; the web uses a bordered history row with title, metadata, status and an explicit Detay action. Native now uses a compact card, separate FDI/date chips, a status badge and an accessible Detay button.
2. When a native continuation-page request failed, the generic retry action called `load(false)`, silently restarting from page one and discarding the already loaded continuation context. The error now remembers whether the failed request was a continuation and retries the same cursor. Existing pages remain visible and duplicate IDs remain filtered.
3. Invalid timestamps now render a safe Turkish fallback instead of `Invalid Date`; voice-review entries do not show a tooth label, matching the web partial.

## Files

- `mobile/src/patientHistoryPresentation.ts` — bounded presentation helpers and status tone.
- `mobile/src/NativePatientHistory.tsx` — web-aligned history cards and same-cursor retry.
- `mobile/tests/patientAnalysisHistory.cjs` — card/detail/status assertions.
- `mobile/tests/patientHistoryRetry.cjs` — failed continuation retry and presentation edge cases.
- `mobile/package.json` — registers the new regression in `test:beta`.

## Validation boundary

The GitHub source was read back from `feature/mobile-web-parity-20261110` after each sequential write. The new test is registered in the beta suite. This automation runtime has no repository checkout, node_modules, React Native/Expo dependencies or FastAPI/SQLModel environment, so the committed Node tests, full TypeScript check, Expo export, Android Gradle/device build and Python integration/security suites were not executed here. Do not treat source read-back as a test pass.

No API, schema, database migration, patient data, AI provider, production deployment, APK/IPA publication or main branch was changed.
