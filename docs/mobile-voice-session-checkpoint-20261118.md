# Native voice extraction checkpoint scope — 2026-11-18

## Finding

The native extraction checkpoint was keyed by account and patient and validated the transcript hash. That protects cross-account, cross-patient, and edited-transcript recovery, but it did not distinguish two separate examinations for the same patient when the transcript text happened to be identical within the 24-hour checkpoint lifetime. In that case, a new examination could restore the prior examination's completed review without running extraction for the new session.

## Change

- Each native voice draft now carries a random UUID v4 `sessionId` in the existing encrypted SecureStore draft.
- New drafts and an explicit local-draft reset receive a fresh session ID.
- Existing version-1 drafts without a session ID remain readable; on recovery, the recorder assigns and persists a new ID.
- The recorder reports the ID to the parent flow and passes it with the final transcript.
- Extraction checkpoints are keyed by account, patient, and session ID. The checkpoint parser requires the exact session ID as well as the account, patient, transcript hash, cursor, revision, and expiry checks.
- The previous account/patient-only checkpoint key is deleted when extraction starts, so an old unscoped checkpoint is not reused.

## Recovery semantics

The session ID is stored beside the local transcript and pending audio receipts, so a force-close/reopen of the same draft retains the same checkpoint scope. Clearing the local draft rotates the ID. A different examination therefore cannot silently inherit a prior examination's review, even when the transcript is byte-for-byte identical.

The change does not alter the server's patient records, raw-audio receipt format, Gemini/Claude provider routing, or clinician approval boundary. Patient data is still written only by the existing explicit approval action.

## Regression coverage

`mobile/tests/voiceWorkflow.cjs` now checks:
- the checkpoint is accepted for its original session;
- the same account, patient, and transcript are rejected for a different session;
- checkpoints without a session ID are rejected;
- account, patient, transcript, and expiry guards remain active.

## Verification limits

The source and test changes were committed to `feature/mobile-web-parity-20261110`. A local repository checkout was unavailable because the execution environment could not resolve `github.com`; GitHub Actions on the branch also had no new runner-backed run at the time of this change. The Node suite, full Android TypeScript check, pytest, and device-level force-close/reopen test must therefore still run before this work is considered fully verified.

No merge, production migration, or live deployment was performed.
