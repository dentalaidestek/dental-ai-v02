# Native notification and account parity — 2026-11-17

## Web flow inspected first

Reviewed the real web notification/account flow before changing native code:
- `app/templates/base.html`: notification bell, center cards, same-origin target anchors, single-flight refresh and the `/account/notifications/read-all` cutoff.
- `app/templates/account.html`: explicit Web Push setting and its user-initiated browser permission/subscription flow.
- `app/main.py`: canonical notice targets, read-all timestamp semantics, mobile push delivery and message privacy copy.
- `app/mobile_api.py`: bearer-authenticated notice list, per-notice read, push-device registration/unregistration and mobile notice delivery.
- `mobile/src/ModernScreens.tsx`, `mobile/App.tsx`, `mobile/src/modernApi.ts` and `mobile/src/notificationTarget.ts`: native center, stack targets, current permission onboarding and API contracts.

## Findings

1. The native center could mark individual notices read but had no equivalent to the web center's cutoff-scoped read-all action.
2. The native home unread badge refreshed on realtime events, but not explicitly when returning to Home after a read action on a screen where the realtime event was missed.
3. The first-run native onboarding requested Android notification permission even though the app had no Expo push token registration or push-response listener. The same screen admitted that OS delivery was not active. Asking for permission before a usable feature exists is misleading.
4. The notification target resolver already supports `/support-request?ticket_id=...` and maps it to the owner-scoped native SupportRequests screen. The earlier note claiming this route was unsupported was stale and is corrected here.
5. Backend `/api/mobile/v1/push/devices` registration endpoints and Expo transport exist, but `expo-notifications` is not a declared mobile dependency and native token acquisition/response handling is not wired.

## Changes in this turn

- The mobile notice list now returns a full active-unread count via a bounded SQL `COUNT` query independent of the 20-row display page, matching the web notification badge without loading all notices into memory.
- Added `POST /api/mobile/v1/notifications/read-all` with bearer-authenticated owner scope.
- The endpoint accepts a client-captured `seen_before` timestamp, normalizes offset-aware values to UTC, clamps future values to server time, and marks only active unread notices created at or before the cutoff.
- Existing `read_at` values are preserved. Notices created after the cutoff, resolved notices and another user's notices remain untouched.
- The endpoint returns the exact remaining active-unread count after the update, so the native badge does not derive a total from its 20 visible cards. A durable `NOTIFICATIONS_READ` realtime event carries that count and is recorded only when at least one notice changes. Replaying the same cutoff is idempotent and emits no second event.
- Added the native API adapter and a pure local snapshot helper so the list only optimistically reads items at or before the same cutoff. SQLModel's naive server datetimes are interpreted as UTC (matching the web client), while explicit offsets are respected; this prevents a +03:00 device timezone from leaving older notices visually unread.
- Added an explicit “Tümünü okundu işaretle” action. It does not mark notices read merely because the user opened the native screen; this keeps the action deliberate while preserving the web cutoff semantics.
- Home refreshes its unread badge when it regains focus, and the notification list reconciles `NOTIFICATIONS_READ` events.
- Removed the premature Android OS permission request from the first-run notice. It now explains that in-app notices are available while native Expo push registration and killed-app routing are not yet integrated. No OS permission is requested until that feature can actually register a device.
- Added backend ownership/cutoff tests, native state/UI tests, and security workflow path/test coverage.

## Tests and verification boundary

Committed tests:
- `tests/test_mobile_notifications.py`: owner isolation, active-status filter, cutoff boundary, 25 unread notices across a 20-item page, newer-notice preservation, unauthorized request, invalid timestamp and idempotent replay.
- `mobile/tests/notifications.cjs`: cutoff snapshot, already-read preservation, invalid cutoff, naive-UTC/offset parsing, native API/UI wiring, Home focus refresh and no premature OS permission prompt.

The GitHub Actions jobs inspected at the starting PR head had empty step arrays and no runner assignment; npm, TypeScript, Gradle and pytest did not start. The new tests are committed and registered but are not reported as passed. Full mobile typecheck, beta suite, backend TestClient/SQLite execution, Android build and device tests remain required.

## Native Expo push implementation — 2026-11-17

The SDK 54 compatibility table in Expo's `sdk-54` branch confirms:
- `expo-notifications ~0.32.17`
- `expo-constants ~18.0.14`
- `expo-application ~7.0.8`

The mobile manifest and npm lock now include the notification package and its dependency closure. `expo-notifications` is registered as an app config plugin. The dynamic `app.config.js` reads the non-secret `EXPO_PUBLIC_EAS_PROJECT_ID` build variable; no project ID was invented or committed because this repository's app config did not contain one.

Native behavior now includes:
- An explicit **Profil > Cihaz Bildirimleri** setting. No permission is requested during login, onboarding, app startup or background refresh.
- Project-ID preflight before requesting OS permission. If the EAS project ID is missing, the setting explains the blocker and does not prompt.
- A UUID installation identifier in SecureStore. Expo push tokens are sent directly to the authenticated API and are not persisted locally or written to logs.
- Token refresh only for a user who previously opted in, on session restore and app foreground; no polling timer.
- Android default notification channel and a foreground banner/list handler. Foreground sound and OS badge mutation are disabled.
- Response listeners plus cold-start response lookup. Only the server's two existing payload shapes are accepted: `{kind: "notification", notice_id}` and `{kind: "consultation", case_id}`.
- A notification tap fetches the exact active notice by ID through the owner-scoped API before the existing web-path allowlist opens its native target. A consultation tap opens the existing case screen, whose API still enforces participant ownership.
- Logout revokes only the current account/device registration before clearing the session. If the network prevents revocation, the user is warned before choosing to force logout.
- Backend registration validates UUIDv4 device IDs and Expo token shape, rejects cross-account token reuse, serializes same-account updates, caps each account at 10 devices and maps unique-index races to HTTP 409.
- Notification list, read, read-all and push-device endpoints return `private, no-store` responses. The optional `notice_id` lookup includes an older notice only when it is active and belongs to the authenticated user.

Push payloads remain generic. The server sends no patient name, case text, message preview or clinical details; only a generic title/body and the allowlisted numeric routing IDs are included.

## Tests and verification boundary

Committed tests now also include:
- `tests/test_mobile_push_registration.py`: UUID/token validation, cross-account token conflict, owner-only unregister, same-device token replacement, ten-device cap, no-store headers and owner-scoped lookup outside the 20-item page.
- `mobile/tests/notificationTargets.cjs`: strict Expo payload routing and malformed/unsafe identifier rejection.
- `mobile/tests/notifications.cjs`: SDK dependency/lock, app plugin, explicit opt-in, no token logging, logout revocation and foreground refresh wiring.

The lockfile was updated, but `npm ci` has not been executed in this environment. The Actions jobs on the current PR head still have empty step arrays and their logs return `BlobNotFound 404`; npm, TypeScript, Node, pytest and Gradle did not start. These tests are committed and included in the mobile/security workflows, not reported as passed.

## Remaining acceptance and external configuration

- Supply the real EAS project ID as `EXPO_PUBLIC_EAS_PROJECT_ID` in the mobile build environment. Until then, native push intentionally remains disabled and does not ask for permission.
- Configure Android FCM v1 and iOS APNs credentials for the EAS project, then set the server-side `MOBILE_PUSH_ENABLED=true` only after the owner approves activation. The current backend sender is disabled by default; no production environment was changed.
- Run `npm ci`, TypeScript typecheck, beta Node tests, backend TestClient/SQLite tests, Android prebuild/APK and iOS prebuild in a functioning runner.
- Validate real-device permission denial/recovery, Android channel presentation, iOS presentation, token rotation, duplicate tap/cold-start handling, logout, account switch, expired sessions, offline revocation and EAS delivery receipts.
- The explicit native read-all button remains a deliberate UX choice; compare it with web auto-read-on-open during product acceptance.
- No main merge, production deployment, APK/IPA publication, migration or patient-record mutation was performed.
