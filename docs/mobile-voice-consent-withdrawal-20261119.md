# Voice consent withdrawal safety — 2026-11-19

## Web/native parity finding

The web consent checkbox was disabled while either the browser recorder or live WebSocket microphone was active. The native screen also disabled its consent control whenever `audioBusy` was true. This made withdrawal unavailable during the most privacy-sensitive part of the workflow.

The live browser controller did not subscribe to consent changes. The native recorder had no consent-change effect. A further native race existed when `finish()` had already acquired its operation gate: an opt-out during the cut phase could be followed by the existing drain call.

## Changes

- Web live PCM: unchecking consent stops the microphone, invalidates an in-progress connection, flushes already-finalized transcript text, and sends `pause` rather than `finish`. A pending finish is downgraded if consent is withdrawn before the server's end response. Clinical extraction is therefore not started by this path.
- Web file recording: unchecking consent stops MediaRecorder. The completed in-memory blob is held on the page and is not sent automatically; the user must restore consent and explicitly retry.
- Web controls: consent remains available while a microphone is active; start, retry, text transcription, and finalization require consent.
- Native: the consent checkbox remains available while recording or ASR is in progress. Opt-out aborts an active upload and pauses the recorder without draining the queue. The app-private clip and idempotency key remain available for an explicitly consented retry.
- Native race guard: a consent ref is checked by the ASR drain, pause, and finish paths so a stale callback cannot start a new upload or clinical handoff after opt-out.
- Browser script cache keys were bumped to `voice-exam.js?v=33` and `voice-exam-live.js?v=9`.

No provider, prompt, clinical taxonomy, database schema, patient record, or production configuration changed.

## Regression coverage

- Native recording opt-out stops capture and retains the private segment without ASR.
- Native opt-out during an ASR request aborts the request and retains the same local segment.
- Native opt-out while the finish gate is cutting the active clip prevents the subsequent ASR drain and clinical handoff.
- Native opt-out while the OS microphone permission prompt is pending prevents audio-mode activation and recorder startup.
- Native UI regression keeps the consent checkbox accessible while `audioBusy` is true and proves a stale finish callback cannot start extraction after withdrawal.
- Browser live opt-out sends pause, retains finalized text, and never marks the examination finished.
- Browser regression covers withdrawal after a Finish command is sent but before the server's final flush response; the client downgrades the result to paused and does not emit a finished examination.
- Browser UI keeps consent withdrawable while live capture is active.

The new regressions are committed to the existing native and browser test files. Final-head execution is pending; no green result is claimed for these newly added assertions until the workflow reruns.

## CI evidence at the start of this follow-up

- Android run [#44985026414](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44985026414) completed successfully: TypeScript typecheck, session/auth, realtime/pagination, beta regressions, Expo Android/iOS export, and internal APK assembly all passed.
- Security Recovery [#44985026330](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44985026330) executed the Python suite: 617 passed, 2 failed. The failures were a committed-analysis fixture whose object key used hard-coded analysis ID 42 instead of the generated row ID, and the active clinical media route registry assertion. Native clinical, voice, social, support, academic, and program security jobs passed. PostgreSQL and web duplicate-submission checks were skipped after the Python failures.
- The upload fixture now binds its object key to the actual generated Analysis ID. The route registry assertion now records the full mounted media-route inventory when it cannot find the canonical source symbol; this is diagnostic, not a claimed route fix.

## Remaining acceptance

- Rerun final-head Security Recovery and resolve the actual mounted media-route mismatch before claiming Python security green.
- Run the new native and browser consent regressions.
- Verify Android/iOS behavior on physical devices, including Bluetooth route changes, app backgrounding, and OS microphone interruption.
- Verify the web file-recorder opt-out path in a real browser; its held blob is intentionally page-memory-only and is not a restart-recovery artifact.
