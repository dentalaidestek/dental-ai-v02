# Native voice draft scope isolation — 2026-11-19

## Web-first comparison

Re-read `voice_exam_entry.html`, `voice-exam-live.js`, and `voice-pcm-worklet.js` before changing native code. The browser live path holds its current session in the page controller and streams PCM16 frames over the authenticated voice WebSocket. Native currently records bounded, app-private M4A segments, persists the transcript draft in the existing SecureStore-backed chunk store, and sends each segment through the existing owner-scoped ASR receipt endpoint. This change does not claim PCM16/WebSocket parity and does not introduce a speculative native audio encoder.

## Newly reproduced lifecycle risk

`NativeVoiceRecorder` used one shared `mounted.current` boolean to guard asynchronous draft restoration. On an owner/patient change, React can run the old effect cleanup (setting the boolean false) and then the new effect setup (setting it true) before the old SecureStore read or cache-file inspection resolves. The stale operation then sees `mounted.current === true` and could publish the previous patient's transcript into the newly reused component, call the new transcript callback, or mutate shared draft state.

## Changes

- Added `mobile/src/voiceDraftScope.ts`; the active in-memory scope is the existing owner+patient draft key. No token, transcript, patient name, or audio bytes are added to persistent storage.
- Each restore effect now owns a local active lease and rechecks it after SecureStore reads, cache-file reads, deletion, and cleanup awaits.
- A new owner/patient restore waits for the previous scope's pending ASR/recorder cleanup before reading its own draft.
- Old-scope recorder cleanup writes only to the captured old SecureStore key and cannot replace the active in-memory draft or view.
- `persist`, ASR drain, and transcribed-file cleanup reject stale-scope state updates. Late ASR responses cannot append transcript text to a different patient view.
- Added a delayed SecureStore-read account/patient-switch regression to `mobile/tests/voiceWorkflow.cjs`, plus a pure scope helper test in `mobile/tests/voiceDraftScope.cjs`.
- Registered the helper test in `npm run test:beta` and the manual Security Recovery native-voice job.

## Validation and limits

- Pure scope helper test: 5 assertions passed in an isolated Node 22.16 run.
- Standalone helper strict TypeScript check: passed.
- `voiceWorkflow.cjs` JavaScript syntax parse: passed.
- `mobile/package.json` JSON parse and beta registration: passed.
- GitHub source-contract checks: 16/16.
- The new delayed-read React Native renderer regression is committed but was not executed here; this connector runtime does not contain the mobile `node_modules` / React renderer checkout.
- Full `npm run typecheck`, `npm run test:beta`, Security Recovery, Expo export, Gradle APK, physical Android/iOS and PostgreSQL/60k mixed-load acceptance remain unrun.

The exact native raw-PCM16 capture gap remains open: the current Expo Audio recorder integration exposes M4A files, not the browser AudioWorklet's raw PCM frame callback. No unsupported conversion, new native dependency, provider call, endpoint, schema, polling, migration, main merge, or live deploy was added.
