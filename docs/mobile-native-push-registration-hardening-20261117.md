# Native push registration hardening — 2026-11-17

## Scope

PR #257, branch `feature/mobile-web-parity-20261110`. This change follows the account/device notification work and does not merge to the base branch or deploy anything.

## Web flow inspected first

The existing browser flow in `app/templates/base.html` obtains `/account/push/config`, asks for permission only after an explicit account action, registers `/push-sw.js`, and posts the browser subscription to `/account/push/subscribe`. Notification cards use same-origin `target_url` values and the service worker keeps the lock-screen body generic.

The native flow is separate by design: `mobile/src/nativePush.ts` requests an Expo token only from Profile → Device Notifications, registers it through `/api/mobile/v1/push/devices`, and resolves only server-authored notification/consultation targets. The native OS payload does not contain patient names, case text, or clinical details.

## Findings and fixes

### 1. Expo token regex rejected valid tokens on both sides

Both the native validator and the backend route contained two literal backslashes before the opening and closing brackets. As a result, the pattern expected a backslash-wrapped token rather than the real `ExpoPushToken[...]` / `ExponentPushToken[...]` shape.

- Native validation failed before the registration request could be sent.
- If a token reached the server, `register_mobile_push_device` rejected it with HTTP 422.
- The existing API test already used a canonical token, but the prior Actions job had no steps/logs, so that regression was not exposed by CI.

The token-shape rule is now centralized in `mobile/src/pushToken.ts`; the backend uses the same canonical bracket semantics. Both accept 8–128 URL-safe token characters and reject whitespace, escaped brackets, unsupported prefixes, and out-of-range lengths.

### 2. Existing production schemas could lack the native push table

The PR branch adds `MobilePushDevice` to `app/main.py`, but the existing schema revision is 15 and the production startup path intentionally does not replay `main.init_db()` after the revision check. The release migration path did not create this newly added table. A valid registration could therefore fail on an existing database with a missing-table error.

`app/migrate.py` now ensures `MobilePushDevice.__table__` and its indexes through an idempotent compatibility helper called by `require_schema`. PostgreSQL uses a transaction-scoped advisory lock and a 10-second lock timeout; other test dialects use the same idempotent table/index creation without a PostgreSQL lock. The schema revision remains 15. This is code only: no migration or database operation was run against production.

## Regression coverage added

- Native pure-helper tests for Expo and Exponent prefixes, 8/128-character boundaries, malformed/escaped values, and wrong prefixes.
- Backend API tests for both supported prefixes and malformed values.
- A schema-compatibility test that starts from revision 15 and verifies the native push table and required columns are created without changing the revision.
- Existing ownership isolation, 10-device limit, no-store response headers, and revocation tests remain in place.

## Validation performed in this run

- JavaScript regex behavior checked against canonical and malformed sample tokens: passed.
- Python `re.fullmatch` behavior checked: 3 valid and 5 invalid cases passed.
- Source checks confirmed the native app uses the shared helper, the backend has single-escaped bracket semantics, and the migration helper is called by `require_schema`.
- The repository's full Node/TypeScript/pytest/Android suites were not executed locally because this session has no checked-out repository/dependency environment.

## CI limitation

The last pre-change runs on commit `28be1e8edb7f9913bffce27400838b78dd628ce8` were:

- Android CI: `44065067496`
- Security recovery: `44065067071`
- Admin security: `44065066993`
- Expert social: `44065067325`
- Voice regression: `44065066860`

The GitHub job records exposed `logs_url: null` and `steps: null`; the step and log endpoints returned no executable steps/log blob. This is consistent with a job that never reached a runner, but the repository API data does not establish the exact organization/account-side cause. New commits should trigger Android and Security workflows because the changed paths are already included in their PR filters.

## Safety boundary

- No main merge.
- No live deploy.
- No production migration execution.
- No APK/IPA publication.
- No patient data read or modified.
