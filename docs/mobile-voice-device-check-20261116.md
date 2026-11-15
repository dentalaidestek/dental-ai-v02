# Native microphone device check — 2026-11-16

## Web reference inspected first

Compared `app/templates/voice_exam_entry.html`, `app/templates/voice_exam_device_check.html`, `app/static/voice-device-check.js` and `app/static/voice-pcm-worklet.js` with `mobile/src/VoiceExamEntry.tsx`, `mobile/src/NativeVoiceRecorder.tsx`, `mobile/app.json` and the Expo Audio 1.1.1 API used by this app.

The web entry exposes a separate six-second device check. It requests microphone access only after an explicit tap, displays live level, stops on background/navigation, and does not send audio or start clinical extraction. The native entry previously had only the clinical recorder, so users could not check the microphone before starting an examination.

## Native adaptation

- Adds `NativeVoiceDeviceCheck` before the clinical consent/recording controls.
- Uses Expo Audio's native permission request and metering support; the existing app configuration already declares the Android/iOS microphone rationale and does not request shared media-library audio permission.
- Captures for six seconds only after the user taps the button.
- Writes only a temporary recording under the app-private cache directory because Expo Audio's recorder API is file-based. It is never uploaded, transcribed, placed in a patient draft, or passed to an AI provider. The file is deleted immediately after stop/cancel/error/background/blur/unmount.
- Restores the audio mode after cleanup.
- Uses explicit outcomes for permission denied, incomplete capture, empty file, unavailable metering, low signal and a measurable signal. Missing metering is inconclusive, never a pass.
- Cancels when the app leaves the foreground or the screen loses focus. The native check's busy state blocks navigation and clinical edits/recording while it runs.
- No patient ID, user ID, session token, transcript, or API client is passed to the component.

## Deliberate native/web difference

The browser page runs its PCM16 AudioWorklet in memory. Expo Audio 1.1.1 exposes recorder metering but not the same public native PCM worklet surface through this app's current API. The native check therefore verifies local capture + meter + non-empty temporary file, not PCM16 conversion. A successful check does not certify Gemini connectivity, ASR accuracy, Bluetooth routing or clinical suitability. A real Android and iOS device check remains mandatory.

## Regression coverage

- `mobile/tests/voiceDeviceCheck.cjs`: six-second window, permission denial, short/empty capture, unavailable meter, quiet signal, threshold and bounded meter.
- `mobile/tests/voiceDeviceCheckUI.cjs`: cache-only temporary file, deletion, no network/transcription/identity payload, background/blur cleanup, and entry integration.
- Both tests are added to `npm run test:beta`.
- Existing `mobile/tests/voicePermissions.cjs` continues to assert the native microphone permission configuration.

These tests are committed but have not been executed in this environment. Do not treat the feature as device-accepted.

## CI evidence at the starting head

Starting branch/PR head was `5e2824b33a05ad4e80a53fcbda98ee6fd103dac8`. The latest associated runs before this work were Android #2104 (run 43767959675; `typecheck` and `beta-apk`), security recovery #859 (43767959667), admin security #743 (43767959674) and expert social #739 (43767959663). Every returned job had an empty step list; `fetch_workflow_job_steps` returned `[]`; all five job-log downloads returned Azure `BlobNotFound 404`; all four artifact lists were empty. Therefore npm/tsc, Gradle, pytest and security regressions did not run. The available records identify a pre-step Actions job/runner allocation failure, not a source-level TypeScript or pytest diagnostic. The exact GitHub-hosted runner/account/billing cause is not exposed by the available API. Do not change `runs-on` speculatively; repository owner must inspect Actions availability and billing.

No main merge, production deploy, account/patient mutation, or store publication was performed.
