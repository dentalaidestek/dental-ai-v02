# Dental Flow comment pagination refresh race — 2026-11-19

## Web-first inspection

Re-read the current branch web flow before the native change:

- `app/templates/expert_following.html`: Dental Akış discovery/following tabs, specialty chips and paged feed shell.
- `app/templates/_expert_social.html`: canonical profile post/comment entry points.
- `app/static/expert-social.js`: comment sheet, root comment pagination and reply pagination.
- `app/expert_social_api.py`: `GET /posts/{id}/comments` uses an ascending comment-ID cursor and a bounded page size.
- `mobile/src/SocialScreens.tsx` and `mobile/src/socialApi.ts`: native comments list and authenticated cursor adapter.

The web comment loader has one shared `loading` guard, so a pull-to-refresh cannot start a second root/page request while a page request owns the loader. Native intentionally permits a first-page refresh to supersede a stale page request, but its old boolean page lock was not invalidated safely.

## Reproduced native race

1. The first comments page returns `next_cursor`.
2. The member starts loading older comments; `commentPageLock` becomes true and the request captures generation N.
3. Pull-to-refresh starts a new first-page request and increments the generation to N+1.
4. The older request resolves after the refresh. Its `finally` block checks the generation and therefore does not clear the old boolean lock.
5. Every later older-page request returns early because the lock remains true. The comment list appears to have more comments but cannot load them.

This is a native pagination deadlock after a refresh/page overlap, not a backend cursor or authorization failure.

## Change

- Replaced the boolean with `commentPageRequest: number | null`, recording the exact request that owns the page lease.
- A first-page refresh invalidates the older page lease before issuing its request.
- A page request releases the lease only if its request ID still owns it. A stale `finally` cannot clear a newer request's lease.
- Existing generation checks continue to prevent stale comment rows/cursors from being committed.
- Effect cleanup invalidates both the generation and the current lease.

No API, schema, permission, storage, patient data, polling or server query changes.

## Regression coverage

Added `comment refresh invalidates an in-flight page lease without wedging the next cursor` to `mobile/tests/socialScreens.cjs`. It drives the native Comments component through: first page, pending older page, refresh, replacement older page, late stale response, and the next cursor. It asserts that the new page can start and that the stale request cannot release its lock.

The file is already included in `npm run test:beta` and the manual `native-social-security` job in `.github/workflows/security-recovery.yml`; no workflow edit or dispatch was needed. A second source-contract regression protects the request-ID lease and refresh invalidation from being replaced by the old boolean lock.

## Validation limits

- GitHub PR #257 head before this batch: `c84238ccef4cad09d7dba6462e959de599a79c10`.
- That head had no combined status entries and no associated PR workflow runs.
- The new regression is committed but was not executed in this connector-only change session.
- Full `npm run typecheck`, `npm run test:beta`, Android/iOS export, Gradle, Python social tests, PostgreSQL and physical-device acceptance remain open.
- Existing Android/Security runs inspected in the PR history failed before their first step with runner ID 0, empty step arrays and `BlobNotFound 404` logs. This does not establish a source-level typecheck or test failure; the exact hosted-runner/account/billing cause is not exposed.

No main merge, live deployment, production migration, APK/IPA publication or user/clinical data mutation.
