# Native microphone preflight cleanup verification — 2026-11-19

## Web-first comparison

Before changing native behavior, re-read:
- app/templates/voice_exam_device_check.html
- app/static/voice-device-check.js
- app/static/voice-pcm-worklet.js
- mobile/src/NativeVoiceDeviceCheck.tsx
- mobile/src/voiceDeviceCheck.ts

The web preflight processes six seconds of PCM16 frames in the AudioWorklet and stops the media tracks; it does not create a local audio file. Native Expo Audio needs a temporary app-cache M4A file to verify capture. The native cleanup helper previously swallowed delete errors, did not read the file back after deletion, and cleared the only in-memory URI regardless. The UI could therefore show the ordinary result even when deletion had not been confirmed.

## Changes

- Added an exact app-cache URI validator: only one safe M4A filename directly beneath the configured file:// cache root is accepted. Prefix siblings, nested paths, traversal and non-file paths are rejected.
- Native cleanup now checks file existence before deletion, calls idempotent deletion, and checks existence again. It returns success only when the file is absent.
- The URI is retained until deletion is verified. A failed or untrusted cleanup cannot be classified as a successful microphone check.
- Added a visible retry action for a cleanup-pending file. A new microphone test is blocked until cleanup succeeds, so a later test cannot overwrite the only reference to the previous file.
- Start failures and user/background/screen cancellation use the same verified cleanup path.
- No audio, transcript, patient ID, user ID, token or device-check file is uploaded or persisted in SecureStore.

## Regression coverage

- Exact direct-cache M4A path accepted.
- Cache-prefix sibling, traversal, nested path and non-file path rejected.
- cleanupVerified=false always classifies as cleanup_failed, even when capture duration, file size and meter otherwise pass.
- UI source contract checks post-delete existence verification, URI retention, retry UI and strict recorder-path validation.
- Existing privacy checks continue to prohibit API/network and persistent-storage use in the preflight component.

Tests are committed and already registered in npm run test:beta. The helper test and renderer/source test were not executed in this connector-only run. Full typecheck, beta suite, Android/iOS build and physical-device deletion-failure simulation remain open.

No patient data, production configuration, schema or provider behavior changed. No workflow was dispatched, no main merge and no live deploy.