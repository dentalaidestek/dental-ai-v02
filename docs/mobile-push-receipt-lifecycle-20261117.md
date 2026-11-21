# Native Expo push receipt lifecycle — 2026-11-17

## Web-first parity and discovered gap

The browser path in app/templates/base.html, its Web Push subscription endpoints, and app/static/push-sw.js was compared with the native path:

NativePushSettings -> nativePush.ts -> POST /api/mobile/v1/push/devices -> RealtimeEvent publication.

Native device registration already had account ownership, logout revocation, a 10-device cap, generic notification text, and a safe deep-link payload. The server transport in app/mobile_push.py only counted successful tickets, however. It discarded ticket IDs, never called Expo's receipt endpoint, and therefore could not retire tokens reported as unregistered by APNs/FCM.

## Implemented lifecycle

- send_push_tokens sends no more than 100 messages per request and 1,000 unique tokens per invocation. Each HTTP request has an eight-second timeout.
- Safe ticket metadata contains only a SHA-256 token fingerprint, status, Expo ticket UUID, and allow-listed error code. Ticket message text and raw Expo tokens are not returned or persisted.
- A unique (event_id, device_id) key reserves one send per realtime event/device. Replayed events do not send a second notification to a device.
- Ticket-level DeviceNotRegistered immediately disables only the same current device/token pair.
- Successful tickets are checked after 15 minutes, following Expo's recommendation. Receipt lookup batches are capped at 1,000; the worker currently claims at most 100 per pass.
- A receipt with status=ok is recorded as PROVIDER_ACCEPTED, not “delivered”: Expo defines this as FCM/APNs accepting the handoff, not proof that the device displayed it.
- Receipt-level DeviceNotRegistered disables the device only if its current token fingerprint still matches the ticket. A stale receipt cannot disable a token that has since rotated.
- Missing receipts are retried with bounded exponential intervals and expire no later than the 24-hour Expo receipt retention window. Terminal records are pruned in batches after 30 days.
- An ambiguous send timeout is recorded as SEND_UNCERTAIN and is not automatically resent: Expo may have accepted the first request before the connection timed out, so a retry could duplicate the notification.
- Receipt polling and cleanup run inside the existing app.work_worker loop. Render's current runtime group sets DENTAL_WORK_EXECUTION=embedded; no additional timer, service, provider, or queue was added.

## Data minimization

The additive MobilePushDelivery table stores event/user/device IDs, a one-way token fingerprint, Expo ticket UUID, state, bounded error code, attempt count, timestamps, and a short worker lease. It does not store patient names, clinical text, notification title/body, route payload, or the raw Expo token.

app/migrate.py ensures this table for existing revision-15 databases using a separate PostgreSQL advisory lock and a ten-second DDL lock timeout. The revision number remains 15. This migration has NOT been run against production.

## Configuration

The Render manifest now declares, without values:

- MOBILE_PUSH_ENABLED — set to true only when native push delivery is intentionally enabled.
- EXPO_ACCESS_TOKEN — set only when Expo Enhanced Push Security is enabled for the project.

No secret value is committed. Push remains disabled when MOBILE_PUSH_ENABLED is absent or false.

## Regression coverage

- Transport tests cover 100-message batches, 1,000-token bounds, eight-second timeouts, safe ticket metadata, receipt UUID validation, 1,000-receipt limit, bearer auth, HTTP rejection, and ambiguous timeout handling.
- Receipt tests cover event/device deduplication, ticket persistence, ticket-level invalidation, receipt success semantics, receipt-level invalidation, token rotation safety, missing-receipt backoff, 24-hour expiry, disabled delivery, definite HTTP rejection, and revision-15 schema bootstrap.
- The new module and tests are included in the Security recovery workflow's path filter and pytest command.

## Validation and release gate

GitHub source-contract checks were performed against the final branch files. The repository's pytest/Node/TypeScript/Gradle suites have not run in this automation environment because current GitHub Actions jobs fail before allocating a runner (runner_id=0, empty steps, and log downloads return BlobNotFound 404). No green CI is claimed.

Still required: actual pytest execution, PostgreSQL concurrent-reservation/lease tests, one Android and one iOS physical-device push test, token rotation/uninstall observation, Expo project credential verification, and production-equivalent event-rate testing. This does not certify 60,000 concurrent users or end-device delivery.

No main merge, production deploy, migration execution, APK/IPA publication, or patient-record mutation was performed.

## External contract

Expo recommends checking receipts after 15 minutes, limits each receipt request to 1,000 IDs, and clears receipts after 24 hours. A DeviceNotRegistered ticket/receipt should stop future sends to that token. See the Expo Push Service documentation: https://docs.expo.dev/push-notifications/sending-notifications/
