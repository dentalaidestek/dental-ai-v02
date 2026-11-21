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

## Regression coverage

Added `mobile/tests/voiceRenderIdentity.cjs` and registered it in `npm run test:beta`. It parses the TSX syntax tree and asserts that the three named components use opaque keys, no JSX key expression contains the token identifier, and the memoization scopes continue to rotate on the relevant account/patient/review changes.

Run from `mobile/`:

```sh
npm run typecheck
npm run test:beta
```

Remote CI for the starting commit had no associated workflow runs and no reported status checks. The newly pushed commits must receive fresh Actions execution before this change can be called CI-verified. No local test execution is claimed in this review.

## Boundaries

No main merge, production deployment, APK/IPA release, schema migration, provider/model change, or patient-data mutation was performed. Web production behavior was inspected as the parity reference; this work did not modify web or production code.
