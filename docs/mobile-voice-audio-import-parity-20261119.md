# Native voice audio-file import parity

Date: 2026-11-19

## Web contract reviewed

The web voice-exam panel and `voice-exam.js` accept one audio file for transcription-only input. The browser checks a supported audio MIME, a non-empty file, an 8 MiB maximum and a 90.5-second duration ceiling before sending the file. The user can append the resulting transcript to the active examination; clinical extraction remains a separate action initiated by **Muayeneyi bitir**.

The native implementation now follows that flow without routing imported audio through the clinical-extraction endpoint.

## Native flow

1. `expo-document-picker` opens the system document picker for MP3, WAV, WebM, OGG and MP4/M4A audio.
2. The picker uses `copyToCacheDirectory: true`; the app checks the source size, then copies the file to a generated direct child of the app cache: `voice-import-<UUID>.<extension>`.
3. The temporary picker cache copy is removed after the private copy is verified, and is also removed on validation failure when it is inside the app cache. A provider URI outside the app cache is never deleted.
4. MIME and extension must agree. The app checks the copied file size (100 bytes through 8 MiB) and reads duration metadata with `expo-audio` without playing the clip. Duration must be positive and at most 90.5 seconds.
5. The segment, MIME, patient/account-scoped draft and stable request key (segment UUID) are saved through the existing encrypted chunked SecureStore draft.
6. `transcribeNativeRecording` sends the raw file to `/api/mobile/v1/patients/{patient_id}/voice-exam/audio` with bearer auth, consent and `X-Voice-Request-Key`. The server's owner-scoped encrypted receipt makes retries idempotent.
7. The transcript is persisted before the private audio is deleted. If transcription or deletion fails, the local draft and source file remain recoverable. A new key is only created after the existing explicit warning/confirmation flow.
8. The imported transcript is appended to the examination. It does not trigger clinical extraction or write anything to the patient record; the existing finish/final-review and clinician-approval steps remain unchanged.

## Privacy and resource boundaries

- No new microphone, media-library or broad storage permission is requested; selection is delegated to the platform document picker.
- Imported files are copied into the app's private cache and never uploaded from arbitrary provider paths.
- MIME is sent as the canonical supported type and the server validates the file signature and 8 MiB body limit.
- The server route is transcription-only and uses the encrypted owner/patient/request-key receipt. Raw audio is not stored in the patient chart.
- Cache copies are removed only after the app has verified the corresponding path is inside its own cache.
- The duration check currently mirrors the web client and is performed on-device using audio metadata. The server validates MIME/signature and size but does **not** independently enforce the 90.5-second limit; a modified client can bypass the duration check. Server-side duration enforcement remains a separate hardening item.

## Regression coverage added

- `voiceAudioImport.cjs`: supported MIME/extension mapping, mismatch rejection, 100-byte/8-MiB bounds and 90.5-second duration boundary.
- `nativeVoiceAudio.cjs`: metadata-only duration read, player release, MIME-bound private paths, request-key upload and mismatch rejection.
- `voiceWorkflow.cjs`: imported segments in account-scoped drafts, picker/cache cleanup, transcript-only path and the existing explicit finish flow.
- `voiceApi.cjs`: the legacy Blob helper now requires and sends a stable request key; tests use a stable key and reject a missing one.
- The new pure helper test is included in `npm run test:beta` and the manual-only native voice security job.

## Verification status

The pure MIME/size/duration helper and a local mocked native-upload/duration harness were exercised in isolation. The complete repository `npm test`, Android `tsc --noEmit`, APK build and Python security suite have not been run in this automation. The GitHub workflows remain manual-only; no workflow was dispatched.
