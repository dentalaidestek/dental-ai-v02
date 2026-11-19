# Native analysis composer web parity — 2026-11-20

Branch: `feature/mobile-web-parity-20261110`  
PR: #257 (Draft)  
Issue: #258

## Web-first inspection

Before changing the native screen, reviewed:

- `app/templates/analysis_new.html`: anonymous patient context, three numbered steps (Diş, Kısa klinik bilgi, Fotoğraf / Röntgen or Ek görünt), FDI input, hekim note, saved + new image count, safety note and submit action.
- `app/static/style.css`: `.analysis-field-block`, `.analysis-step-title`, `.analysis-field-help`, `.analysis-safety-note` and compact mobile spacing rules.
- `app/main.py::new_analysis` and `create_analysis`: authenticated patient owner check, saved-media patient/owner validation, four-image combined cap and 15 MiB / 48 MiB new-file byte validation before allocating the analysis.
- `app/mobile_analysis_api.py`: the same authenticated patient/saved-media ownership boundary, minimal anonymous patient summary and receipt-backed idempotent native upload.
- `mobile/src/NativeAnalysisUpload.tsx`, `analysisUpload.ts` and `uploadLimits.ts`: native camera/gallery selection, encrypted pending intent, receipt-first recovery, same-key retry, actual multipart byte progress and the shared image/byte limits.

## Gap found

Native upload and recovery behavior was already richer than the web form, but the screen flattened all fields into one generic panel. It omitted the web's visible 1–2–3 hierarchy, the saved-media-specific “Ek görünt” title, the clinical-only helper and the clinical safety note. The 15 MiB / 48 MiB values were also hard-coded in display copy rather than read from the shared byte contract.

## Changes

- Added `analysisComposerPresentation.ts` as the single presentation source for the web-ordered three steps, saved-media title, byte-limit guidance and saved/new image count.
- Reworked `NativeAnalysisUpload` into numbered native step sections. The mobile-specific camera/gallery controls, encrypted preview, removal, progress, cancellation, receipt recovery and retry actions remain intact.
- Added the web-equivalent clinical-only helper and safety note, and a full-width navy primary submit action.
- Limit guidance now derives from `uploadLimits.ts` (4 images, 15 MiB/file and 48 MiB/new-file batch); it does not invent a new limit or alter backend admission.
- Kept the existing four-image combined saved + new limit. Saved media remains an owner-checked reference, not a second byte upload.

## Android typecheck source defect found

Source inspection found a real compile-time contract defect that the hosted runner had not exposed:

- `analysisApi.ts` used `ANALYSIS_MAX_IMAGES` without importing it.
- `NativeAnalysisUpload` and `NativePatientMedia` imported that constant from `analysisApi`, but the module did not export it.

The API module now imports and re-exports the same `uploadLimits.ts` constant. A regression test protects the declaration, import/re-export and both native consumers. The new native style uses supported React Native font-weight values; an initially drafted `850` value was corrected to `800` before finalizing.

This is a source-level fix for the missing-symbol/type-export errors. It is not a claim that the complete Expo project typecheck has now passed.

## Privacy / security review

- The web POST and native API continue to verify patient ownership and every selected saved-media row before creating an analysis.
- The native analysis patient payload remains minimized to anonymous ID, age and chief complaint; the composer does not add name, phone or national ID.
- The upload still binds its durable request key to the owner, patient, selected saved-media IDs, clinical fields and file bytes. The UI change adds no endpoint, provider call, schema, migration, logging of clinical content or patient-record auto-write.
- `NativeDentalAI` keys the upload composer by token + user + patient; the gallery composer is also scoped to its owner/patient key. No account-switch scope was broadened.

## Regression coverage

Added and registered in `npm run test:beta`:

- `analysisImageLimitContract.cjs`: shared four-image constant, API import/re-export and both native consumers.
- `analysisComposerPresentation.cjs`: web step order/copy, saved-media title, 15/48 MiB guidance, saved/new count and native screen wiring. It also asks TypeScript to transpile the native TSX component and fails on syntax diagnostics.

## Verification boundary

- Ran isolated Node 22 / TypeScript fixtures: 3/3 image-limit contract tests and 6/6 composer presentation/TSX-syntax tests passed. The TSX parser check used a minimal component fixture, not the actual repository component.
- Ran strict TypeScript compilation of an isolated shared-limit/import-export fixture: passed.
- The committed TSX transpilation guard reads the actual native component in CI, but this runtime could not execute that guard against the full repository source. These isolated fixtures are not the complete repository test suite and are not a substitute for Expo's full `tsc --noEmit`, `npm test`, Android Gradle, Python security or device acceptance.
- The repository could not be cloned into this runtime because GitHub DNS resolution failed. The committed tests have not been run against the full checkout here.
- At the inspected starting HEAD, the current branch had no workflow runs, no check runs and no commit statuses. Android, Android APK and Security Recovery workflows are `workflow_dispatch`-only. The last retrieved code-bearing hosted jobs from 18 November ended before their first step (empty steps / unavailable `BlobNotFound` logs); they did not execute npm, TypeScript, Gradle or pytest. The exact hosted-runner/account cause remains outside the repository evidence.

No main merge, production deploy, database migration, APK/IPA publication or clinical record mutation.
