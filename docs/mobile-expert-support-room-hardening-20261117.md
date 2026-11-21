# Expert support room hardening — 2026-11-17

## Web-first flow inspected

Before editing native code, re-read:

- `app/templates/expert_case_room.html`
- `app/templates/messages.html`
- `app/templates/_message_row.html`
- the web room's `messages-live?after_id`, read-receipt, media-message and annotation flows
- `app/mobile_api.py` consultation inbox, snapshot, incremental-message and receipt routes
- `mobile/src/ModernScreens.tsx`, `ChatAttachmentComposer.tsx`, `consultationRealtime.ts` and `modernApi.ts`

The web room keeps a last-message cursor, reconciles message IDs from socket and HTTP responses, renders Turkish status labels and type-specific reply previews, and serves private message/media content only to the two participants.

## New gaps found

1. Native media send success and receipt recovery still called the full `GET /consultations/{id}` loader through the `onSent` callback. This re-fetched up to 100 messages even though the attachment POST or receipt already returned the persisted message.
2. The mobile consultation inbox, full room snapshot and incremental message endpoint returned private message previews/content without explicit response cache headers. The receipt endpoint already had a partial no-store policy.
3. The native chat header rendered raw status enums (for example `EXPERT_COMPLETED`) instead of the web room's Turkish labels.
4. Native reply previews showed raw text or a generic label for image, voice, file and annotation messages; annotation rows did not use the web room's “İşaretlenmiş görüntü” presentation.

## Changes

### Incremental media acknowledgement

- `ChatAttachmentComposer` now passes the persisted `ChatMessage` returned by upload or receipt recovery to its parent.
- `ConsultationChat` merges that message by ID, advances its cursor, and lets the existing read-receipt effect observe the new message.
- A full case reload remains only for a deleted receipt with no message payload or for explicit ambiguous-state reconciliation.
- The durable idempotency key and SecureStore recovery rules are unchanged.

### Private response cache policy

- Added one response helper for participant-scoped consultation data.
- Inbox previews, full case/message snapshots, incremental messages and message receipts now return `Cache-Control: private, no-store`, `Pragma: no-cache` and `Vary: Authorization`.
- No clinical message content, filename, patient identifier or media bytes were added to the receipt or local intent.

### Web-equivalent presentation

- Added a pure status-label mapping matching the web room's status vocabulary.
- Added type-aware reply previews for image, voice, file and annotation messages.
- Native annotation rows now render the same concise label as the web room.

### Security CI coverage

- Added `tests/test_mobile_consultation_live_api.py` to Security recovery path filters and the pytest command.
- Added response-cache assertions for inbox, room snapshot, incremental pages and receipt recovery.

## Regression coverage

- `tests/test_mobile_consultation_live_api.py`: private cache headers plus existing bearer, participant and cursor assertions.
- `tests/test_mobile_chat_actions.py`: receipt response no-store assertion.
- `mobile/tests/consultations.cjs`: attachment acknowledgement merges the server message without a full room reload.
- `mobile/tests/consultationRealtime.cjs`: web status labels, type-aware previews and ID-deduplicated attachment receipt merge.

The tests are committed but were **not executed** in this environment.

## CI evidence and limits

Starting PR head: `e2e6cb6decdcc9acc8da4f5d1e73318c057a2f00`.

The latest observed Android, Security recovery, Admin security, Expert social and Voice regression runs all concluded failure before executing steps. The Android typecheck/APK and three Python regression jobs returned empty step arrays; downloading their logs returned GitHub's `BlobNotFound 404`. No compiler, Node test, pytest, Gradle or Expo export ran. The available GitHub records do not expose the exact hosted-runner/account/billing cause.

The new Security workflow now includes the incremental consultation API regression file. The next code-head workflow result must be inspected before claiming any test pass.

## Remaining acceptance

- Full TypeScript 5.9.2, Node beta, Python/PostgreSQL, Expo export and Android build.
- Two-account Android/iOS acceptance for send/replay, deleted chat, read receipts, attachments and account switching.
- Native OS push registration/response/deep-link wiring is still not installed; in-app notification read-all and unread reconciliation are separate and already implemented.
- 60,000-account / concurrent-user capacity remains unproven.

No schema migration, main merge, production deploy, APK/IPA publication or clinical record mutation.
