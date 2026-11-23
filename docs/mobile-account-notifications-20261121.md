# Native account and notification parity — 2026-11-21

## Baseline CI: commit 8325c3a0e7cc74418583278104b95658eb4631ac

- Android typecheck passed.
- Session/auth and realtime/pagination passed.
- Beta: 936/937. The failing support cursor test expected an unencoded `before_id` concatenation while the client encodes the cursor. The branch test was aligned to the actual URL-encoded contract; no production validation was weakened.
- Android internal APK and Android/iOS Expo exports completed.
- Security Recovery: native social, academic, clinical, voice and program jobs passed; native support failed 18/19 and Python security failed 568/570.

## Root causes corrected in test fixtures/contracts

1. Native support cursor regression assertion now checks the URL-encoded cursor argument rather than a literal unescaped concatenation.
2. The admin support API test previously created a role=ADMIN session without the fixed admin email and second-factor verified-session record. Production `_admin_only` correctly returned 403. The fixture now creates the same verified admin session required by production; authorization was not relaxed.
3. The migration test expected schema revision 13, but the current serialized migration has support receipts at revision 14 and the global revision at 20. The test now asserts the named constants and current revision alias.

## Native account/push lifecycle change

All push registration mutations for a physical installation now share one promise queue:
- login installation claim
- explicit push enable
- foreground token refresh
- explicit disable
- logout revocation

Logout revocation therefore waits behind any earlier claim/refresh and runs before the app discards the session. This closes a race where an in-flight claim could finish after logout's unregister request and re-bind the device to the signed-out account. The queue is per app process; server-side ownership and installation proof remain authoritative.

## Notification center behavior

- Notification list refreshes now follow the web notice event policy: `NOTICE_CREATED`, `NOTICE_RESOLVED`, and `NOTIFICATIONS_READ`.
- Chat/consultation events no longer trigger a full AdminNotice list fetch.
- Concurrent refresh requests are coalesced into one in-flight request plus one trailing reconcile, matching the web center's single-flight behavior.
- Existing account token/request-generation checks, cutoff-based mark-all semantics, and server-authoritative unread counts remain intact.
- Push payload routing continues to accept only known minimal server-authored target shapes; notification and consultation IDs are validated before navigation.

## Files changed in this pass

- `mobile/src/nativePush.ts`
- `mobile/src/ModernScreens.tsx`
- `mobile/src/notificationRefresh.ts`
- `mobile/tests/notifications.cjs`
- `tests/test_mobile_support_api.py`

## Validation boundary

Changes are on `feature/mobile-web-parity-20261110` only. The new head requires Android and Security Recovery CI to execute before any green claim. No local tests are claimed. No main merge, production deploy, migration execution, or patient/account data mutation was performed. A 60,000-user load test and real-device two-account push/logout acceptance remain open.
