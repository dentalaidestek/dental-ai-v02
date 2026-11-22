# Native microphone preflight — audio-mode restoration safety

Date: 2026-11-22  
Branch: `feature/mobile-web-parity-20261110`  
PR: #257 · Issue: #258

## Web-first flow traced

Before changing native behavior, re-read the canonical web preflight and live voice path:

- `app/templates/voice_exam_panel.html` — the microphone check is separate from patient consent and the live examination.
- `app/static/voice-exam-live.js` and `app/static/voice-pcm-worklet.js` — the browser owns a media stream and AudioContext; stopping the stream closes the browser capture resources.
- `app/voice_exam.py` — live ASR is a separate consented server flow; the device check does not call it.
- Native counterpart: `NativeVoiceDeviceCheck`, `voiceDeviceCheck`, `NativeVoiceRecorder` and `voiceRecorderLifecycle`.

The web browser preflight does not change a process-wide Expo audio mode. Native Expo Audio does: setting `allowsRecording=true` changes app-wide routing, so a device check must explicitly restore `allowsRecording=false` after success, cancellation, backgrounding, navigation and start failure.

## Newly found defect

Native `NativeVoiceDeviceCheck.resetAudioMode()` swallowed `setAudioModeAsync({allowsRecording:false})` failures with `.catch(()=>{})`. The component then reported the microphone check solely from permission, duration, file size and meter values. A capture could therefore appear successful while the app-wide audio route remained in recording mode.

This is separate from the previously fixed temporary-file cleanup check: a file can be deleted correctly while the global audio-mode reset still fails.

## Changes

- Added the explicit `audio_mode_restore_failed` outcome to the pure device-check classifier.
- Kept backwards compatibility for callers that do not provide an audio-mode result.
- Reused the existing `restoreVoiceAudioMode` helper so platform setter rejection becomes a boolean failure rather than a swallowed success.
- The native preflight now records the restore result after normal finish, cancellation, stale-start cancellation and recorder-start failure.
- A failed restore blocks another microphone preflight and presents an accessible warning.
- The retry action re-attempts both outstanding cleanup and audio-mode restoration. It only unblocks the next test after the private file is absent and the app-wide audio mode has been restored.
- Private audio remains local-only; no patient identifier, transcript, session token or audio bytes are sent or persisted by the device check.

## Regression coverage

- `mobile/tests/voiceDeviceCheck.cjs`: explicit audio-mode restore failure, success, backwards-compatible default and cleanup-warning precedence.
- `mobile/tests/voiceDeviceCheckUI.cjs`: rejects the old swallowed-error implementation, requires the restore result to reach UI state, blocks another test after failure and requires an explicit retry action.
- Existing `voiceWorkflow.cjs` already tests the shared `restoreVoiceAudioMode` helper's success/failure contract and the main recorder's rotation-failure/unmount recovery.

## Verification boundary

At the starting HEAD `313a44a483dbdcfb28c01922b754eaf1b0ebb704`:

- Android typecheck completed successfully.
- Session/auth, realtime/pagination and the full beta regression command completed successfully.
- Android/iOS Expo bundle export completed successfully.
- The internal Android APK job was still assembling.
- Security Recovery was pending without job records at the last check.

The five follow-up commits add code, helper tests, UI contract tests and this acceptance note. Their CI must complete on the resulting HEAD before these new regressions are claimed as passing. Physical Android/iOS checks remain required for Bluetooth routing, calls/notification interruptions, background/foreground and playback after microphone preflight. No physical device, patient data, production API, main merge or live deploy was used.
