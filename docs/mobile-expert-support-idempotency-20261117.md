# Expert consultation messaging idempotency — 2026-11-17

## Web-first comparison

Compared the actual web consultation room (`app/templates/expert_case_room.html`) and its multipart/text submit flow with the native `ConsultationChat`, `modernApi`, and `ChatAttachmentComposer` flow.

The web client already sent a `client_message_id` for text and media retries, but the canonical handlers only echoed the ID; they did not persist a receipt or bind the key to the submitted content. Native text kept the key only in memory, and native media did not send a stable key. A lost response or process death could therefore create a second message or attachment.

## Server contract

- Added `ConsultationMessageReceipt`, keyed by the composite primary key `(case_id, sender_user_id, client_message_id)`. The table stores only a SHA-256 payload digest, resulting message ID, and timestamp; it does not duplicate message text or media.
- The composite key is the only lookup index. Case and sender are the leading columns, and retention cleanup deletes receipts with the case messages.
- Text and media handlers replay the original message for the same sender/key/payload. Reusing a key for different content returns HTTP 409.
- Media identity binds message type, raw-byte SHA-256, and reply target; the filename is deliberately excluded so a renamed copy of the same file does not create a second message. Raw bytes are never stored in the receipt.
- Message, receipt, and durable realtime events are committed in one database transaction.
- Added an authenticated mobile receipt lookup. It is participant-checked, sender-scoped, and returns `Cache-Control: private, no-store`. A peer in the same consultation cannot read another sender's receipt.
- Message retention deletes receipts in the same transaction as the chat messages. A deleted conversation reports `deleted: true` so clients can clear local pending intent.

## Client recovery

### Native text

- The clinical text remains in the existing encrypted SecureStore draft only once.
- A separate SecureStore intent stores only version, random request ID, account/case scope, and reply target.
- The draft is persisted before the intent and before the network mutation.
- On reconnect or app restart, the client queries the receipt. If it exists, the draft is cleared before the intent key. If no receipt exists, retry uses the same key and same text.
- Text editing is locked while the outcome is unresolved. Malformed or missing pending metadata fails closed rather than silently creating a new key.

### Native media

- The composer persists only the random key, account/case scope, MIME type, size, reply target, and creation time. It does not persist the file URI, bytes, or filename.
- After process death, the client checks the receipt first. If no receipt exists, the user reselects the same file and the same key is reused; the server rejects different bytes with 409.
- A deleted conversation clears the local pending media intent.

### Web media

- The consultation room keeps the pending key and non-content signature in sessionStorage, scoped by case and user.
- The signature contains type, size for non-images, and reply target; it contains no filename or clinical content.
- Refresh/retry reuses the same key. A different payload cannot silently reuse the key. Existing message-ID deduplication prevents a replayed response from adding a second DOM bubble.

## Schema migration

- Raised schema revision to 14.
- Revision 13 creates the consultation receipt table.
- Revision 12 creates both the existing mobile support mutation receipt table and the new consultation receipt table.
- Revisions 10/11 create the new table along with the existing additive tables in the recent-schema path.
- The security recovery path filter includes `app/migrate.py`.

## Regression coverage added

- `tests/test_mobile_chat_actions.py`: text replay, changed-payload conflict, sender isolation, private receipt lookup, media same-byte replay, changed-byte conflict, retention cleanup, compact composite key, and payload hash binding.
- `mobile/tests/consultations.cjs`: receipt lookup validation, media FormData key propagation, encrypted draft/intent source contract, media intent recovery, and web sessionStorage retry contract.
- `tests/test_legacy_pr215_repairs.py`: updated its synthetic request key to the bounded client-key format.

These tests are committed but have not been executed in this environment. The repository Actions runs inspected at the start of this work failed before runner allocation (empty steps and unavailable job logs); no TypeScript, pytest, or Gradle pass is claimed.

## Remaining acceptance gates

- PostgreSQL migration and concurrent duplicate-submit tests on a real PostgreSQL service.
- Full `npm run test:beta`, project TypeScript 5.9.2 typecheck, and Android build.
- Android/iOS process-death, file-provider reselect, account-switch, and two-account device tests.
- Realtime/push delivery after an idempotent replay and retention purge.
- 60,000-user load and storage-growth measurements.

No main merge, production deployment, APK/IPA publication, or patient-record mutation was performed.
