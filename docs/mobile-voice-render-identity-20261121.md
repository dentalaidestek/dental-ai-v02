# Native voice render identity security review — 2026-11-21

## Web/native flow checked

Web entry and session UI: `app/templates/voice_exam_entry.html` and `app/templates/voice_exam_panel.html`. Browser lifecycle and transcript batching: `app/static/voice-exam-live.js` and `app/static/voice-exam.js`. Server transcription/extraction/finalization: `app/voice_exam.py` and `app/voice_exam_core.py`.

Native equivalents: `mobile/src/VoiceExamEntry.tsx`, `NativeVoiceRecorder.tsx`, `voiceSession.ts`, `voiceApi.ts`, and `NativeVoiceApproval.tsx`.

The parity review confirms the intended sequence remains: explicit consent → user-started capture → bounded local audio segments → transcript persistence/ASR → explicit exam finish → sequential, resumable clinical extraction → source-backed final review → clinician-selected approval. No patient-profile write is triggered by transcription or extraction alone.

## Finding and repair

Three keyed native children in `VoiceExamEntry.tsx` used the raw bearer token as a React `key`: patient selection, microphone recorder, and clinician approval. Keys are renderer identity metadata, not authorization material; embedding credentials there is unnecessary and can expose them to UI inspection/debug tooling.

Replaced those values with process-local opaque keys from `mobile/src/sessionRenderKey.ts`. Their memoization scopes preserve the old remount semantics without embedding the credential:

- patient selector: token/session changes;
- recorder: token, account, or patient changes;
- approval view: token, account, patient, or review revision changes.

The token remains in authenticated API calls only. The change does not alter audio upload, consent, ASR, extraction, checkpoint, or server authorization behavior.

The same web comparison also exposed a disclosure parity gap: the native consent text did not name the transcription and clinical-review providers. The native consent now explicitly identifies Gemini for speech-to-text and Claude for post-finish clinical/source review. The expanded privacy text explains temporary private-device audio staging, that direct identifiers are reduced but full anonymization is not guaranteed, and that raw audio/full transcript are not automatically written to the patient record. A regression assertion covers this disclosure.

## Regression coverage

Added `mobile/tests/voiceRenderIdentity.cjs` and registered it in `npm run test:beta`. It parses the TSX syntax tree and asserts that the three named components use opaque keys, no JSX key expression contains the token identifier, memoization scopes rotate on relevant account/patient/review changes, and the native consent/privacy copy names Gemini and Claude with the correct data-handling boundary.

Run from `mobile/`:

```sh
npm run typecheck
npm run test:beta
```

Remote CI for the starting commit had no associated workflow runs and no reported status checks. The newly pushed commits must receive fresh Actions execution before this change can be called CI-verified. No local test execution is claimed in this review.

## Boundaries

No main merge, production deployment, APK/IPA release, schema migration, provider/model change, or patient-data mutation was performed. Web production behavior was inspected as the parity reference; this work did not modify web or production code.


## 2026-11-21 follow-up — CI harness repair and native entry parity

### Starting-head CI diagnosis

The PR workflow attached to starting head `f48c1b39fa67508d64c971199a6ba607c0da83bd` ran successfully through Android TypeScript typecheck, session/auth tests, realtime/pagination tests, APK assembly and Android/iOS JS bundle export. The mobile beta suite then reported 969/974 passing, with five VoiceExamEntry tests failing at the same VM boundary: `sessionRenderKey_1.nextSessionRenderKey is not a function`.

Security Recovery showed the same five VoiceExamEntry failures in the native voice/clinical jobs. Python security/identity recovery, PostgreSQL migration/concurrency, and the native Program, Social, Academic and Support security suites passed. The failure was therefore isolated to the CJS VM test-loader contract, not an Android TypeScript error or a demonstrated clinical authorization defect.

### Repair and web parity work

- Rebuilt `mobile/tests/helpers/sessionRenderKeyModule.cjs` using Node's CommonJS module loader so VM harnesses receive the actual production `nextSessionRenderKey` function.
- Made all six voice/approval VM loaders accept both extensionless and explicit `.ts` session-key specifiers; the suite now asserts the bridge export is callable before rendering.
- Updated the voice workflow regression to verify that a route carrying a server-verified `initialPatientId` opens the examination directly. The web `/voice-exams/{patient_id}/session` route already does this, while native previously required a redundant second tap.
- Reworked the native Voice Exam selection screen to follow the web hierarchy: clinical-assistant hero, three-step progress, separate new/existing patient cards, and the microphone/privacy notice.
- Added contextual patient-search labels for Voice Exam without changing the default appointment selector copy or its existing pagination, query bounds, or TCKN display boundary.

### Commits on the feature branch

- `401e1f0` — load the production session-key helper through CommonJS
- `9ca1907` — normalize voice VM resolution and test direct session routes
- `145c00c` — guard all voice helper VM mappings
- `c734bfe` — make shared patient selector copy contextual
- `276b8bc` — align native Voice Exam entry and direct patient routing with web
- `88b13d7` — test contextual patient-search labels
- `e508034` — test Voice Exam entry hierarchy and direct-route parity

### Validation boundary

Fresh CI for the repaired head must still complete before these changes are called verified. No local Android build or device test is claimed. No web/backend code, provider behavior, database, patient data, production environment, main branch or live deployment was changed. The next gate is the new Android and Security Recovery runs; after they pass, continue the web-first patient profile/media and AI-analysis acceptance work. The 60,000-user target remains un-certified.
