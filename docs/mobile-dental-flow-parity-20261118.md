# Dental Akış — native/web parity follow-up (2026-11-18)

## Web-first references inspected

- `app/templates/expert_following.html`: member feed shell, Keşfet / Takip Ettiklerim tabs, specialty filters, expert directory link and paged feed.
- `app/templates/_expert_social.html`: profile tabs, owner-only composer, post/publication/about sections and review-state surface.
- `app/static/expert-social.js`: author verification marker, timestamp, follow state, post actions, moderation status refresh, reason text, comment threads, link previews and media viewer.
- `app/static/expert-social.css` and `app/static/dental-flow.css`: web card and feed hierarchy.
- `app/expert_social_api.py`: bearer/cookie actor resolution, verified-expert gating, `GET /posts/{id}`, owner-only pending post visibility and moderation metadata from `post_rows`.
- `app/expert_social_moderation.py`: durable review state and user-safe explanation fields.

## Native gaps found and addressed

1. The general native Dental Flow header showed `＋ Paylaş` whenever `expertId` was absent. That is the member discovery feed, not an expert-owned profile; regular members could see a composer that the API would reject. The general feed no longer exposes this action. The owner profile composer remains gated by `PublicExpert.can_publish` and ownership.
2. Native owner cards displayed only a generic `İnceleme durumu: PENDING` string. They did not expose the moderation explanation or a way to refresh the authoritative state after a moderator decision. The card now shows a bounded user-facing reason and an accessible `Durumu yenile` action backed by `GET /api/expert-social/posts/{id}`.
3. The refresh response is validated before use: requested post ID, owner ID, status, version, media array and moderation state/reason are checked. Feed-only author metadata (specialty/follow/support state) is retained when the detail endpoint does not include it.
   The detail boundary also rejects more than four media items, non-first-party media URLs, malformed interaction counters/flags and any non-published detail response that is not marked as owned. Exhausted moderation failures are labeled as requiring administrator intervention instead of promising an automatic retry.
4. Native post headers previously showed either specialty or date. When a specialty existed, the publication date disappeared; even otherwise only the date was shown. The card now displays the verified-expert marker, specialty and full localized date/time together.

## Changed files

- `mobile/src/socialApi.ts`
- `mobile/src/SocialScreens.tsx`
- `mobile/tests/social.cjs`
- `mobile/tests/socialScreens.cjs`
- `.github/workflows/security-recovery.yml`

## Regression coverage added

- Owner moderation refresh uses bearer auth, rejects invalid IDs, mismatched post IDs and malformed moderation receipts.
- Pending owner cards show the moderation explanation and refresh the server-authoritative status while retaining feed presentation metadata.
- Published cards show the verified-expert marker, specialty and full timestamp together.
- Source contract asserts the general feed composer is not exposed to ordinary members and that publish permission is required for the owned profile.

The two Node test files are already part of `npm run test:beta`. A dedicated `native-social-security` job was also added to Security Recovery and runs:

```sh
cd mobile
npm ci
node --test tests/social.cjs tests/socialScreens.cjs
```

## Verification limits

The source and workflow changes are committed, but the Node tests and Android typecheck have not been executed locally in this environment. GitHub Actions at the previous code-bearing head failed before any workflow step: job records had `runner_id=0`, empty runner name and no steps; log downloads returned `BlobNotFound 404`. This is a pre-step runner/execution failure, not evidence of a TypeScript or test failure. The newly added native-social job must still run on an allocated runner before it can be accepted.

No screenshot/device acceptance, Android/iOS build, PostgreSQL load test or 60,000-user capacity claim is made here. No backend route, clinical data, moderation policy, patient record, production migration or provider behavior was changed.

PR #257 remains open and Draft. No main merge, live deploy, APK/IPA publication or production data mutation.
