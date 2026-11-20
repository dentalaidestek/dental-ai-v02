# Native voice final-review retry parity — 2026-11-21

## Web flow inspected first

Before changing native code, compared:

- `app/templates/voice_exam_panel.html`
- `app/static/voice-exam.js`
- `app/static/voice-finish-draft.js`
- `app/voice_exam.py`
- `app/voice_exam_final.py`

The web flow retains the previous `source_fingerprint` only for a retry of an unchanged final-review snapshot when `review_status.source_retryable` is true. The server recomputes the source signature and returns `not_modified` when the evidence is unchanged, avoiding a second Claude final-review call. The web client also compares the patient revision returned by final review with the revision captured during extraction before displaying the result.

## Native gap found

The native `finalizeVoice` client did not send `source_fingerprint` at all and `VoiceExamEntry.finalize` did not compare the final-review response revision with the extraction revision. Consequences:

- Retrying a partial source review could repeat source retrieval and the final model call even when the source signature had not changed.
- A patient record changed between extraction and final review could leave native UI showing a result based on a stale revision.

This was a source-level parity gap found by tracing the real web/backend path, not a reported TypeScript compiler failure.

## Changes on the PR branch

- `mobile/src/voiceApi.ts`
  - accepts an optional, strictly validated 64-hex `source_fingerprint`;
  - accepts the extraction revision as an expected revision;
  - validates the final response revision and source fingerprint;
  - accepts `not_modified` only when the returned fingerprint exactly matches the supplied prior fingerprint;
  - keeps the web 72,000-character / 216 KB transcript envelope explicit.
- `mobile/src/VoiceExamEntry.tsx`
  - stores the last final-review source fingerprint and exact request snapshot in memory only;
  - sends the fingerprint only when a previous final result exists, that result is retryable, and the request snapshot is byte-for-byte unchanged;
  - preserves the previous full review on a valid `not_modified` response or a retryable source outage;
  - invalidates the retry receipt when the user edits clinical content, changes patient/account, withdraws consent, or removes/restores extracted items;
  - rejects a patient revision mismatch, clears the stale final result and requests a fresh extraction;
  - avoids an unnecessary manual final-review call when the current result is complete and no source retry is pending.
- `mobile/tests/voiceApi.cjs`
  - covers source-fingerprint forwarding, invalid retry keys, malformed response identity and patient-revision mismatch.
- `mobile/tests/voiceWorkflow.cjs`
  - covers a source-only retry, the `not_modified` response and preservation of the already-rendered final review;
  - aligns final-review mocks with the backend's revision/source-fingerprint response contract.

## Commits

- `ee5ab97` — validate final-review revision and source receipt
- `f8898a3` — cover source retry and patient revision contracts
- `b45019e` — native source-only final-review retry
- `a51cf9c` — rendered workflow regression for unchanged-source retry
- this documentation commit records the acceptance boundary

## Verification and limits

The new Node regressions are registered through the existing `mobile/package.json` `test:beta` script, but were **not executed in this run**. No new green typecheck, beta suite, Android APK, Python pytest or device result is claimed.

At the previously confirmed PR head `cb68dbe`, GitHub returned zero commit statuses and no PR-triggered workflow runs. The issue/PR evidence from 2026-11-19 records earlier current-head Actions jobs failing before step 1 with `runner_id=0`, empty runner names/steps and `BlobNotFound 404` job logs; npm/tsc, Gradle and pytest did not start. The exact hosted-runner/account/billing cause is not exposed by the available GitHub records. The newly created commits must receive a real runner-backed check before source validation can be called green.

No patient records, clinical audio, production database or live service were modified. No main merge, production deploy, migration, APK/IPA publication or store release was performed.
