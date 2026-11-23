# Native Expo push receipt verification — 2026-11-17

This change hardens the existing receipt lifecycle; it does not introduce a second worker, timer, provider, or notification-content store.

## Web contract reviewed first

The web reference remains `app/templates/base.html`, `app/static/push-sw.js`, and the authenticated `/account/push/config`, `/account/push/subscribe`, and `/account/push/unsubscribe` routes. Web and native delivery keep generic lock-screen copy. Patient names, diagnoses, message bodies, and clinical attachments are not sent in Expo payloads.

Native delivery is owner-scoped to `MobilePushDevice.user_id`; the server-authored route contains only a notification or consultation identifier. The recipient API still performs authorization when the app opens the route.

## New failure cases covered

- A malformed or missing legacy receipt ticket is terminalized as `RECEIPT_ERROR/INVALID_TICKET` before provider I/O. It can no longer poison a batch of otherwise valid UUIDs.
- A missing `SENDING` lease becomes `SEND_UNCERTAIN`; it is not resent because the external request may already have reached Expo.
- A missing `CHECKING` lease returns to bounded receipt retry. Receipt lookup is read-only and safe to retry.
- Boolean values are rejected as poll limits even though Python treats `bool` as a subclass of `int`.
- Provider transport tests cover UUID deduplication, unrequested/malformed response keys, HTTP 429, timeout, and invalid top-level data.
- PostgreSQL integration tests coordinate two workers to prove one event/device reservation and that a second receipt poll skips a row locked by the first worker.

## Verification commands

The repository's existing workflows already include the relevant suites:

- `python -m pytest tests/test_mobile_push.py tests/test_mobile_push_receipts.py -q`
- `DENTAL_TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_postgres_optimization.py -q`

The PostgreSQL fixture creates a unique disposable schema and drops it after each test. The GitHub Security Recovery workflow provisions PostgreSQL 16 and runs the PostgreSQL optimization suite separately.

## Acceptance boundary

The PostgreSQL concurrency tests are committed but must execute on a real PostgreSQL 16 service before the locking behavior is marked verified. Mocked Expo HTTP tests verify request/response handling only; they do not contact Expo or prove APNs/FCM device delivery. No clinical records are created or changed by these tests.

No production migration, deployment, APK/IPA publication, or main-branch merge is part of this work.
