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


## 2026-11-17 follow-up — private voice-cache path containment

Web-first recheck covered the canonical voice entry/device-check/session panel, voice-exam.js, voice-device-check.js, voice-pcm-worklet.js, and the native recorder/ASR adapter before changing the file boundary.

### New security finding

The persisted native draft parser accepted any file:// URI. The ASR uploader also accepted any file:// URI, so a corrupted or stale SecureStore record could direct the upload task at an app-readable file outside the recorder cache. Separately, the cleanup guard used only a string-prefix check against cacheDirectory; a cache-prefixed traversal such as cache/../Documents/... could pass that check. A malformed segments array containing null could also throw in the duplicate-ID pass before row validation.

### Changes

- Added a URI-shape validator for persisted segments: absolute file URI, no encoded path, query/fragment, control characters, backslash, dot segments, malformed filename, or non-.m4a recording.
- Added a runtime cache-root validator that accepts only one direct .m4a child of Expo's actual FileSystem.cacheDirectory. ASR upload rejects an out-of-scope path before file metadata reads or upload-task creation.
- Reused the same runtime validator before deletion. Draft clear skips untrusted paths, never deletes outside the app-private cache, and explains that the unverified file was left untouched.
- The recorder now validates Expo Audio's returned URI immediately after preparation and before calling record(), so an unexpected output location never opens the microphone.
- Validated segment rows before building the duplicate-ID set, so malformed rows fail closed with the normal draft-validation error.
- Added a dedicated native-voice-security job to Security Recovery. Its path filters include the native voice boundary and it runs node --test tests/nativeVoiceAudio.cjs. The existing Android workflow already watches all mobile/** changes and runs the full beta suite/typecheck.

### Regression coverage

The committed Node test now covers valid cache child, outside-cache path, traversal, encoded traversal, nested path, cache-prefix collision, query string, wrong extension, rejection before file read/upload, malformed draft rows, and recorder cleanup guard usage. The test is included in the existing npm run test:beta command.

### Validation boundary

The test source is committed and the workflow is wired, but the Node test, full TypeScript typecheck, beta suite, pytest, Expo export and Android build are not yet confirmed as executed. On starting HEAD d61ae1b, Android typecheck job 134255233806, Security job 134255233520 and Voice job 134255233557 each returned an empty step list; their log downloads returned Azure BlobNotFound 404. These jobs did not provide compiler/test output. The exact hosted-runner/account cause remains unavailable from the GitHub API; no speculative runs-on change was made.

No transcript/audio/patient record was created or modified. No main merge, production deploy, migration, APK/IPA publication or store release.
