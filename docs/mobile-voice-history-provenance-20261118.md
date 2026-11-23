# Voice-exam history provenance correction — 18 November 2026

## Web-first finding

Compared the web session panel and `voice-exam.js`, the native `VoiceExamEntry` / `NativeVoiceApproval` components, and the shared `reviewed_history_payload` used by both web and mobile history endpoints.

## Defect

The approved-history endpoint parsed a saved clinical-note value and returned that same value in both `value` and `quote`. Native and web review screens then labelled `quote` as a previous-record speech basis. The underlying value was an approved structured note, not a retained verbatim transcript excerpt. This overstated provenance and could make a clinician believe an original patient statement was still available when it was not.

## Correction

- The shared web/mobile history payload now returns an empty `quote`; the approved value and source analysis ID remain unchanged.
- Native provenance presentation treats history as a prior approved field value, ignores legacy history `quote` strings, and explicitly says the original transcript excerpt is not stored and current validity must be confirmed with the patient.
- The native approval screen repeats that distinction immediately before the explicit save action.
- The web review screen uses the same distinction and no longer labels a prior value as a transcript quote.
- Current-examination quotes remain visible, bounded to the existing 3,000-character limit. Missing current evidence is shown as missing, not invented.
- Added web, mobile API, helper and renderer regressions; the helper/API regressions are already part of `test:beta`, and `voiceEvidence.cjs` is also included in the Security Recovery native-clinical job.
- No schema, provider, AI prompt, endpoint, patient record or production data was changed.

## Validation boundary

The tests are committed to existing suites. This connector-only environment does not provide the repository checkout or installed SQLModel/React Native dependencies, so the full pytest, Node beta suite, TypeScript project check, Expo export, Android Gradle build and physical-device acceptance were not executed. GitHub Actions on the starting HEAD had no associated runs/status checks. The latest historical Android typecheck/APK and Security jobs had `runner_id=0`, `steps=null`, and `BlobNotFound 404` log retrieval; no compiler or security test started. Current workflow definitions are manual-only and the connected GitHub tools do not expose workflow dispatch.

No main merge, production deploy, migration, APK/IPA publication or patient-data mutation.
