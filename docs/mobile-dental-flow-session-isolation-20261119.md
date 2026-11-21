# Dental Flow session isolation — 2026-11-19

## Web flow inspected first

Compared the native screen with:

- `app/templates/expert_following.html`: server-selected `discover/following` mode and specialty filter.
- `app/static/expert-social.js`: `loadPosts` cursor chain, follow-state removal in the following feed, private same-origin API requests, and `dai:session-ending` cleanup of the comments sheet/drafts.
- `app/expert_social_relationships.py`: account-authorized page route, published/verified-expert filtering, mutual-block filtering, keyset pagination, and batched author details.
- `app/expert_social_api.py`: Bearer session validation, private/no-store response headers, idempotent post/comment writes, and owner-scoped moderation status.

The web page is reloaded on account/session navigation, so its DOM-owned feed and comments do not remain attached to a different native session.

## Native parity gap found

The native feed cache scope previously included the user ID, feed mode, profile and specialty, but not a session generation. The comments sheet was keyed only by post ID. A session change could therefore leave account-owned feed rows or comments mounted while a new request was pending; an old follow/edit/compose completion could also write presentation state into the currently mounted feed.

This was a client-side state-isolation defect, not an API authorization bypass. Backend owner checks and Bearer authorization remain authoritative.

## Changes

- Added `socialSessionScope.ts` with exact session identity comparison and a non-secret generation key.
- Advance a non-secret generation only when either user ID or Bearer token actually changes. The initial mount does not advance it, avoiding a duplicate first-page request. The token itself is not embedded in React keys, persisted or logged.
- Include the generation in `usePagedRecords` scope and the feed list key, so the prior cursor chain is invalidated.
- Hide the old feed, comments, media viewer and edit sheet immediately when the incoming identity differs from the last painted session.
- Remount comments by session generation and post ID.
- Clear account-owned modal state and reset the moderation resume cooldown after the new session's page scope is established.
- Guard follow, moderation, edit, profile navigation, composer completion, comments, media and support actions against stale session completions.
- Scope in-flight locks by session generation so a previous account's request cannot hold or release the new account's lock.
- Skip resume-driven moderation requests while the previous feed is hidden and the new session generation has not finished resetting.
- Keep encrypted drafts scoped by user ID; switching accounts does not delete another account's locally saved draft.

No API contract, clinical record, social database, patient media, moderation decision or provider workflow was changed.

## Regression coverage

Added three tests to `mobile/tests/socialScreens.cjs`:

1. Account and token rotation produce different non-secret UI generation keys; exact session comparison rejects old completions.
2. The feed, comments, images and edits are gated while a new session is being painted.
3. Delayed follow, edit and composer results are rejected after a session change.

A local strict TypeScript compile of the isolated session-scope helper and six Node assertions passed. This is not the full mobile test suite.

## Validation and remaining acceptance

- The complete `npm test` / `tsc --noEmit` suite was not run in this environment.
- Android APK, two-account device switching, offline/reconnect and real API acceptance remain open.
- At the prior branch head, GitHub reported zero check-runs/statuses. Earlier Android/security jobs ended before any step with `runner_id=0`, empty step lists and missing log blobs; this does not establish a source-test failure or a passing CI run.
- No CI workflow was dispatched to avoid repeating the user's previous notification storm.
- No merge to `main`, production deploy, migration or patient-record mutation was performed.
