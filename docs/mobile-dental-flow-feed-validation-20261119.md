# Dental Akış feed payload boundary — 2026-11-19

## Web-first comparison

Reviewed the actual member feed and profile surfaces before changing native code:

- `app/templates/expert_following.html`: discover/following tabs, specialty filters and paged feed.
- `app/templates/_expert_social.html`: profile posts, owner-only composer, publication/about tabs and moderation status.
- `app/static/expert-social.js`: post rendering, follow/like/comment actions, media cards, share/report actions and moderation refresh.
- `app/expert_social_api.py`: `post_rows`, member feed routes, owner visibility, media ownership, like/follow and comment authorization.
- `app/expert_social_models.py`: bounded media references, idempotency keys, unique like/follow constraints and moderation records.

The web client receives server-rendered JSON and inserts untrusted post text with DOM text nodes. The native client used a TypeScript cast for feed rows; that cast did not validate runtime data.

## Gap and correction

A malformed or stale API response could pass through `getFeed` with invalid identifiers, counters, media URLs or moderation values. Native components then trusted the shape for list keys, navigation, image requests and moderation labels.

Added `normalizeSocialFeedPost` and applied it at the feed API boundary. It now rejects:

- Invalid post/author IDs, versions, timestamps, counts and required interaction flags.
- More than four media entries or media URLs that do not exactly match the first-party media route for their ID.
- Unpublished posts not explicitly marked as owned by the current viewer.
- Malformed author metadata and malformed/bounds-exceeding moderation reason/state payloads.
- Duplicate post IDs, more than 15 feed rows, and invalid pagination cursors.

This is response validation only. Server-side ownership, block checks, publication eligibility, authorization, idempotency and moderation remain authoritative. No patient/clinical record, backend route, schema or moderation policy changed.

## Regression coverage

Added tests for valid feed rows, invalid IDs/counters/dates, foreign media URLs, excessive media, unpublished non-owned content, duplicate IDs, malformed cursors and malformed moderation metadata. Existing feed, follow, like, comment, media and session-isolation tests remain in their current test groups.

## Commits in this batch

- `7c11c81` — add feed post trust-boundary normalizer.
- `6aa012b` — apply normalization and validate page/cursor envelope.
- `bf1ca22` — test feed identity/counter/media rejection.
- `ef8505e` — validate bounded moderation metadata.
- `90a807b` — test moderation metadata rejection.

## Validation limits

The connected GitHub environment was used to read and write the branch. It did not provide a local repository checkout or Node/Python runtime for executing the committed test files. No full `npm test`, `tsc --noEmit`, pytest, Android build, PostgreSQL test or device acceptance is claimed. CI was not dispatched. The new head must still be run on an allocated runner.

The web Dental Akış feed has no gift-sending control or gift API in the inspected template/JS/API flow; gift behavior belongs to a different feature and was not invented here.

No PR merge, main update, production deployment, migration or user/clinical data mutation.

## Follow-up backend contract correction — 2026-11-19

A closer comparison of the moderation serializer found two valid server values that the first native normalizer incorrectly rejected:

- `app/expert_social_moderation.py::describe` emits a UUID string for `job_id` when a moderation task exists; it emits `null` for a legacy row without a task.
- The same legacy path emits `revision: 0`. A positive-only integer check rejected those pre-task rows.

Updated the native `SocialModeration.job_id` type to `string | null`, validate canonical UUID v4 task IDs, and accept non-negative revisions while keeping `content_version` positive. Regression coverage now includes a registered UUID task, a legacy `job_id: null / revision: 0` row, numeric/malformed job IDs and negative revisions.

A local isolated rule check passed 5 assertions. The committed `social.cjs` test was not run as part of the full repository suite; current-head CI still has no check-runs/statuses. No backend schema or moderation record was changed.
