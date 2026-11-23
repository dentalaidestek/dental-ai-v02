# Native voice clinical receipt throughput and crypto preflight — 2026-11-18

## Web flow checked first

The web reference remains `voice_exam_entry.html`, `voice_exam_session.html`,
`voice-exam.js`, `voice-exam-live.js`, `voice_exam.py` and
`voice_exam_core.py`. Web and native both keep transcription separate from
clinical extraction: the user finishes the examination before bounded clinical
text extraction begins. Neither path writes extracted values into the patient
record before explicit clinician approval.

## New findings

The native text endpoint already had an encrypted, owner/patient-scoped
`VOICE_CLINICAL_RECEIPT` with a 24-hour encrypted result TTL, a seven-day
tombstone window, input HMAC, PostgreSQL advisory lock, lease fencing and
terminal handling for indeterminate provider outcomes. The receipt tests cover
replay, changed input, owner/patient isolation, busy/unknown/expired states,
tampering, stale leases and deletion cleanup.

Two operational gaps remained:

1. `encryption_key()` validated the configured 32-byte key but did not check
   whether AES-GCM support was importable. The provider could therefore be
   called before receipt encryption failed. The endpoint would correctly avoid
   a second provider call, but the completed model result could not be recovered.
2. The async FastAPI text endpoint performed receipt reservation, completion
   and terminal-state SQLAlchemy transactions synchronously on the ASGI event
   loop. Under DB pool contention, those short synchronous operations could
   stall unrelated requests.

## Changes

- `encryption_key()` now resolves AES-GCM support before returning the key.
  Both native ASR and clinical extraction fail closed before provider work if
  encryption is unavailable.
- Added transaction adapters in `voice_clinical_receipts.py` for reserve,
  complete and finish operations. They own a short session/commit boundary.
- The native clinical text endpoint now runs every receipt DB transaction
  through Starlette's bounded threadpool. Provider inference was already
  offloaded and remains unchanged.
- The retry policy is unchanged: only typed failures known to occur before
  provider invocation (capacity/configuration) are retryable. Timeout,
  provider exception, stale lease, patient revision conflict or receipt
  persistence uncertainty remain terminal/unknown and cannot trigger a
  second provider call under the same request key.
- No transcript, context or review was added to plaintext WorkJob fields,
  application logs, or a new database table. No migration or provider/model
  change was made.

## Regression coverage added

`tests/test_mobile_voice_workflow.py` now also checks:

- AES-GCM unavailable: HTTP 503, no receipt row, no provider invocation.
- Successful native extraction: reserve and completion transactions are
  executed via `run_in_threadpool`.
- Typed pre-provider capacity rejection: terminal transition is offloaded,
  the same key can safely retry once, and the provider is called only for the
  successful retry.

These cases are included in the existing Security Recovery Python command via
`tests/test_mobile_voice_workflow.py`; the workflow remains manual-only while
the hosted runner problem is unresolved.

## Validation limits

GitHub source reads confirm the intended helpers, endpoint call sites and
workflow test command. This run did not execute pytest, npm typecheck, Android
Gradle, Expo export or device tests. The current PR head had no associated
pull-request workflow run and no combined status checks at inspection time.
Older recorded Actions failures had runner ID 0, empty steps and BlobNotFound
logs; they did not reach the compiler or tests. No green CI is claimed.

The threadpool change reduces event-loop blocking but is not a 60,000-user
capacity test. A PostgreSQL concurrency test, DB pool saturation probe and
end-to-end Android/iOS recovery test remain acceptance gates.

No main merge, production deploy, migration, APK/IPA publication or patient
record mutation was performed.
