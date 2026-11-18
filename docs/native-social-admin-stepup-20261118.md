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
