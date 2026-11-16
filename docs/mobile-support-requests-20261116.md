# Native support requests — web parity implementation

Branch: `feature/mobile-web-parity-20261110`  
Scope: PR #257 / issue #258  
Status: implementation committed; runtime/CI acceptance pending.

## Web contract inspected first

Reference files:
- `app/templates/support_request.html`
- `app/templates/_support_status_regions.html`
- `app/main.py` handlers for `/support-request`, `/fragment`, `/{ticket_id}/conversation`, `/{ticket_id}/reply`, and `/{ticket_id}/read`
- `tests/test_support_ticket_flow.py`

Web behavior:
- Authenticated users create a private support ticket with subject (max 160) and message (max 4000).
- The web form can optionally associate a selectable expert conversation. The current native form intentionally omits that optional association; this remains a parity gap.
- Ticket list filters include all, open, waiting, in progress, and closed. The web screen also includes a separate user-report/notification list; the native screen currently covers support tickets, not that separate report inbox.
- Conversation history is paged; reply is permitted only when the latest support turn was sent by an admin and the ticket is not closed.
- Read cursors are persisted independently in `SupportTicketReadState`.
- User access is scoped to `SupportTicket.user_id`; inaccessible tickets return not found.

## Native implementation

API routes under `/api/mobile/v1/support/tickets`:
- GET list (authenticated; owner-scoped; bounded to 100 newest support tickets)
- POST create (authenticated; 160/4000 character validation)
- GET detail (authenticated; owner-scoped; last 20 messages)
- POST read cursor
- POST reply (authenticated; closed/turn rules match web)

A durable `MobileSupportMutationReceipt` records per-user create/reply idempotency keys and payload hashes. Reusing a key with identical content returns the original ticket/message; reusing it with different content returns HTTP 409. Reply uses a row lock and the existing web `_support_user_can_reply` rule. The mobile client persists pending draft content and its idempotency key in SecureStore so a lost response/app restart can retry the same mutation.

Native screen: `mobile/src/NativeSupportRequests.tsx`; reachable from the home quick actions and the native navigation stack. `/support-request` notification targets now resolve to that actual screen.

## Security and acceptance

- Native endpoints require the existing verified bearer session.
- List/detail/read/reply query only `source_type=SUPPORT` tickets owned by the authenticated user.
- Other accounts receive 404 for another user's ticket.
- User cannot reply before an admin turn, after closure, or twice in one turn.
- No patient data, expert consultation message or support message content is placed in push payloads.
- The native form does not support optional linked-case selection yet.
- Native UI currently loads up to 100 newest tickets and last 20 messages per detail; older-message pagination and separate report inbox remain open.

## Tests added, not yet executed

- `tests/test_mobile_support_api.py`: authenticated creation, idempotent replay, payload-key collision, cross-account isolation, admin response gating, reply replay and one-reply-per-turn.
- `mobile/tests/supportRequests.cjs`: API/UI/security source contracts and durable draft behavior.
- `mobile/tests/notificationTargets.cjs`: `/support-request` native route.
- `mobile/package.json`: support regression added to `test:beta`.

No claim of passing pytest, TypeScript, Expo or device tests: the connected GitHub Actions runs have not been associated with the latest content-API commits, and this environment did not execute the repository test commands.

No main merge or production deploy.
