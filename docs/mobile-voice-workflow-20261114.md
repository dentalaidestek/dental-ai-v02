# Native microphone, voice draft recovery and clinician approval

Continues PR #257 / issue #258, based on `06824a52`. No main merge, production deploy or store publication. Existing clinical providers, closed concept/source workflow and finish-only clinical evaluation remain unchanged.

## Confirmed missing behavior

`VoiceExamEntry` explicitly said the native microphone was not connected. It provided only a temporary text field and a web handoff. The mobile transcription endpoint and Expo Audio dependency/permissions already existed, but nothing on the screen recorded or uploaded audio. The existing native extraction/final review also had no native path to the web's revision-checked, idempotent clinician approval handler.

The implementation connects those existing capabilities rather than inventing another clinical engine or automatically writing AI output to records.

## Web-to-native mapping

| Stage | Native behavior |
|---|---|
| Patient | Existing shared, searchable, paginated real-patient selector; an explicit profile patient is verified through the patient API |
| Consent / microphone | Explicit consent, runtime microphone permission, AAC/MP4 recording through the installed Expo Audio module |
| Live listening | Roughly 15-second audio pieces are transcribed sequentially; returned speech is appended to the visible transcript. This is chunk transcription, not a promise of word-by-word latency |
| Pause / resume | Finish the current piece, preserve it and continue with a new piece; max-five queued pieces applies backpressure |
| Background / interruption | Stop foreground recording, retain pending audio references and show recovery; platform interrupts and unexpected recording stops are surfaced |
| Finish | Stop recording, drain pending ASR pieces and only then trigger the existing clinical extraction; ASR failure prevents clinical handoff |
| Manual note | Explicit finish-and-analyze action; disabled while an audio session is unfinished or has pending pieces |
| Clinical review | Existing editable fields, removable findings/coaching, closed-concept finalization, verified-source output and expandable sections retained |
| Clinician approval | Nothing selected by default; explicit chosen fields/teeth and confirmation; optional clinician-selected appointment date/time |
| Persistence | Canonical web apply handler owns patient/tooth/appointment transaction, revision conflict checks, duplicate receipt and realtime notifications |

## Native/runtime fixes verified from source

- The installed iOS Expo Audio recorder reuses its AVAudioRecorder URL when prepare receives no new options. Each chunk now passes explicit recording options so iOS creates a fresh file, matching Android's new-file behavior. The regression mock rejects preparation without those options.
- ASR failure while the next chunk was already recording could otherwise leave the microphone running after the rotation flag stopped. Failure now serializes a cut and preserves the current piece as well.
- Native upload cancellation alone may never settle a platform promise. A separate deadline rejection bounds the wait even if the native upload never resolves.
- Manual clinical evaluation cannot bypass an unfinished audio session. Live transcript events never call clinical extraction; the finish handoff does.

## Privacy and recovery

Text, pending-file references and clinical apply intent use SecureStore-backed chunked storage scoped by user and patient. No bearer token, raw audio or transcript is added to logs. The generic chunked store keeps its default social limit; voice may use up to 300 bounded encrypted chunks so the existing 72,000-character manual-text envelope is not published as an unreadable manifest. Clinical extraction still has the existing 18,000-character backend limit; longer text is not silently truncated or submitted as a complete examination.

Pending AAC audio stays in the application's private recording/cache area. It is **not additionally encrypted by this implementation**. Successful transcription publishes the updated secure draft before deleting the completed audio piece. Pending clips are not deleted on ASR errors. Expired drafts are cleaned when that user/patient examination is reopened after 24 hours; this is not a guaranteed background deletion timer. An explicit delete action works even after consent is withdrawn. A killed process can leave an unfinished/unplayable recording or orphan cache file; OS cache retention and device encryption are not certified here.

A clinical save intent is stored before the request. Unknown responses retry the same exact request key/payload, including after reopening; they do not generate a new key for the same uncertain save. The web's existing VOICE_REVIEW WorkJob dedupe transaction prevents a second patient/analysis write. Corrupt or wrong-account approval intent blocks new writes. Definite validation failures allow correction; changed patient revisions require fresh clinician review. Saved history records only explicitly approved clinical fields, not the full conversation.

## Verification

TypeScript and **253 Node tests passed, 0 failed** (18 session, 46 realtime, 189 beta), including 13 new voice workflow cases. Selected Python suite: **212 passed, 0 failed** (361 warnings). Bare Python suite: **265 passed, 7 failed, 5 skipped** (573 warnings); browser/environment failures are listed below. Commit, fresh JS export and remote CI state are recorded in PR #257 / issue #258.

- Native regressions exercise draft account/patient binding and expiry, exactly-once local segment append, binary upload headers/consent, microphone start/pause/resume/finish, retained failed audio, live-rotation failure stopping the next recording, clinical finish-only handoff, encrypted large-text round trip, approval field selection/exact-intent retry, restored text, explicit appointment controls, bounded native upload timeout and unreadable-intent write blocking.
- Four real backend cases exercise consent/owner/revision/FDI/idempotency, ASR transcription-only without patient writes, and approved appointment/atomic conflict behavior. Provider ASR itself is mocked; canonical handler/database/security code executes.
- Full configured Node/typecheck suite and selected Python boot/account/program/patient/media/chat/request/admin/security/social suites run.
- Bare Python suite also runs. The seven existing web-browser launch failures remain separately reported: six Chromium socket-permission failures and the following-feed browser case expecting missing `/tmp/chromium`. PostgreSQL cases lack the configured test database and skip. No test was deleted or weakened to hide a failure.
- Android/iOS Expo-Hermes exports are checked. Expo Audio was already installed and configured; no new package/native dependency was added.

## Remaining acceptance and scope

No actual Android microphone/iOS recorder/earpiece/Bluetooth/noise/background/permission-denial or Turkish provider quality test. No signed APK/IPA produced; adb/Android emulator was not available in the inspected workspace. No authenticated production save, actual mail/push or PostgreSQL concurrency/load certification. Extraction/final results before approval are recomputed from the restored text; they are not durable server jobs. Pending audio/private-cache encryption, hard process death and retention need device/security acceptance.

New apply adapter is not deployed. Source changes do not update the installed APK. Native voice source wiring does not certify the entire app or every voice acceptance criterion. Clinical image AI result/review parity, full Academic AI and remaining expert/product work stay in `mobile-web-parity-tracker-20261114.md`, together with P0 CI/API/session/device gates and all original clinical/privacy decisions.


## Web entry parity added after source comparison

The web entry page also offers **Yeni hastayla başla** before the existing-patient search. The earlier native entry exposed only NativePatientSelect, so it could not complete this first web action. The native flow now calls an authenticated mobile endpoint that creates the same empty, owner-scoped SES-… patient record and emits the existing patient-created realtime event. It then opens the recorder for that patient.

The native request key is generated once and kept in SecureStore until a valid receipt is returned. A lost response retries the same key; the backend derives a stable per-account anonymous ID and serializes creation on the owner row in PostgreSQL, so the retry resolves to the same patient. The response is private/no-store and contains only the minimal patient payload. The new path does not accept patient fields, does not invoke ASR or clinical inference, and does not write clinical data. Existing-patient selection remains unchanged.

Regression coverage was added for authenticated ownership, account separation, private response headers, retry identity, invalid request keys, native request shape, and the screen's retry-to-recorder transition. These tests are committed but await a runner that actually starts the workflow; no production device or backend acceptance is claimed.
