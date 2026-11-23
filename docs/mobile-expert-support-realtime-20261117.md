# Mobile expert-support realtime parity — 2026-11-17

## Web flow inspected first

The canonical web case room is `app/templates/expert_case_room.html`. Its message path is incremental:

- The browser tracks `lastMessageId`.
- `catchUp()` calls `/expert-support/cases/{case_id}/messages-live?after_id=...`.
- Concurrent catch-up calls are coalesced with `catchUpPromise` and `catchUpAgain`.
- `addMessage()` deduplicates by persisted message ID and reconciles pending text/media sends by `client_message_id`.
- Read receipts are acknowledged through the case-scoped read route.
- `CASE_STATUS_UPDATED` events update the state panel; authoritative room refresh is reserved for state that cannot be applied safely in place.

The web inbox is `app/templates/messages.html` with `_message_row.html`; it maintains each row's latest message ID, preview, unread count, status, and sort timestamp.

## Native gaps found

Before this change, native `Consultations` called the first-page inbox endpoint for every `MESSAGE_CREATED` event. That repeated a 50-row inbox read even though the durable event already carried the case ID, message ID, preview, timestamp, sender direction, and status.

The native chat also called `GET /consultations/{id}` for every new-message event and on socket reconnect. That returned the latest message page (up to 100) instead of following the web room's `after_id` cursor. A send acknowledgement also caused another full case read even though the server returned the persisted message.

## Changes

### Backend

- Added `last_message_id` to the mobile consultation inbox rows.
- Added `GET /api/mobile/v1/consultations/{case_id}/messages-live?after_id={id}&limit={n}`.
- The new endpoint requires the existing Bearer-authenticated mobile user and verifies that the user is one of the two case participants; nonparticipants receive 404.
- The response is bounded to at most 100 messages, ordered by increasing message ID, and includes an advancing `next_after` only when another page exists.
- The incremental response includes only case status/deadline metadata and message rows. It does not include patient identifiers, clinical summary, or patient profile fields.
- If message retention has removed the case messages, the endpoint returns an empty terminal page and the deletion timestamp.

### Native inbox

- Added a pure reducer for `MESSAGE_CREATED`, `CASE_READ`, `CASE_STATUS_UPDATED`, and `CASE_CREATED`.
- New message events patch only the matching visible row, update the preview/time/last-message ID, and increment unread count only for incoming messages.
- Duplicate and out-of-order message events are ignored using `last_message_id`.
- A case-read event clears unread count only for the account that performed the read.
- Case creation and detected durable-event gaps trigger an authoritative first-page refresh; ordinary message events no longer do.

### Native chat

- Added a validated client for the incremental message endpoint.
- The chat tracks a per-case message cursor and coalesces overlapping catch-up requests.
- Socket reconnects and relevant message events fetch only messages newer than the last verified message ID.
- A catch-up is bounded to five 100-message pages per batch; if the final page still advertises more data, the coalesced continuation is queued.
- Message rows are merged by ID and sorted ascending, preventing duplicate rendering when a POST acknowledgement, durable realtime event, and HTTP catch-up describe the same message.
- A successful text-send response and a recovered message receipt are applied locally instead of triggering a full case reload.
- Status events patch the current case snapshot; peer read events update `other_read_at`. Case updates and reports still use an authoritative room reload.

## Regression coverage added

- `tests/test_mobile_consultation_live_api.py`: Bearer requirement, participant-only access, incremental cursor paging, terminal empty pages, and absence of patient/clinical-summary fields in the incremental snapshot.
- `mobile/tests/consultations.cjs`: inbox latest-message ID normalization, successful incremental reads, empty terminal pages, duplicate/out-of-order/foreign page rejection, and nonadvancing cursor rejection.
- `mobile/tests/consultationRealtime.cjs`: incoming/outgoing preview updates, unread-count behavior, duplicate/out-of-order event rejection, read receipt scoping, status patching, message merge idempotency, and source-level checks for incremental chat/inbox integration.
- `mobile/package.json`: registered the new realtime regression file in `test:beta`.

## Validation limits

The GitHub Actions jobs were checked before and after the changes. The latest Android typecheck and Security jobs still have no assigned runner (`runner_id=0`), no steps, and no downloadable logs. Therefore the repository's full TypeScript, Node beta, pytest, Android build, and security suites have not run in this environment. The added tests are committed but must not be described as passed until a runner executes them.

No schema migration, production deployment, APK/IPA publication, or main-branch merge was performed.
