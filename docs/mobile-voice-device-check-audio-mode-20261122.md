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


## 2026-11-22 follow-up — route owner correction and prepared-recorder cleanup

### Starting-head CI diagnosis

Starting HEAD: `32a272c27867058a34e405071e80cf4dedc1acab`.

- Android run [#44989322878](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44989322878) completed successfully: TypeScript typecheck, session/auth, realtime/pagination, 991 beta tests, Android+iOS bundle export and internal APK assembly all passed.
- Security Recovery [#44989322945](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44989322945) completed with 618 passed / 1 failed. All six native security jobs passed. The Python suite's only failure was the clinical media route ownership regression.
- Exact root cause: the test looked for GET `/patients/{patient_id}/media` in `app.mobile_api.router`, but the active canonical GET gallery is `app.mobile_modern_api_v3.mobile_patient_media`. The primary `app.mobile_api` router owns the receipt-aware POST upload and original-file GET. The v3 legacy POST is shadowed by method/path deduplication. Production route ownership and cache headers were already correct; the test expected the wrong source router.
- Corrected the test to resolve GET from the v3 router, retain POST from the primary router, and assert the canonical GET handler is mounted exactly once with `private, no-store` headers. No production endpoint or authorization rule was weakened.

### New native voice lifecycle findings

Re-read the web flow first: `voice_exam_panel.html` → `voice-exam-live.js` → browser MediaStream/AudioWorklet stop on hidden/pagehide. Compared with `NativeVoiceRecorder.startChunk()`, `cut()`, `discardUnstartedSegment()`, AppState/focus handling and the Expo Audio preflight.

1. Expo Audio `prepareToRecordAsync()` allocates a recorder file before `record()`. The native recorder previously left its `stopped` flag true during the asynchronous encrypted-draft persistence window. If the app backgrounded in that gap, the unstarted segment could be removed from the draft and its file deleted without first stopping the prepared recorder; audio-mode restoration could then be attempted while the recorder was still prepared.
2. If the recorder returned a URI outside the app cache, the device-check component threw before storing that URI in its in-memory cleanup reference. The catch path then treated `null` as already clean and could allow another microphone check. It did not send the file anywhere, but the local cleanup state was falsely optimistic.
3. A failed stop during interruption previously allowed a stale status snapshot to set `stopped=true`. That could permit audio-mode restoration and another start while the actual stop had not been verified.

### Changes

- Mark the Expo recorder as not-stopped immediately after successful prepare; keep that state through draft persistence and the record transition.
- Stop the prepared recorder before deleting an unstarted segment, on start/persist failure, during background/blur and during unmount cleanup. A failed stop keeps the session blocked and retains an in-memory cleanup reference.
- Add a strict direct-child app-cache cleanup helper. It may remove a malformed recorder artifact only if it is a single safe filename directly inside the app-private cache. Nested paths, traversal and any URI outside that cache are never passed to filesystem deletion.
- The explicit device check now retains an unexpected returned URI before validating it. If the URI is outside cache or cleanup cannot be verified, the check stays blocked instead of reporting cleanup success.
- Clearing a voice draft no longer clears the safety block when an untrusted or unremovable file remains.

### New regression coverage

- Backgrounding during the prepared-before-record draft-write window calls recorder.stop before deleting the unstarted file, removes the segment from the draft and restores playback mode only after stop.
- An outside-cache recorder URI is never recorded, uploaded or deleted; it keeps the native voice UI blocked.
- Direct-cache-child cleanup succeeds for malformed filenames while nested/traversal/outside paths are rejected.
- Device-check tests assert the URI is retained before validation and that failed cleanup remains blocking.
- The existing 15-second chunk, transcript checkpoint, consent, duplicate-ASR and explicit “Muayeneyi bitir” tests remain intact.

### Commit set

`b8cc63a`, `2249ffa`, `dd5943a`, `a017e02`, `98b8a23`, `7f8e76f`, `442b95c`, `e6c3539`, `cf88e8f`, `90b35d2`, `0b74ab9`.

### Final-head verification boundary

Final HEAD: `0b74ab96044f77d06555f6c29570116a0b311fd8`.

- New Android run [#44992328767](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44992328767) is pending and has no job records at this check.
- New Security Recovery run [#44992328784](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44992328784) is pending and has no job records at this check.
- Therefore the new prepared-recorder and unexpected-URI regressions are committed but not yet reported as passing on final HEAD.
- The preceding Android run on `32a272c` proves the unchanged typecheck/beta/APK pipeline was healthy before this patch; it does not validate the new final-head code.

No physical Android/iOS Bluetooth, call/notification interruption or background-resume test was possible in this GitHub-only pass. No patient/audio payload, production API, R2 object, database migration, main merge, live deploy or store release was touched.
