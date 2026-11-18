# Native voice recorder rotation and compact session parity — 18 Nov 2026

## Web-first review

Before changing native code, re-read the web session flow on the target branch:

- `app/templates/voice_exam_entry.html`
- `app/templates/voice_exam_session.html`
- `app/templates/voice_exam_panel.html`
- `app/static/voice-exam.css`
- `app/static/voice-exam-live.js`
- `app/static/voice-pcm-worklet.js`
- `app/voice_exam_live.py`
- `app/mobile_api.py::mobile_voice_audio`

The web live path keeps a single microphone session open and streams bounded 100 ms mono PCM16/16 kHz frames through the authenticated WebSocket. The native path intentionally remains Expo Audio 1.1.1 local 15-second M4A segments, then uploads each segment through the existing owner-scoped, consent-gated, encrypted ASR receipt endpoint. No new provider, endpoint, prompt, or raw-audio persistence path was added. Native live PCM16/interim-transcript parity remains a separate acceptance gap because the recorder API used here exposes files and metering, not AudioWorklet frames.

## New functional defect

The native recorder tracks whether Expo Audio was previously recording. During a normal 15-second rotation, `cut()` stops the old segment, checks the file, and persists its ready state before `rotate()` starts the next segment. The status hook can publish `isRecording=false` during that interval. The old implementation still had `wasRecording=true`, `wanted=true`, and an active segment, so it classified the expected stop/start gap as an unexpected microphone interruption. Its background-pause path then cleared the recording intent and prevented the next segment from starting. This can present as the microphone stopping at a chunk boundary even though the user did not pause.

## Changes

- Added a small pure lifecycle classifier that distinguishes an unexpected stop from a transition owned by the recorder.
- Clear the previous-recording marker before calling `recorder.stop()`; a false status from that expected stop can no longer be mistaken for an interruption, including when file inspection or SecureStore persistence takes longer than one status poll.
- Keep the existing unexpected-stop behavior outside the owned transition: recording intent is stopped, the current segment is retained, and no clinical handoff is triggered.
- Added regression cases for normal rotation, a genuine unexpected stop, clinician pause, and stale status without an active segment.
- Aligned the native session's first-use layout with the web state contract: microphone/timer/level affordances are hidden before the first recording; the microphone focal point is reduced from 94 px to 76 px; live level and waveform appear only while recording; primary actions are full-width and vertically ordered.

## Files changed

- `mobile/src/voiceRecorderLifecycle.ts`
- `mobile/src/NativeVoiceRecorder.tsx`
- `mobile/tests/voiceWorkflow.cjs`

The existing `npm run test:beta` already includes `tests/voiceWorkflow.cjs`; no duplicate workflow or dependency was added.

## Validation boundary

- The regression test source now exercises the pure lifecycle classifier and checks that the recorder clears the previous marker before stopping and uses the classifier for unexpected-stop handling.
- The visual contract regression checks first-use hiding, compact microphone sizing, recording-only metering, and vertically stacked actions.
- The dependency-free helper passed strict TypeScript compilation with `tsc --strict --noEmit --target ES2020 --module commonjs`.
- Four isolated Node tests passed (4/4): expected rotation, genuine unexpected stop, clinician pause, and stale status without an active segment. These tests exercise the helper logic, not the complete React component.
- GitHub source-contract checks passed 15/15 for lifecycle integration, first-use/recording-only UI states, compact layout, regression registration, and the documented PCM16 limitation.
- Full `npm run typecheck`, `npm run test:beta`, Expo export, Gradle/APK, Python security regressions, PostgreSQL concurrency, and physical Android/iOS microphone/rotation tests have not been run in this environment. Do not treat committed test coverage as an executed test pass.

## CI diagnosis at the start of this work

The branch started at `b9f5d79` with no combined status checks. The latest available older runs included Android APK run `44273348890` and Security Recovery run `44257062507`; their jobs had `runner_id=0`, `runner_group_id=0`, an empty runner name, standard `ubuntu-latest` labels, and zero steps. The Android job ran for roughly two seconds. Log downloads returned Azure `BlobNotFound 404`; the security job records showed the same pre-step failure. Therefore npm/tsc, Node tests, Gradle and pytest did not start. This is a GitHub Actions runner/log allocation failure, not evidence of a TypeScript or security-test assertion failure. The exact hosted-runner/account/billing cause is not exposed by the repository API and cannot be repaired with an application source change.

The branch had a burst of repeated Android APK push runs (run numbers 801–823 in the retrieved recent history). The current Android, Security Recovery, Voice and Mobile Android workflow files are manual-only, preventing another automatic run burst while runner availability remains unresolved. No workflow was dispatched in this work.

## Safety and release

No transcript, audio file, patient record, or production data was read or changed. No provider call, database migration, main merge, production deploy, APK/IPA publication, or store release was performed. PR #257 remains draft.
