# Native voice interrupted-recording recovery — 18 November 2026

## Web-first comparison

Re-read the web voice flow before editing: \`voice_exam_entry.html\`, \`voice_exam_panel.html\`, \`voice-exam-live.js\`, \`voice-pcm-worklet.js\`, and the native recorder/session implementation. The web PCM worklet sends bounded 100 ms PCM16 mono/16 kHz frames to the live WebSocket; the native Expo Audio path deliberately remains local 15-second M4A segments followed by the existing authenticated Gemini transcription endpoint. No provider, prompt, ASR endpoint, or clinical extraction order was changed.

## Defects found

1. A process interruption could leave a SecureStore segment with \`ready=false\`. The next app launch displayed a generic pending-audio message but exposed no action to transcribe or remove that segment, so the existing transcript could become stuck behind an unready file.
2. \`cut()\` cleared \`active.current\` before \`recorder.stop()\` and before the durable ready-state write. If stop or SecureStore persistence failed, the exact segment ID was lost from the live component and could not be retried.
3. The ASR transcript receipt used escaped backslash-n text instead of a real newline. Multi-segment transcript formatting was inconsistent with the normal append path.
4. Several renderer tests still searched for the previous recorder button labels, so they did not target the current native controls.

## Changes

- On restore, only a direct private-cache M4A is inspected. A missing file drops only its stale segment reference while preserving earlier transcript text. A present file is made uploadable only when it exists within the server's 100-byte–8-MiB contract. Unknown, missing-size, undersized, oversized, or unreadable files stay blocked.
- A clearly labelled per-segment discard action requires explicit confirmation and removes only that interrupted segment; it never removes already-transcribed cleanup receipts or earlier transcript text.
- The active segment ID is retained until recorder stop, file inspection, and SecureStore persistence complete. A failed stop can be retried against the same recording; a failed persistence can retry finalization without stopping the recorder twice.
- App blur/background/unmount attempts to stop and finalize the current segment. If that cannot be completed, the next launch reconciles the same durable intent from the private file.
- Transcript receipt separators now use actual newline characters.
- Renderer tests now use the actual Turkish native control labels and cover valid interrupted recovery, missing-file recovery, transcript preservation, and a failed-stop retry.
- Security Recovery's native voice job now runs both the private-audio path tests and the voice workflow renderer suite.

## Privacy and clinical boundaries

- The microphone still opens only after explicit consent and a user action.
- Audio remains in the app-private cache until the existing ASR request succeeds and cleanup is confirmed.
- No patient ID, transcript, audio URI, filename, or audio bytes are added to logs or push payloads.
- Clinical extraction/final evaluation still starts only after the clinician finishes the examination; approved fields still require explicit clinician selection.
- No patient chart is auto-written. No new AI call or polling loop was added.

## Verification boundary

The tests are committed but must be executed by GitHub Actions. At starting HEAD \`365ddb4740e88ca25728e562b1759245a6a5c8e4\`, Android typecheck job \`134532184679\`, Security job \`134532183748\`, and native voice job \`134532184250\` returned empty step arrays. The typecheck and Security job-log endpoints returned \`BlobNotFound 404\`; npm, TypeScript, pytest, and Gradle did not start. This proves a pre-step Actions execution/log allocation failure, not a source test result. The exact hosted-runner/account/billing cause is not exposed by these records.

Remaining parity gap: native still uses bounded M4A segments rather than the web's PCM16 live WebSocket/interim transcript. Expo Audio 1.1.1 does not expose the web AudioWorklet's PCM frame stream through the recorder API used here. This change does not claim live-stream parity or physical Android/iOS acceptance.
