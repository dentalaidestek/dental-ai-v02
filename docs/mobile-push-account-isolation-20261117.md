# Native push account isolation — 17 Nov 2026

## Web flow reviewed first

Re-read `app/templates/base.html`, `app/templates/account.html` and `app/static/push-sw.js`. The web account page only requests browser permission after an explicit user action, posts the browser subscription to the authenticated account route, and removes that subscription on opt-out. The service worker keeps the notification generic and validates same-origin navigation. The native account screen already used an explicit opt-in, but its installation identity was not reconciled on every account login.

## New findings

1. The native sign-out path allows the user to continue after a failed server-side unregister. The session token is then discarded, so the old account's device row can remain enabled until it is explicitly removed.
2. The login effect only refreshed push registration when the current account had previously opted in. A new account on the same installation therefore did not revoke the previous account's stale registration.
3. Registration rejected an Expo token owned by another account even when the request came from the same stable installation. A token rotation plus a failed logout could leave multiple account rows associated with one installation identity.

## Changes

- Added a per-installation 256-bit random proof in Expo SecureStore. The raw proof is never sent to logs or stored server-side; the API stores only its SHA-256 hash on `MobilePushDevice`.
- Added authenticated `POST /api/mobile/v1/push/devices/claim`. It runs on every authenticated native login, even when the new account has not enabled notifications. It revokes previous-account registrations for that installation without asking for OS permission or registering a new Expo token.
- New-format rows require a matching installation proof before another account can claim the installation. Pre-proof legacy rows (`device_proof_hash IS NULL`) can be migrated using the existing UUIDv4 installation ID retained by the old client.
- Registration now transfers same-installation rows after proof validation. An Expo token still owned by a different device remains a conflict; the endpoint does not let a caller steal a token from another installation.
- PostgreSQL claim and registration operations share a transaction-scoped advisory lock derived from the installation UUID. This serializes account changes across app instances. The client also serializes its own claim promises so a delayed request from an old session cannot finish after a newer account's claim.
- Added an additive nullable column to the existing revision-15 compatibility migration. The schema revision remains 15; no production migration was run.
- Native claim does not enable push, request notification permission, fetch an Expo token, or add polling. Existing generic notification payloads and deep-link authorization are unchanged.

## Regression coverage added

- Previous-account row is removed on a new login claim before optional opt-in.
- Wrong installation proof cannot remove the current owner's row.
- Legacy proof-less row can be migrated by the retained UUIDv4 installation ID.
- Claiming one installation leaves another installation untouched.
- Invalid proof, UUID and token ownership cases are rejected.
- Existing revision-15 device table gains the nullable proof-hash column without a revision bump.
- Native tests assert login claim ordering, SecureStore proof generation, and that claim does not request OS permission or enable notifications.
- PostgreSQL 16 test verifies two transactions cannot acquire the same installation advisory lock concurrently.

## Validation and limits

The tests are committed and wired to existing Android/Security workflows, but they are not claimed as passing until a runner executes them. At the starting head `ae5d6141`, Android typecheck and Security Recovery jobs ended before any step: job step arrays were empty, runner metadata was absent, and log downloads returned `BlobNotFound 404`. No TypeScript, Gradle, pytest or PostgreSQL command ran in those jobs.

The proof is an app-private installation secret stored by SecureStore, not hardware attestation. Legacy rows are less strongly bound because they predate the proof column; their UUIDv4 identifier is used for the one-time upgrade path. If SecureStore is wiped and the installation UUID is lost, the old server row cannot be safely claimed automatically.

No main merge, production deploy, production migration, APK/IPA publication, or clinical-record mutation.
