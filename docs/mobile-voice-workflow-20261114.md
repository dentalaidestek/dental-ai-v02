# Native microphone, voice draft recovery and clinician approval

Continues PR #257 / issue #258, based on `06824a52`. No main merge, production deploy or store publication. Existing clinical providers, closed concept/source workflow and finish-only clinical evaluation remain unchanged.

## Confirmed missing behavior

This was the initial gap when the native recorder and approval path were introduced. The native microphone, local audio recovery and canonical approval adapter are now present. A further source comparison found that the web accepts a 72,000-character / 216 KB examination and extracts it in 12,000-character chunks, while native draft append and extraction stopped at one 18,000-character request. That limit prevented long examinations from reaching the same final review.

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
| Clinical extraction | Full transcript is split into <=12,000-character / <=36 KB requests; prior structured extraction is passed as bounded context and each completed chunk is checkpointed |\n| Clinical review | Existing editable fields, removable findings/coaching, closed-concept finalization, verified-source output and expandable sections retained |
| Clinician approval | Nothing selected by default; explicit chosen fields/teeth and confirmation; optional clinician-selected appointment date/time |
| Persistence | Canonical web apply handler owns patient/tooth/appointment transaction, revision conflict checks, duplicate receipt and realtime notifications |

## Native/runtime fixes verified from source

- The installed iOS Expo Audio recorder reuses its AVAudioRecorder URL when prepare receives no new options. Each chunk now passes explicit recording options so iOS creates a fresh file, matching Android's new-file behavior. The regression mock rejects preparation without those options.
- ASR failure while the next chunk was already recording could otherwise leave the microphone running after the rotation flag stopped. Failure now serializes a cut and preserves the current piece as well.
- Native upload cancellation alone may never settle a platform promise. A separate deadline rejection bounds the wait even if the native upload never resolves.
- Manual clinical evaluation cannot bypass an unfinished audio session. Live transcript events never call clinical extraction; the finish handoff does.

## Privacy and recovery

Text, pending-file references, extraction checkpoints and clinical apply intent use SecureStore-backed chunked storage scoped by user and patient. No bearer token, raw audio or transcript is added to logs. The generic chunked store keeps its default social limit; voice uses a bounded 512-chunk ceiling. The backend still accepts at most 18,000 characters per extraction request, so native now mirrors the web FinishDraft contract: up to 72,000 characters / 216 KB are split into sequential 12,000-character / 36 KB chunks. Each successful response is saved with its cursor, revision and cumulative structured review; the next request carries only the canonical bounded fields/teeth/appointment/source context accepted by `clinical_context`. Communication and decision-barrier insights are deduplicated and merged across chunks (with the web 24-item ceiling and fail-closed clinical-statement rule), follow-up questions are deduplicated while preserving a clinician's resolved state, and uncertainty notes retain the latest eight. A retry resumes after the last saved chunk instead of re-sending completed chunks. Checkpoints are rejected when account, patient, transcript SHA-256, cursor, revision or 24-hour expiry does not match. A patient-revision conflict explicitly clears the old checkpoint before re-extraction; if secure deletion is temporarily unavailable, an in-memory force-fresh flag prevents the stale checkpoint from being loaded on the next retry. Final clinical synthesis still receives the complete transcript under the existing 72,000-character conversation limit.

Pending AAC audio stays in the application's private recording/cache area. It is **not additionally encrypted by this implementation**. Successful transcription publishes the updated secure draft before deleting the completed audio piece. Pending clips are not deleted on ASR errors. Expired drafts are cleaned when that user/patient examination is reopened after 24 hours; this is not a guaranteed background deletion timer. An explicit delete action works even after consent is withdrawn. A killed process can leave an unfinished/unplayable recording or orphan cache file; OS cache retention and device encryption are not certified here.

A clinical save intent is stored before the request. Unknown responses retry the same exact request key/payload, including after reopening; they do not generate a new key for the same uncertain save. The web's existing VOICE_REVIEW WorkJob dedupe transaction prevents a second patient/analysis write. Corrupt or wrong-account approval intent blocks new writes. Definite validation failures allow correction; changed patient revisions require fresh clinician review. Saved history records only explicitly approved clinical fields, not the full conversation.

## Verification

Historical verification from the earlier native-recorder commit: TypeScript and **253 Node tests passed, 0 failed** (18 session, 46 realtime, 189 beta), selected Python **212 passed, 0 failed**, and bare Python **265 passed, 7 failed, 5 skipped**. Those counts do not include the long-transcript changes below and must not be treated as current verification. The new chunking/checkpoint tests are committed but have not run in this runtime; current Android typecheck and security CI remain blocked before their first step.

- Native regressions exercise draft account/patient binding and expiry, exactly-once local segment append, binary upload headers/consent, microphone start/pause/resume/finish, retained failed audio, live-rotation failure stopping the next recording, clinical finish-only handoff, encrypted large-text round trip, approval field selection/exact-intent retry, restored text, explicit appointment controls, bounded native upload timeout and unreadable-intent write blocking.
- Four real backend cases exercise consent/owner/revision/FDI/idempotency, ASR transcription-only without patient writes, and approved appointment/atomic conflict behavior. Provider ASR itself is mocked; canonical handler/database/security code executes.
- Full configured Node/typecheck suite and selected Python boot/account/program/patient/media/chat/request/admin/security/social suites run.
- Bare Python suite also runs. The seven existing web-browser launch failures remain separately reported: six Chromium socket-permission failures and the following-feed browser case expecting missing `/tmp/chromium`. PostgreSQL cases lack the configured test database and skip. No test was deleted or weakened to hide a failure.
- Android/iOS Expo-Hermes exports are checked. Expo Audio was already installed and configured; no new package/native dependency was added.

## Remaining acceptance and scope

No actual Android microphone/iOS recorder/earpiece/Bluetooth/noise/background/permission-denial or Turkish provider quality test. No signed APK/IPA produced; adb/Android emulator was not available in the inspected workspace. No authenticated production save, actual mail/push or PostgreSQL concurrency/load certification. The transcript and per-chunk extraction checkpoint are locally recoverable in SecureStore; the final source evaluation and approval intent are not a durable server job until the existing canonical workflow is invoked. Pending audio/private-cache encryption, hard process death and retention need device/security acceptance.

New apply adapter is not deployed. Source changes do not update the installed APK. Native voice source wiring does not certify the entire app or every voice acceptance criterion. Clinical image AI result/review parity, full Academic AI and remaining expert/product work stay in `mobile-web-parity-tracker-20261114.md`, together with P0 CI/API/session/device gates and all original clinical/privacy decisions.


## Web entry parity added after source comparison

The web entry page also offers **Yeni hastayla başla** before the existing-patient search. The earlier native entry exposed only NativePatientSelect, so it could not complete this first web action. The native flow now calls an authenticated mobile endpoint that creates the same empty, owner-scoped SES-… patient record and emits the existing patient-created realtime event. It then opens the recorder for that patient.

The native request key is generated once and kept in SecureStore until a valid receipt is returned. A lost response retries the same key; the backend derives a stable per-account anonymous ID and serializes creation on the owner row in PostgreSQL, so the retry resolves to the same patient. The response is private/no-store and contains only the minimal patient payload. The new path does not accept patient fields, does not invoke ASR or clinical inference, and does not write clinical data. Existing-patient selection remains unchanged.

Regression coverage was added for authenticated ownership, account separation, private response headers, retry identity, invalid request keys, native request shape, and the screen's retry-to-recorder transition. These tests are committed but await a runner that actually starts the workflow; no production device or backend acceptance is claimed.


## Long-examination parity — 2026-11-15

Compared the web `VoiceFinishDraft.splitTranscript` / `finishTranscript` path with `voiceSession.ts`, `voiceApi.ts` and `VoiceExamEntry.tsx`. Native previously stopped at 18,000 characters even though its text field and finalizer allowed 72,000. This could leave a long appointment with a complete local transcript but no complete clinical extraction.

Native now uses the same 72,000-character / 216 KB envelope and Unicode-safe 12,000-character / 36 KB request chunks. Extraction requests are sequential and carry the prior structured review through the same bounded context contract used by the web handler. A SecureStore-backed checkpoint stores only the transcript hash, account/patient scope, completed cursor, server revision and structured extraction. Retry skips already completed chunks. A mismatch, expiry or invalid checkpoint is discarded; a revision conflict uses a fresh extraction rather than replaying a stale completed checkpoint. The full transcript remains available for the existing single final synthesis. No provider, prompt, taxonomy, backend clinical rule, or automatic patient write was changed.

Commits: `9a33661` transcript/chunker/checkpoint contract; `f62405e` sequential extraction and context carry-forward; `49c4a86` encrypted checkpoint integration and progress; `1936a42` chunk/resume/security regressions; `dc10098` Unicode/limit fixture correction; `10fcdf9` UI limit alignment; `40a9cd5` revision-conflict restart. Pure helper TypeScript compile and isolated Node chunk/resume checks passed in the available scratch runtime; the repository's full `npm test`, Android/iOS export and Python suites remain unexecuted here. No physical microphone/provider/device acceptance is claimed.

Latest PR-head CI (127af68): Android #2030, recovery #824, admin #708 and expert-social #704 have runner_id=0, empty runner_name and zero steps; logs return BlobNotFound. This remains an Actions runner-allocation blocker, not a reported source test result.


## Web parity correction — cumulative recording duration (2026-11-16)

Compared the web live timer in `app/static/voice-exam-live.js` with `NativeVoiceRecorder`. The web timer carries elapsed time across pause/resume. Native previously displayed Expo Audio's `durationMillis` for the current recording file, but native recording rotates to a fresh file every 15 seconds; the visible timer could therefore restart at each chunk instead of showing the whole examination.

Native `VoiceDraft` now persists `elapsedMs`. The recorder renders a cumulative `MM:SS` timer, adds a chunk's elapsed interval only after the recorder stop succeeds, and restores the accumulated duration when the same account/patient draft is reopened. Older version-1 drafts without `elapsedMs` remain readable and default to zero. This is local session metadata only; it does not alter transcript, ASR, clinical extraction, approval or patient records.

If the OS kills the process before the active chunk can be stopped/cleaned up, the pending audio reference remains subject to the existing recovery behavior, while that incomplete chunk's duration is not guessed. Completed chunks' elapsed duration remains persisted.

Regression coverage was added for multi-chunk/pause accumulation, `MM:SS` formatting, legacy draft migration, invalid duration rejection, component-level pause/resume and restored display. These tests are committed but have not been executed in this runtime.
