# Approved voice anamnesis on patient profile — 17 November 2026

## Web flow checked before changing native UI

Re-read the web voice entry/session and the patient detail route/template:
- `app/templates/voice_exam_entry.html`
- `app/templates/voice_exam_session.html`
- `app/templates/patient_detail.html`
- `app/voice_exam.py`
- `app/main.py`

The web voice flow has an explicit clinician review and save action. `POST /patients/{patient_id}/voice-exam/apply` stores only selected fields in a `VOICE_REVIEW` analysis record and a minimal idempotency WorkJob. The patient detail page already marks those rows as “Sesli muayene”, but did not surface the approved anamnesis fields in a dedicated profile section. Native VoiceExamEntry could read the same approved-history endpoint, but the patient profile had no corresponding section.

## Root cause fixed

`reviewed_history_payload()` split `Analysis.clinical_notes` on the two literal characters `\\n` rather than the actual blank-line separator. The apply path writes actual newline characters with `'\\n\\n'.join(...)`, so the history reader could not match the saved field labels and returned an empty anamnesis even after a successful clinician-approved save.

The reader now splits on the actual blank-line delimiter. Added a route regression that applies medical history, medication, allergy and family-history values, reads the history endpoint, checks the exact values/source analysis IDs, and verifies another owner's patient remains 404.

## Changes

- Web patient detail route now computes `voice_history` only for the owning clinician, using the existing approved-history reader and existing ownership checks.
- Web patient detail renders a separate **Hekim Onaylı Anamnez** card between analysis and treatment history. Values are escaped by normal template rendering; each row shows its source voice-analysis ID.
- Added `patientVoiceHistoryPresentation.ts` with a fixed clinical display order and allowlisted field mapping.
- Added `NativePatientVoiceHistory.tsx`, which reads the existing bearer-protected history endpoint when the patient profile is focused and after relevant patient/analysis realtime events. It does not persist the response locally.
- Connected the card to `NativePatientProfile.tsx`.
- The native card preserves the clinician-approved wording, including negative statements such as “Alerjim yok”; it does not reinterpret an old statement as a current diagnosis or medication. It shows the server notice and source analysis ID.
- Late responses are scoped to the current token/patient; switching patient invalidates the previous request.
- Added six native component regressions for field ordering, negative statements, empty history, retry after errors, stale patient response isolation, and hiding old clinical values after a failed refresh. Added API tests for the authenticated GET route and strict field/source validation. Registered the suite in `npm run test:beta`.
- A JavaScript syntax parse of the touched native tests exposed a malformed pre-existing regex in `mobile/tests/voiceApi.cjs` (`Invalid regular expression flags`). Replaced it with an explicit `endsWith()` route assertion; both touched CJS test files now parse successfully.

## Data and privacy boundaries

- No Patient columns were invented and no schema migration was added.
- The source remains the existing completed `VOICE_REVIEW` WorkJob joined to its Analysis record.
- No transcript, raw audio, provider payload or private coaching is added to the profile history response.
- Only explicitly saved fields are displayed; no inferred or unapproved extraction is written to the patient profile.
- The web profile section is limited to the owning clinician. The native endpoint continues to enforce the existing patient ownership check and `private, no-store` response behavior.
- No clinical records or production storage were read or changed.

## Validation and remaining gates

Added:
- 1 backend regression for save → history read → ownership isolation.
- 2 voice-history API regressions.
- 5 native presentation/component regressions.

The new tests are committed but have not yet been executed in this run. At starting head `7ae4c65d`, Android typecheck, beta APK, Security Recovery and Voice Regression workflows failed before exposing any steps; step queries returned empty arrays and log downloads returned `BlobNotFound 404`. This does not identify a TypeScript/Python source failure. Exact hosted-runner/account/billing cause is not available from the returned GitHub records.

No merge, production deploy, migration, APK/IPA publication or patient-record mutation.
