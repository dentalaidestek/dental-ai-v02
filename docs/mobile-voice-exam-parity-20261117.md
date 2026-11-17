# Native voice examination parity and private audio cleanup — 17 Nov 2026

## Web-first reference

Reviewed the PR base branch `feature/mobile-beta-20261110` before changing native code:

- `app/templates/voice_exam_entry.html`
- `app/templates/voice_exam_session.html`
- `app/templates/voice_exam_panel.html`
- `app/templates/voice_exam_device_check.html`
- `app/static/voice-exam.css`
- `app/static/voice-exam.js`
- `app/static/voice-exam-live.js`
- `app/static/voice-device-check.js`
- `app/static/voice-pcm-worklet.js`
- `app/voice_exam.py`
- `app/voice_exam_live.py`
- `app/voice_exam_core.py`
- `app/voice_exam_sources.py`
- `app/voice_exam_final.py`

The web session has a visible consent gate, private-draft notice, previous clinician-approved history, a microphone state/timer/waveform, start/pause/finish actions, a transient transcript preview, a manual transcript fallback, chunked extraction checkpoints, a structured review, optional source lookup, an appointment draft, and explicit clinician selection before any patient-file write.

Compared with the web UI, the native recorder previously appeared as a compact text card with plain buttons and no live input-level affordance. Its recording flow was chunked locally, while the web page uses an AudioWorklet PCM16 WebSocket. The native screen intentionally retains Expo Audio's bounded local segment transport; it does not claim browser-equivalent PCM streaming or interim transcription.

## New privacy/data-integrity defect

The native ASR drain previously removed a segment from SecureStore immediately after receiving the transcript, then attempted to delete its cache file with a helper that swallowed deletion errors. If deletion failed, the URI was no longer tracked. The transcript was retained, but a temporary clinical audio file could remain orphaned in the app cache without a cleanup receipt.

## Changes

- Added a durable `transcribed` state to a voice segment.
- ASR success now persists the transcript and its cleanup receipt before touching the source audio.
- The cache file is deleted only from the app-private cache directory; deletion is verified with a follow-up file-info read.
- Only after deletion is confirmed is the cleanup receipt removed from SecureStore.
- On process restart, completed segments are cleaned first and are never sent to Gemini again.
- A failed cleanup keeps the receipt, blocks new recording, and exposes an explicit cleanup retry.
- `persist` now writes to SecureStore before publishing the new in-memory state, so a failed storage write cannot make an uncommitted transcript look durable.
- Native recorder UI now has the web session's navy microphone focal point, timer, microphone-level meter, waveform bars, explicit pause/finish controls, and a bounded recent-transcript preview.
- Recorder files are explicitly created in the app cache and metering is enabled. The meter is presentation only; it does not make a speech-recognition quality claim.
- Corrected two beta-test calls that omitted the now-required persisted ASR request key.
- Security recovery path filters and pytest command now include the canonical web voice routes/core/source/final modules and their route/live tests.

## Changed files

- `mobile/src/voiceSession.ts`
- `mobile/src/NativeVoiceRecorder.tsx`
- `mobile/tests/voiceWorkflow.cjs`
- `mobile/tests/nativeVoiceAudio.cjs`
- `.github/workflows/security-recovery.yml`

## Validation boundary

The updated tests are registered in the existing `npm run test:beta` script (`voiceWorkflow.cjs` and `nativeVoiceAudio.cjs) were already included). The test source now covers required ASR request keys, idempotent transcript receipts, invalid ready/transcribed states, cleanup recovery, and the native web-parity UI contract.

The latest pre-change GitHub run for head `28cd28f6b72b303cf42b48c8af234cdeb26d1940` had Android typecheck/APK and Security jobs fail before any step. The typecheck job's step list was empty, its log download returned Azure `BlobNotFound 404`, and its artifact list was empty. Therefore npm/tsc, Gradle and pytest did not start. The exact hosted-runner/account cause is not exposed by the repository API.

No full repository typecheck, full beta suite, Python pytest, PostgreSQL test, Expo export, Android build, or physical Android/iOS test is claimed as passed in this run. The changed TypeScript/React Native code still needs the actual Actions runner and device acceptance.

## Remaining parity/acceptance

- Native recorder still uses local 15-second segments and ASR after each segment; it does not yet mirror the web PCM16 WebSocket interim transcript.
- Verify the new meter and waveform on physical Android and iOS devices, including Bluetooth microphones and denied/revoked permission.
- Exercise process death at each point: before ASR, after ASR response, after transcript receipt persistence, after file deletion, and before receipt removal.
- Run `npm run typecheck`, `npm run test:beta`, `pytest tests/test_voice_exam.py tests/test_voice_exam_live.py`, Expo export and Android build once Actions runner allocation is available.
- No live AI provider call was made by this change; no transcript/audio/patient data was generated or changed.
- PR #257 remains Draft. No main merge, production deploy, APK/IPA publication or patient-record mutation.
