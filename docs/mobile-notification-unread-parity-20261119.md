# Mobile notification unread parity and request reduction

Date: 2026-11-19  
Branch: `feature/mobile-web-parity-20261110`  
PR: #257 · Tracking issue: #258

## Web flow traced first

The web notification center is implemented in `app/templates/base.html`. Its realtime handler changes the notification badge for `NOTICE_CREATED`, `NOTICE_RESOLVED`, and `NOTIFICATIONS_READ`. Patient, analysis, program, profile, and ordinary chat events are handled by their own UI paths; they do not cause a notification-center count fetch.

The web badge is backed by the authenticated notification-center state. The native home screen should follow the same event contract rather than refreshing on every event received from `/ws/sync`.

## Findings

1. Native `Home` previously called `getNotifications(token)` for every `lastEvent`. That downloaded up to 20 notification rows (titles, messages, and target URLs) even though the home screen only displayed a count.
2. The broad effect also caused avoidable count/list database work after patient, analysis, program, and other unrelated events. This is unnecessary fan-out as the application grows.
3. The mobile list endpoint returned `is_read` in its legacy `notifications` array but omitted it from the preferred `items` array. The client prefers `items`, so its read-state normalization could disagree with the web UI when legacy `read_at` and `is_read` values were inconsistent.
4. The Android TS2554 media regression was already resolved earlier on this branch: the obsolete duplicate `MediaGallery` implementation was removed from `ModernScreens.tsx`, and the registered route delegates to the owner-scoped `NativePatientMedia` implementation. A focused signature regression test now protects that contract.

## Changes in this pass

- Added `GET /api/mobile/v1/notifications/unread-count`. It requires the normal mobile bearer identity, scopes the count to `user.id`, returns only `unread_count`, and applies the existing private/no-store response headers.
- Added canonical `is_read` to both mobile notification list shapes. The `is_read` flag is the user-visible read state used by the web and native notification centers; `read_at` remains the timestamp used for retention/audit.
- Added a strict native count-only client and a backwards-compatible read-state normalizer for older servers that only returned `read_at`.
- Changed the native home badge to refresh only for `NOTICE_CREATED`, `NOTICE_RESOLVED`, and `NOTIFICATIONS_READ`, matching the web sync flow. Returning to the focused Home screen still refreshes the count.
- Added regressions for owner isolation, unauthenticated access, minimal response shape, private cache headers, inconsistent legacy read flags, notice-only event filtering, and the canonical media API signature.

No polling loop, background worker, provider call, or new dependency was introduced.

## Verification and remaining gate

The changes and regression tests are committed to the feature branch only. This run could inspect GitHub source, branch history, and workflow/status metadata, but it could not execute the Android TypeScript compiler, Node test suite, pytest, or Gradle locally because the repository/runtime is not available in the execution container.

The Android and security workflows remain `workflow_dispatch`-only. The last reported hosted attempts failed before their first step with a runner-side `BlobNotFound 404`; the current branch head has no attached workflow run or check result. That is an infrastructure blocker, not evidence that the application regression suites passed or failed. Automatic triggers were not re-enabled, to avoid restoring the repeated CI email stream.

The reported `npm audit` aggregate (14 moderate, 4 high) still has no package paths or advisory details in the available output. Dependencies were not changed and `npm audit fix --force` was not run. A complete audit report is required before safe, targeted dependency remediation.

No merge to `main` and no production deployment were performed.

## Next blocker

Run the existing manual Android typecheck and security recovery workflows once the hosted runner can allocate jobs, then capture the full `npm audit --json` report. After those gates, continue the next web/native parity slice without broadening the scope or introducing polling.
