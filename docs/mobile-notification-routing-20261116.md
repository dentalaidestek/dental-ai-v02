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

- Added `POST /api/mobile/v1/notifications/read-all` with bearer-authenticated owner scope.
- The endpoint accepts a client-captured `seen_before` timestamp, normalizes offset-aware values to UTC, clamps future values to server time, and marks only active unread notices created at or before the cutoff.
- Existing `read_at` values are preserved. Notices created after the cutoff, resolved notices and another user's notices remain untouched.
- A durable `NOTIFICATIONS_READ` realtime event is recorded only when at least one notice changes. Replaying the same cutoff is idempotent and emits no second event.
- Added the native API adapter and a pure local snapshot helper so the list only optimistically reads items at or before the same cutoff.
- Added an explicit “Tümünü okundu işaretle” action. It does not mark notices read merely because the user opened the native screen; this keeps the action deliberate while preserving the web cutoff semantics.
- Home refreshes its unread badge when it regains focus, and the notification list reconciles `NOTIFICATIONS_READ` events.
- Removed the premature Android OS permission request from the first-run notice. It now explains that in-app notices are available while native Expo push registration and killed-app routing are not yet integrated. No OS permission is requested until that feature can actually register a device.
- Added backend ownership/cutoff tests, native state/UI tests, and security workflow path/test coverage.

## Tests and verification boundary

Committed tests:
- `tests/test_mobile_notifications.py`: owner isolation, active-status filter, cutoff boundary, newer-notice preservation, unauthorized request, invalid timestamp and idempotent replay.
- `mobile/tests/notifications.cjs`: cutoff snapshot, already-read preservation, invalid cutoff, native API/UI wiring, Home focus refresh and no premature OS permission prompt.

The GitHub Actions jobs inspected at the starting PR head had empty step arrays and no runner assignment; npm, TypeScript, Gradle and pytest did not start. The new tests are committed and registered but are not reported as passed. Full mobile typecheck, beta suite, backend TestClient/SQLite execution, Android build and device tests remain required.

## Remaining acceptance

- Add the Expo SDK-compatible `expo-notifications` dependency and native config only when the lockfile can be generated with `npx expo install` and verified on Android/iOS.
- Register Expo tokens only after an explicit user action and real OS permission grant; keep device ID in SecureStore, token out of logs, and revoke only the current account/device on logout.
- Add notification-response listeners for foreground/background/killed-app launches and route only the known same-origin target types through the existing resolver. Push payloads must remain free of patient names, case content, message previews and clinical data.
- Validate duplicate delivery, token rotation, account switch, logout, expired/revoked sessions, permission denial, offline retries and cross-device unread reconciliation on physical devices.
- The explicit native read-all button is a deliberate UX choice; compare it with web auto-read-on-open during product acceptance.
- No main merge, production deployment, APK/IPA publication or patient-record mutation was performed.
