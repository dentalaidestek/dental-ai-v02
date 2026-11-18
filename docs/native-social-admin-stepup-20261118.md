# Native Dental Flow admin step-up (2026-11-18)

## Web flow reviewed first

The reference remains `admin_social.html`, `expert-social-admin.js`, `expert_social_api.py` and `main.py`:
- Web administrators use the fixed administrator mailbox and a six-digit email OTP.
- The existing browser grant remains in `AdminVerifiedSession` and is validated by `main._admin_only`.
- Social moderation continues to use the existing queue, report, detail and version-checked decision endpoints.

A native Bearer token must not inherit the browser cookie grant. This implementation adds a separate, narrower authorization.

## Native API

- `POST /api/expert-social/admin/step-up`: requires an active, verified ADMIN Bearer session whose email is the fixed administrator mailbox; sends a six-digit code only to that mailbox.
- `POST /api/expert-social/admin/step-up/verify`: verifies the code once and returns an opaque five-minute token with the `SOCIAL_MODERATION` scope.
- `POST /api/expert-social/admin/step-up/revoke`: revokes the current session's step-up token idempotently.

The grant is bound to the hash of the exact active `SessionToken`. It is not an `AdminVerifiedSession`, does not alter browser MFA and is checked only by the social moderation router.

## Security properties

- Raw bearer tokens, OTP codes and step-up tokens are not stored in the database.
- OTP hashes use Argon2id; session and grant tokens are high-entropy opaque values stored by hash.
- Challenge expiry: 10 minutes; resend cooldown: 60 seconds; maximum attempts per challenge: 5.
- Shared `auth_rate.admit` counters limit requests by IP, user and native session.
- Step-up grant expiry: 5 minutes; scope is constrained by a database check.
- Each privileged request rechecks account role, active status, fixed mailbox, verified email, active bearer session, grant scope, expiry and revocation.
- Existing web cookie MFA remains unchanged.
- Responses are private/no-store.
- Social schema revision 3 adds two isolated tables and their indexes.

## Mobile client state

The mobile API exposes begin/verify/revoke helpers. The opaque step-up token is not persisted by these helpers. The native moderation UI has **not** been added yet; it must keep the token in memory only and clear/revoke it on close, account change, background or expiry.

## CI and notification finding

The branch's `android-test-apk.yml` was still triggered by every push touching `mobile/**`. Other Android typecheck, Security Recovery and Admin Security workflows were already manual-only. Recent mobile commits therefore generated repeated APK workflow runs. The latest inspected run #44273348890 (commit `5b692f7`) had job `134695200557`, `runner_id=0`, no steps, no artifacts and a `BlobNotFound 404` log response. TypeScript/npm/Gradle did not start. The APK workflow is now manual-only with a concurrency group.

## Not yet accepted

- Native admin queue/report UI, queue pagination, detail view and decision history.
- Full pytest, Node beta, Android typecheck, Expo export, Gradle APK and physical-device tests were not run in this connector session.
- Hosted runner allocation is outside repository source code; this change prevents repeated push-triggered runs but does not repair GitHub runner allocation.
- Schema revision 3 has not been applied to production. No deploy or migration was run.

PR #257 remains open/Draft. No main merge, live deploy, production migration, store publication or clinical-data mutation.

## 2026-11-18 — step-up lifecycle and client response semantics

A second review of the native OTP flow found a client-side distinction that the generic social request adapter did not preserve: an incorrect OTP is intentionally returned as HTTP 401, but the adapter treated every 401 as a possible expired Bearer session and launched an extra /api/mobile/v1/me probe. The backend now returns the machine-readable SOCIAL_ADMIN_OTP_INVALID code for this one response; the client skips session revalidation only for that explicit code. Generic 401 responses and non-JSON gateway 401 responses still trigger the existing session probe.

Additional hardening:
- Social API responses vary on Cookie, Authorization and the scoped step-up header while remaining private/no-store.
- Expired OTP challenges and five-minute grants are pruned in batches of at most 100 each on the rare step-up issue path. Live credentials are not touched; no feed or general API request performs this cleanup.
- Native step-up tokens are validated as the exact URL-safe 43-character form produced by secrets.token_urlsafe(32).
- Added bounded native adapters for moderation queue, reports, detail/history and version-checked decisions. They require the step-up header and validate cursor, collection, media, history and version shapes before exposing data to a future native screen.

Regression coverage added:
- Python: structured invalid-OTP response, authorization-aware Vary headers, and bounded cleanup retaining live challenge/grant rows.
- Node: invalid OTP does not cause a /me probe, ordinary 401 still does, scoped moderation headers are attached, and malformed grants/queue/report/detail/decision payloads are rejected.

These tests are committed and included in the existing Admin Security and Security Recovery workflow commands. They were not executed in this connector session. Current branch head remains manual-workflow only; no Actions run was started. The exact hosted-runner allocation cause remains outside the repository API evidence. No production migration, deploy, main merge or native admin UI was added in this follow-up.

## 2026-11-18 — native moderation screen

Added NativeSocialAdmin and an ADMIN-only Home entry/stack route. The screen uses the web queue's POST/COMMENT/PUBLICATION filters and PENDING/PUBLISHED/REJECTED states, the reports list, detail view, decision history, operational moderation history, media preview, and version-checked publish/request-changes/reject actions. It does not create a parallel moderation backend or bypass the existing fixed-mailbox OTP.

The five-minute step-up token is held only in a component ref/state (memory); it is never written to SecureStore or AsyncStorage. It is revoked best-effort and cleared on navigation blur/unmount, app background/inactive, expiry, and token/account change. Backend expiry and session binding remain authoritative if the device is offline during revoke. A role check hides the screen from non-ADMIN accounts, and every API operation still requires the backend's verified fixed-mailbox ADMIN and scoped step-up grant.

The screen shows only bounded text/media/history fields, keeps decision reasons to 300 characters, warns against putting patient identifiers or health data in reasons, and uses the authenticated first-party image helper. Native admin decisions do not modify patient charts or clinical records.

Added a source-contract regression for memory-only grant lifecycle and ADMIN/version gates. It is included in mobile test:beta and Security Recovery's native-social-security command. These checks and the full mobile typecheck/beta suite were not executed in this connector session; device-level navigation, OTP email delivery, image rendering, and real moderation decisions remain unaccepted.

