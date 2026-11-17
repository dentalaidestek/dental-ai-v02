# Native Expo push receipt hardening — 17 November 2026

## Scope

This follow-up reviewed the existing web push flow in `base.html`, `push-sw.js`, the account subscribe/unsubscribe routes, and the native Expo event delivery path. The existing durable receipt pipeline was already present; this change set addresses a stale device-snapshot race and the bounded throughput needed to keep receipt/terminal rows from accumulating as opted-in device count grows.

No clinical notification copy, provider credentials, patient data, deployment configuration, or production records were changed.

## Findings and changes

### 1. Revalidate device consent at reservation time

The event dispatcher first reads enabled `MobilePushDevice` rows, closes that session, then reserves delivery rows. Previously, reservation trusted the detached ORM objects. A user could disable push or rotate the Expo token after the first SELECT but before reservation; the stale snapshot could still create a send reservation.

Reservation now treats the supplied rows only as candidate device IDs. In its own transaction it re-queries by both `user_id` and candidate `device_id`, requires `enabled = true`, locks the current rows with `FOR UPDATE SKIP LOCKED`, and fingerprints/sends the current token. A stale disabled device is skipped; a rotated token is used instead of the old token. The existing unique event/device key remains the cross-process replay guard.

This closes the stale-snapshot window before reservation. It does not claim to make an external provider call and a concurrent logout one atomic transaction; the network call necessarily occurs after the reservation transaction commits.

### 2. Keep receipt polling bounded but raise the queue drain ceiling

The provider helper already accepts up to 1,000 receipt IDs per request. The worker previously polled only 100 tickets per minute. The bounded worker batch is now 500, still below the provider helper's 1,000-ID cap. At one successful poll per minute, this is a theoretical ceiling of 720,000 receipt lookups/day; actual throughput depends on provider latency, worker availability, and backlog.

### 3. Prevent terminal-row retention backlog

Terminal cleanup previously removed at most 100 rows every five minutes (28,800/day). At 60,000 accounts with multiple opted-in devices, that could lag behind terminal delivery creation. Cleanup now processes at most 1,000 rows per state bucket per maintenance pass, with an explicit upper bound and no unbounded delete. Terminal retention remains 30 days. This gives a theoretical terminal cleanup ceiling of 288,000 rows/day.

The worker still uses the existing queue loop: receipt polling at most once per 60 seconds and maintenance at most once per 300 seconds. No additional timer, service, or polling loop was introduced.

### 4. Delivery semantics and privacy

- Expo ticket acceptance remains `PENDING_RECEIPT`; an `ok` receipt becomes `PROVIDER_ACCEPTED`.
- Provider acceptance is not represented as proof that a notification was displayed on a device.
- `DeviceNotRegistered` disables a device only if its current token fingerprint still matches the delivery row.
- Delivery rows store event/device IDs, one-way token fingerprint, Expo ticket ID, bounded status/error code, attempts and lease timestamps only.
- No raw token, title, body, route payload, patient name, diagnosis, or clinical note is stored in the receipt table.
- Ambiguous send timeouts are not automatically resent, avoiding duplicate pushes.

## Regression coverage added

- stale pre-opt-out snapshot cannot reserve a push;
- token rotation between initial lookup and reservation uses the current token;
- duplicate candidate IDs create one delivery and another user's device is ignored;
- terminal cleanup deletes at most the configured 1,000 rows per bucket/pass;
- cleanup rejects a caller-supplied batch above its hard limit;
- receipt polling rejects more than 500 IDs in one worker pass;
- the existing worker cadence test verifies receipt polling is not run on every queue iteration.

The Security Recovery workflow already includes both `app/mobile_push_receipts.py` and `tests/test_mobile_push_receipts.py` in its path filter and pytest command, so no extra workflow trigger was needed.

## Validation and remaining gates

Source changes and regression tests are committed on `feature/mobile-web-parity-20261110`. The GitHub Actions jobs observed on the preceding head failed before any step was created: job records had no runner/log/steps, and the run had no usable artifacts. This is an Actions execution/runner allocation problem, not evidence that the Python or Android tests passed or failed. The new head must still complete the Android typecheck/APK and Security Recovery workflows before this work is considered CI-verified.

Still required: PostgreSQL execution of the `SKIP LOCKED` reservation path, a real Expo sandbox ticket/receipt round-trip, device opt-out/token-rotation tests on Android and iOS, and a sustained load test using the deployed worker topology. No main merge, production migration, live deploy, APK/IPA publication, or clinical-record mutation was performed.
