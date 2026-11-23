# Native voice recorder — audio-mode recovery

Date: 2026-11-21  
Branch: `feature/mobile-web-parity-20261110`  
PR: #257 · Issue: #258

## Web-first trace

Before changing native behavior, the web examination flow was traced through:

- `app/static/voice-exam.js` — start/stop controls, transcript budget, consent and finish handoff.
- `app/static/voice-exam-live.js` — microphone stream lifecycle and live-session stop.
- `app/static/voice-finish-draft.js` — bounded final transcript handoff.

The web flow owns and closes its browser microphone stream. Native uses Expo Audio's app-wide audio mode (`allowsRecording`), so stopping an individual recorder is not sufficient: the app must also return to playback mode.

## Newly found native gap

The native recorder enabled `allowsRecording` before preparing a segment. During a 15-second rotation, `cut()` intentionally kept recording mode enabled because another segment was expected. If preparing that next segment then failed, the rotation catch set the recording intent to false but did not restore the global Expo Audio mode. A second gap existed on screen unmount: the active recorder was stopped and its private draft persisted, but the global mode was not reset.

This could leave the app in recording-oriented audio routing after the microphone was no longer active. It did not expose audio to another patient or upload additional data, but could affect later playback/routing and make the recording screen appear stopped while the app-wide audio mode remained stale.

## Changes

- Added `restoreVoiceAudioMode` to `mobile/src/voiceRecorderLifecycle.ts`. It returns an explicit boolean so a failed reset is not reported as success.
- Integrated a guarded restore into native stop, idle exit, rotation failure, start failure, pause/finish failure, ASR drain failure and component cleanup paths.
- A restore is attempted only after the recorder is known to be stopped; an active recorder is not switched to playback mode underneath an ongoing capture.
- When a foreground failure path cannot restore the mode, the screen shows a specific warning. Unmount cleanup performs a best-effort restore without writing patient/audio details to logs.
- The change does not add polling, network calls, database writes, new permissions or new patient-record behavior. Existing private-cache audio and consent/idempotency boundaries remain unchanged.

## Regression coverage

`mobile/tests/voiceWorkflow.cjs` now covers:

1. The helper reports successful restoration and returns false when the platform setter rejects.
2. A synthetic second-chunk preparation failure after a successful first recording restores `allowsRecording=false`.
3. Unmount after recording stops the recorder and restores the app playback route.

The existing voice workflow suite remains part of `npm run test:beta`.

## Acceptance still open

- GitHub Actions for the resulting branch HEAD must complete Android typecheck, beta regressions, Expo Android/iOS bundle export, APK build and Security Recovery.
- Physical Android and iOS checks are still required for speaker routing, Bluetooth, calls/notifications interrupting capture, background/foreground, and subsequent media playback.
- No real patient, microphone recording, production inference, main merge or live deployment was used for this change.
