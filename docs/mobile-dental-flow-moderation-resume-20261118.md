# Dental Flow moderation refresh and reconnect parity — 2026-11-18

## Web-first inspection

Before changing native code, re-read the current branch versions of:

- `app/templates/_expert_social.html`
- `app/static/expert-social.js`
- `app/static/expert-media-viewer.js`
- `app/expert_social_api.py`
- `app/expert_social_moderation.py`

The web owner card renders a non-published post's moderation state and exposes an explicit “Durumu yenile” action. The canonical owner-only read already exists at `GET /api/expert-social/moderation-status/POST/{id}`; it checks the authenticated actor against the content owner (or the server-side social-admin capability) and returns only target type/id, status, version and moderation metadata. The separate `GET /posts/{id}` endpoint returns the complete post representation.

## Root cause and changes

The native manual moderation refresh previously called `GET /posts/{id}`, although it only needed moderation state. That needlessly fetched post text, author details, media references and engagement counts. The feed also had no event-driven status catch-up when a clinician returned to the app or navigated back to Dental Akış, so a moderation decision made while the app was backgrounded could remain stale until the owner manually tapped the per-card button or pulled to refresh.

Changes on `feature/mobile-web-parity-20261110`:

- `mobile/src/socialApi.ts`
  - Added a typed `SocialModerationStatus` response and `getPostModerationStatus`.
  - Validates POST target binding, requested ID, allowed status, monotonic content version, bounded reason text/reason list and known moderation states.
  - Uses the existing bearer-authenticated, cookie-free social request path. No new backend route or permission rule was introduced.
- `mobile/src/SocialScreens.tsx`
  - Per-card manual refresh now calls the minimal moderation endpoint and merges only status/version/moderation metadata.
  - On app background/inactive → active and navigation blur → focus, refreshes only currently loaded, owned PENDING/REJECTED cards.
  - Maximum five candidates per resume, two requests concurrently, one shared 15-second cooldown to coalesce AppState/focus duplicates.
  - Responses are ignored after account/token change and cannot overwrite a newer post version.
  - Background refresh is best-effort; the explicit per-card retry and feed pull-to-refresh remain available when a request fails.
- `mobile/src/socialModerationRefresh.ts`
  - Added pure candidate selection, resume-transition and cooldown helpers.
- Regression files:
  - `mobile/tests/social.cjs`: bearer/cookie policy, minimal endpoint, ID/target/status/version/moderation validation.
  - `mobile/tests/socialScreens.cjs`: manual refresh uses the minimal receipt and does not call the full-post endpoint; source contract for event-driven resume, bounded candidates and no polling.
  - `mobile/tests/socialModerationRefresh.cjs`: candidate ownership/status/limit, AppState transition and cooldown behavior.
  - Registered the helper test in `npm run test:beta` and the manual `native-social-security` job in `.github/workflows/security-recovery.yml`.

## Validation evidence

- GitHub source-contract assertions: 18/18 passed. These inspect the committed branch files and test wiring; they are not the complete test suite.
- Isolated Node helper tests, using the committed helper/test source copied into a scratch workspace: 3/3 passed.
- Strict isolated TypeScript compile of `socialModerationRefresh.ts`: passed.
- Not run: repository `npm ci`, `npm run typecheck`, full `npm run test:beta`, React Native renderer tests, Expo Android/iOS export, Gradle build, Python social/backend tests, PostgreSQL, or physical Android/iOS acceptance.

## CI and remaining gates

At the starting code head `6ba20d374db3962cf1072fd93b2b8cd33343eb4a`, GitHub reported no associated workflow runs and no combined status entries. The Android and Security Recovery workflows are currently `workflow_dispatch` only, retained that way to avoid repeating the earlier notification storm. Prior current-head attempts showed runner ID 0, empty step arrays and `BlobNotFound 404` job logs; they did not reach npm/tsc/pytest/Gradle. The exact hosted-runner/account/billing cause is not exposed by the available GitHub records.

Still open:
- Full repository typecheck and test suites on a functioning runner.
- Admin moderation queue/review actions are not being claimed as native parity by this owner-status work.
- Real Android/iOS foreground/background, navigation focus and two-account acceptance.
- Network-return without an AppState/focus transition (the app still offers manual pull-to-refresh and per-post retry; no new NetInfo dependency was added).
- Dental Flow moderation/reconnect performance under the defined 60,000-user load model.

No main merge, production deployment, production migration, APK/IPA publication or patient-data mutation was performed.
