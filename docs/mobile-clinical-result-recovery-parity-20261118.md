# Native clinical result and viewer parity — 2026-11-18

## Web flow reviewed first

Reviewed the authenticated web analysis composer and viewer before changing native code:

- `app/templates/analysis_new.html`: patient context, tooth/clinical notes and up to four images.
- `app/templates/analysis_viewer.html`: authenticated asset selection, modality-specific viewer, same-origin message bridge, retry, manual finding/note save and selected-tooth treatment analysis.
- `vision_service/templates/radiograph_viewer.js` and `intraoral_viewer.js`: finding pools, confidence threshold, permanent FDI selection, three tabs and result messages.
- `app/ai_engine.py`: preliminary/final response schemas and validation limits.
- `app/mobile_clinical_api.py`: ownership, source revision, durable job and note routes.

Native path reviewed: `NativeClinicalReview → clinicalApi → NativeVisionViewer`.

## Newly found issues and changes

1. **Restart reconciliation used a different newline delimiter.** The initial SecureStore recovery check split on a literal backslash+n while the explicit reconciliation path split on actual line breaks. A note already committed by the web/API could therefore remain marked as uncertain after app restart. Added one shared exact-line matcher that accepts LF and CRLF and use it in both paths. It does not match substrings and does not automatically resend notes.
2. **Refresh could be tapped before secure-draft recovery finished.** The refresh control is now disabled until the initial local recovery read is complete.
3. **Legacy preliminary status was only partly rendered.** The API accepts `ANALYSIS_COMPLETE` as a valid preliminary status, but the question/consent panel rendered only for `INITIAL`. Native now preserves the same question and clinician-consent step for both statuses.
4. **Clinical result validation was too shallow.** The API checked only that `result.status` was a string. It now validates the known result status set, bounds text fields, caps list lengths to the backend schema, and validates at most three TEXT questions before the result reaches native rendering. Existing error/NEEDS_INFO states remain renderable. No AI provider, prompt, clinical taxonomy or backend result generation was changed.
5. **Both web viewers had a double-escaped FDI digit matcher.** The treatment tab's automatic tooth selection used a regex that matched a literal backslash-d rather than digits. Replaced it with the same permanent-tooth allowlist used by the native viewer. Primary-tooth and malformed identifiers are not silently shown as selected.

## Regression coverage added

- `mobile/tests/clinicalWorkflow.cjs`: exact LF/CRLF note reconciliation, malformed/oversized result payload rejection, valid FINAL/error states and legacy `ANALYSIS_COMPLETE` question/consent visibility. The existing restart-reconciliation test now exercises the corrected path.
- `mobile/tests/visionViewer.cjs`: executes the extracted treatment-selection block from both web viewer scripts and asserts that only supported permanent FDI values are preselected.
- `.github/workflows/security-recovery.yml`: added a dedicated `native-clinical-security` job for the clinical workflow and viewer regressions, plus path filters for the touched sources/tests.

## Verification and limitations

- Static source checks confirmed that both native reconciliation paths call the shared matcher, the refresh gate and legacy-status condition are present, the result validator is wired into `getClinical`, and the new Security Recovery job is present.
- Executed the extracted treatment-selection expression from both web viewer scripts in an isolated JavaScript runtime. Synthetic FDI values `36`, `11`, `55`, `3A`, `18` yielded only `11`, `18`, `36`.
- Executed the actual shared note-matching helper after removing TypeScript-only annotations: LF and CRLF exact-line matches passed; substring and null cases returned false.
- Full `npm run typecheck`, `npm run test:beta`, Node test files, pytest and Gradle were **not executed** in this connector-only runtime. No repository checkout or dependency install was available.

## Current-head CI

CI code head before the final test-fixture correction: `a2cbfa45fd34dab14c653b288ac19b8847c7f1ae`. A follow-up test-only commit changed the LF/CRLF regression to use actual newline characters rather than literal backslash sequences. Final branch head: `a76528b0dbdf73abc82d994e1f7812b6b6c9c3d4`.

- Android CI run `44249077479`: typecheck job `134615048636`, APK job `134615048875`.
- Security Recovery run `44249077401`: new `native-clinical-security` job `134615049033`, plus existing voice/social/academic/Python jobs.
- All reported jobs completed as failure with `steps=null` and `logs_url=null`; fetching both the typecheck and clinical job logs returned `BlobNotFound 404`. The TypeScript compiler, Node tests, pytest and Gradle did not start. This is a pre-step GitHub Actions runner/job-log allocation failure, not evidence of a source-level test failure. The exact hosted-runner/account/billing cause is not exposed by the available GitHub records.

No main merge, production deploy, migration, APK/IPA publication or patient-record mutation was performed.
