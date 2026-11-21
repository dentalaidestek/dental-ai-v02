# Dental Flow media-key privacy and Program CI fixture — 2026-11-21

## Web-first flow inspected

Reviewed the Dental Flow web entry and client before changing native code:

- `app/templates/expert_following.html`: server-selected Discover/Following tabs, specialty filter, feed loading/empty states and continuation action.
- `app/static/expert-social.js`: cursor-based feed loading, comment-sheet lifecycle, per-post comment drafts, and `dai:session-ending` cleanup.
- `app/expert_social_relationships.py`: verified-expert visibility, block filtering and keyset pagination.
- `app/expert_social_api.py`: private/no-store API responses, Bearer/cookie authorization and idempotent post/comment writes.
- `mobile/src/SocialScreens.tsx`, `NativeSocialMediaViewer.tsx`, `socialSessionScope.ts` and the matching tests.

The native feed already scopes its page cache, modal state and media-viewer parent key to a non-secret session generation. That generation advances when either user ID or token changes; the token is compared for identity but is not meant to become a React key.

## Finding: bearer token was duplicated into an inner React key

Despite the parent viewer already being remounted with `sessionKey`, `NativeSocialMediaViewer` constructed its image child key as `mediaId:attempt:token`. This was unnecessary and contradicted the session-isolation contract documented in `socialSessionScope.ts`: a bearer credential should never be embedded in UI identity strings or debugging-visible React keys.

The parent key is sufficient for account/session rotation. The inner image key only needs the media ID and retry attempt to reject stale image callbacks and remount on retry.

## Changes

- Added `socialMediaRequestKey(mediaId, attempt)`, which accepts no token and returns a bounded non-secret media/retry identity.
- Replaced the token-bearing inner React key with the helper.
- Kept authenticated image loading unchanged: `socialImageSource(active.url, token)` still supplies the request Authorization header.
- Kept the token dependency in the viewer lifecycle effect so a direct prop rotation still resets viewer state; the parent session generation continues to force a fresh viewer instance on real session changes.
- Added regression assertions for retry key changes, empty/invalid inputs and the absence of token interpolation in the native viewer.
- Kept the web's session-ending cleanup and the native's generation-scoped modal behavior unchanged.

No token is persisted, logged, sent in a URL, or added to a test identifier by this change. No social API, server authorization, media object, or patient data was modified.

## CI root cause from the starting HEAD

Starting commit: `740b9b9c5a4cae389108adda156943f586c8e4c5`.

GitHub Actions completed and exposed two failures:

- Android workflow `44868670725`: TypeScript typecheck passed; session/authentication and realtime/pagination passed; beta suite reported 920/921.
- Security Recovery `44868670653`: Python/security, Native Clinical, Native Voice, Native Academic and Native Social passed; Native Program Security failed one test.

Both failures were the same Program test fixture problem in `mobile/tests/programParity.cjs`. The uncertain-edit fixture omitted `patient_name`, but the production event contract always includes that field and serializes it as `null` when there is no linked patient. The strict `eventValid` validator correctly rejects `undefined` (only null or bounded text is accepted). The test's fake updated event therefore could not prove the saved callback path.

Both affected fixtures now include `patient_name: null`; the production validator was deliberately not weakened.

## Validation boundaries

The fix is committed, but the workflows for the resulting HEAD must still execute before it is considered verified. The Android APK job on the starting HEAD passed, and Android/iOS JS export passed; neither substitutes for the new HEAD's beta and Native Program checks.

No live-device test, production API call, database migration, main merge, production deploy or store publication was performed.
