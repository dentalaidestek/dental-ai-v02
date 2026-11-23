# Native Dental Akış comments parity — 2026-11-21

## Baseline and evidence

- Branch: `feature/mobile-web-parity-20261110`
- PR: #257 (draft; base remains `feature/mobile-beta-20261110`)
- Starting head: `c76f0d7448d4251ea462664e2365b76b7a3b7680`
- Starting Android workflow: [#44873876871](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44873876871) — typecheck, session, realtime, beta, Android/iOS export and internal APK all succeeded.
- Starting security workflow: [#44873876855](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44873876855) — Python/PostgreSQL and Native Academic, Social, Voice, Program and Clinical jobs succeeded.

## Web flow inspected before native changes

- `app/templates/expert_following.html`
- `app/static/expert-social.js`
- `app/expert_social_api.py`

The web comment sheet exposes the published comment count, permits editing only by the comment author while comments are open, permits deletion by the comment author or post owner, only offers replies for published comments while the post is open, disables likes for unpublished comments, and loads reply pages with `limit=10`. The API returns `comment_count` on list/write/delete receipts and uses ascending comment IDs for the `after` cursor.

## Gaps found and changes

1. Native `CommentThread` previously knew only whether the current member owned the comment. It did not receive the parent post's ownership, so the post owner could not delete another member's comment even though the backend authorizes that action. The native action menu now receives the post-owner capability. It does not grant edit permission. The action count remains within Android's three-button Alert limit.
2. Native replies were visible for unpublished comments and for posts with comments closed; unpublished comment likes were also enabled. These controls now follow the web conditions. Editing is hidden when the post is closed; deletion remains available to the comment author/post owner.
3. Native reply pagination used the default 30-row page while web requests 10. Native reply fetches now use 10; root comments remain at 30.
4. Comment pages were accepted as a TypeScript cast without checking post/thread ownership, row ordering, duplicate IDs, counts, or cursor progress. `normalizeSocialCommentPage` now validates these fields before rendering. Invalid IDs, limits and non-advancing/mismatched cursors are rejected.
5. Native comment count was refreshed only when the sheet closed. The sheet now displays the server count and updates the feed immediately after list/create/edit/delete receipts. The feed update is guarded against a session change.

The delete endpoint's `ok`, `comment_count` and `removed_count` receipt is validated before the native UI treats deletion as complete.

## Regression coverage added

- `mobile/tests/socialScreens.cjs`: post-owner delete capability, three-button action limit, closed/unpublished reply gating, published-only likes, 10-row reply paging, and live count display/update.
- `mobile/tests/social.cjs`: post/thread binding, ordered IDs, cursor progress, count validation, root 30-row and reply 10-row request URLs, and invalid-limit rejection.

## Verification boundary

The starting-head CI runs above are green. New source and tests were committed after that head. The current environment cannot resolve `github.com` from the local container, so local `npm test` could not be run. New-head GitHub Actions results must be checked before treating these changes as passing. This work does not claim a real Android/iOS device test or a 60,000-user load test.

No production backend route, database schema, clinical record, main branch, live deployment, or store artifact was changed.
