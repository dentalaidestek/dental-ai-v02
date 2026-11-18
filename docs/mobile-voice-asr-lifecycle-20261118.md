# Native voice ASR lifecycle cancellation — 2026-11-18

## Web-first comparison

The web session template includes `voice_exam_panel.html`. Its live path is `voice-exam-live.js` plus `voice-pcm-worklet.js`: the browser AudioWorklet converts mono input to signed PCM16 at 16 kHz in bounded 100 ms frames and sends those frames to `/patients/{patient_id}/voice-exam/live`. The backend proxy checks same-origin, authenticated patient ownership and explicit consent; it bounds session duration, frame size/rate and provider message size. The current web live proxy also has a four-session global cap and one active session per user.

The native path intentionally differs today. Expo Audio 1.1.1 records app-private `.m4a` chunks, normally 15 seconds each. The client persists a per-account/per-patient draft in the secure chunked store and uploads each bounded file to `/api/mobile/v1/patients/{patient_id}/voice-exam/audio` with a stable segment request key. The backend validates ownership, consent and audio size and stores an idempotent ASR receipt. Native extraction and final clinical review remain separate; only explicitly selected and clinician-confirmed fields can be applied to the patient record.

The current Expo Audio recorder interface used by this screen does not expose the browser AudioWorklet's PCM16 frame stream. This change does not pretend that file-based native ASR is WebSocket live-audio parity, and does not add a new native audio module or provider path.

## Root cause found

The recorder's AppState and navigation-blur handlers previously called `pause(true)` only when `wanted.current` was true. That flag is false after the clinician pauses recording, while the queued segment may still be uploading in `drain()`. Consequently, backgrounding the app or leaving the screen during that ASR request did not abort the transfer. The upload could continue after the recording UI was no longer active.

## Change

- Any non-active AppState transition now aborts the in-flight ASR request, whether or not microphone recording is currently active.
- Losing navigation focus also aborts the in-flight request, including during a paused-session upload.
- `pause(true)` independently aborts a pending transfer so other background-pause callers keep the same privacy rule.
- The local audio file and its original segment request key are retained when an upload is aborted. No transcript is appended and no clinical finalization is triggered by cancellation.
- When the clinician returns and explicitly retries, the same request key is reused. If the server already completed ASR before the client lost the response, the server receipt replay avoids an extra provider call. No automatic background retry was added.

## Regression coverage added

`mobile/tests/voiceWorkflow.cjs` now models AppState transitions and includes two component-level scenarios:
1. Backgrounding during a paused-session ASR upload aborts the signal, retains the segment and transcript, then retries the same key after foregrounding.
2. Leaving the voice screen during a paused-session ASR upload does the same on blur and preserves the key when the screen is revisited.

The file is already included by `mobile/package.json` in `npm run test:beta`.

## Validation and limitations

- GitHub source-contract checks: 8/8 assertions for both lifecycle abort paths, the AppState test harness, both regression scenarios, same-key retry and beta-suite inclusion.
- The Node component tests, full `npm run test:beta`, `npm run typecheck`, pytest, Expo export and device tests were not executed in this run.
- At starting HEAD `eb9d066ae606e577a27e02d00da493bca48372d8`, combined status was empty and the PR-triggered workflow-run lookup returned no runs. The connected GitHub tools expose run inspection/retry but no workflow-dispatch action. A local checkout could not be cloned because this runtime could not resolve github.com. Therefore no green CI or runtime test result is claimed.
- The web PCM16 WebSocket and native chunked `.m4a` ASR paths remain different. Physical Android/iOS interruption tests and a supported native PCM streaming API are still open.

No patient data was read or changed. No schema migration, provider/prompt change, main merge, production deploy or APK/IPA publication was performed.
