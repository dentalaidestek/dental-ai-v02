# Native support account isolation and recovery — 2026-11-21

## Web-first review

Before changing native code, reviewed the current branch versions of:

- `app/templates/support_request.html`: authenticated support creation, optional private consultation association, ticket conversation loading, read-through acknowledgement, older-message paging and realtime refresh.
- `app/templates/_support_status_regions.html`: owner-facing ticket/report cards, unread counters and the one-reply-per-support-turn UI.
- `app/mobile_api.py`: bearer-authenticated support endpoints, owner-scoped ticket access, `MobileSupportMutationReceipt`, payload-hash replay and the shared web reply eligibility rule.
- `mobile/src/NativeSupportRequests.tsx`, `mobile/src/modernApi.ts` and `mobile/App.tsx`: native form, encrypted recovery intent, inbox/detail requests and navigation.

The backend already checks `SupportTicket.user_id` for detail/read/reply and stores only the idempotency receipt digest and resulting IDs. This change does not weaken or replace that authorization.

## New privacy finding

The native support screen previously used global SecureStore names:

- `dai.support.create.pending`
- `dai.support.reply.pending.<ticket_id>`

They did not include the authenticated account ID. On a shared device, a pending support draft from account A could therefore be restored into account B's support form. The reply key also relied only on a ticket ID, which is not an account boundary.

There was a second lifecycle gap: list, detail, older-page and realtime refresh promises could resolve after the token or selected ticket changed and still update the visible screen. The application root remounts when the user ID changes, but token rotation and in-screen selection races still require local request ownership checks.

## Changes

- Added `supportDraftScope.ts` with validated v2 storage keys:
  - `dai.support.create.pending.v2.<user_id>`
  - `dai.support.reply.pending.v2.<user_id>.<ticket_id>`
- Pending intents carry `version=2`, `user_id` and an explicit `CREATE`/`REPLY` kind; restore validates the account and, for replies, the ticket ID.
- The old unscoped keys are deliberately not migrated, read or deleted. Their owner cannot be inferred safely, so the new client leaves them inaccessible rather than assigning another account's content or deleting a possibly recoverable prior-account intent.
- `NativeSupportRequests` now receives the authenticated `userId` from `mobile/App.tsx`.
- Session-scoped request generations prevent stale list/detail/realtime/pagination results from replacing the current view after token or ticket changes.
- Older message pages are deduplicated by message ID and must advance the cursor.
- Once a mutation has an unresolved idempotency key, its payload fields are locked. The user retries the same content/key; editing no longer silently deletes the receipt intent and risks creating a second support ticket/message after a lost response.
- SecureStore persistence is inside the mutation error boundary; a failed local persist does not send the request.

## Regression coverage

- `mobile/tests/supportDraftScope.cjs`: account/ticket namespace separation, invalid IDs, version/kind/user ownership and reply ticket ownership.
- `mobile/tests/supportRequests.cjs`: no legacy global-key reads, user ID wiring, mutation payload lock and stale-response guards.
- `mobile/package.json`: the new helper tests are part of `npm run test:beta`.

## Acceptance limits

The support routes remain owner-scoped and the existing server-side idempotency receipt is unchanged. This work does not inspect or modify any real support ticket or user content. The new code must still pass the latest-head Android typecheck and beta CI; a passing prior HEAD is not evidence for this new commit. Shared-device Android/iOS acceptance and PostgreSQL concurrency tests remain separate gates. No 60,000-user capacity claim is made.

No schema migration, main merge, production deploy, APK/IPA publication or patient/support record mutation.
