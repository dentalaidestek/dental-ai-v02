# Native voice examination — prior approved history parity

Web-first comparison performed on 2026-11-16 before native changes:

- `app/templates/voice_exam_panel.html`: the web screen exposes an explicit “Önceki bilgiler” section, a read action, a patient-confirmation checkbox and a separate “Doğruladığım bilgileri muayeneye ekle” action.
- `app/static/voice-exam.js`: the web action reads only the dedicated voice-history endpoint. It does not treat the entire patient archive as voice history. It adds old fields only after the clinician confirms with the patient; current-vs-prior conflicts remain visible as uncertainty.
- `app/voice_exam.py`: the existing history query joins completed `VOICE_REVIEW` jobs and limits the read to the authenticated patient owner. It returns selected approved field values and a revision, not audio or transcript.

## Gap found

The native recorder, transcript checkpointing and clinician-approval path existed, but `VoiceExamEntry.tsx` had no equivalent history controls and `voiceApi.ts` had no native history read. A clinician switching from web to mobile could not review the prior voice-approved medical-history, medication, allergy, family-history, material, dental-history or oral-habit statements in the voice workflow.

## Changes

- Extracted the web query into `reviewed_history_payload` so web and native use the same allowlist, completed-job filter, owner scope and 12-record bound.
- Added authenticated `GET /api/mobile/v1/patients/{patient_id}/voice-exam/history`. It checks the mobile account role and patient ownership, returns `Cache-Control: private, no-store` and `Vary: Authorization`, and never returns raw audio or transcript.
- Added native API validation for the SHA-256 revision, allowlisted field names, bounded values, and positive source analysis IDs.
- Added a native “Önceki kayıtları göster” panel. It lists only voice-approved history, requires a separate clinician confirmation before adding anything to the current draft, and leaves all fields unselected for final patient-file approval.
- When a prior field conflicts with the current extraction, the current examination value is retained and the old/new statements are surfaced in the uncertainty section. Prior history is not silently substituted and no patient record is written by the history action.

## Commits

- `4a714ad` — shared owner-scoped web history helper
- `21023b1` — authenticated native history endpoint
- `cb12383` — validated mobile API contract
- `058593c` — native history loading, confirmation and conflict handling
- `cdcaa14` — API privacy/provenance regressions
- `e138111` — native UI confirmation/conflict regression
- `5166a77` — backend ownership, completion and archive-isolation regression

## Validation and limits

- Source-contract inspection confirms the web and native route share the same approved-history query and that the mobile response is private/no-store.
- Added tests to `mobile/tests/voiceApi.cjs`, `mobile/tests/voiceWorkflow.cjs` and `tests/test_mobile_voice_workflow.py`. The mobile test files are already included in `npm run test:beta`; the Python test file is already included in the Security recovery workflow.
- These tests were committed but **not executed in this environment**. Current GitHub Actions jobs still fail before runner allocation: `runner_id=0`, no steps, and log download `BlobNotFound 404`. This is not a source-test failure and not a green CI result.
- Actual Android/iOS device appearance, microphone interruptions, provider accuracy and 60,000-user load acceptance remain open.

No main merge, production deploy, migration, APK/IPA publication or patient-record mutation.
