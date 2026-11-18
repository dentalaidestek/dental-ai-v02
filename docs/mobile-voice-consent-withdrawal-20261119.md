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

## Regression coverage added

- Native recording opt-out stops capture and retains the private segment without ASR.
- Native opt-out during an ASR request aborts the request and retains the same local segment.
- Browser live opt-out sends pause, retains finalized text, and never marks the examination finished.
- Browser UI keeps consent withdrawable while live capture is active.

The regression tests were added to the existing test files but were not executed in this run. The repository's relevant GitHub workflows remain manual-only because previous hosted jobs failed before step 1 (runner ID 0, empty step arrays, and unavailable job-log blobs). No green CI result is claimed.

## Remaining acceptance

- Execute `npm run typecheck`, `npm run test:beta`, and the browser voice regression when hosted runner allocation is healthy.
- Verify Android/iOS behavior on physical devices, including Bluetooth route changes, app backgrounding, and OS microphone interruption.
- Verify the web file-recorder opt-out path in a real browser; its held blob is intentionally page-memory-only and is not a restart-recovery artifact.
