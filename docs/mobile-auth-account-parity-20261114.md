# Native authentication and account adaptation

Continues the original mobile completion task, branch `feature/mobile-web-parity-20261110`, PR #257 / issue #258. Base inspected: `26710927f1ac50da5debafd7ea0fca115355ea98`; concurrent patient/media/schedule fixes retained. No main merge, production deploy or store publication.

## Root causes and implementation

The native login's Üye Ol action opened `/register` in the browser; there was no native registration/recovery form. Profile was a read-only summary with shortcuts and no username/name/photo/password/email editing. Saving profile data also had no callback to update the main app's current user.

`NativeAuth` now handles login, native registration, email-code verification, forgot password and password reset. It includes show/hide password, autofill hints, legal-text viewing, explicit consent controls, keyboard scrolling and Android back handling. The only stored credential remains the confirmed session token in SecureStore; registration and OTP state/passwords remain in memory. It verifies `/me` before storing a successful token.

`mobile_account_api` delegates mutations to the existing web handlers rather than duplicating account security/business rules. Registration retains web admission rate limiting, title/specialty rules, fixed DOCTOR role, username/email uniqueness and all three versioned agreement records. The unused browser session minted by the canonical registration handler is revoked before returning a native verification challenge. No native session is issued before successful email verification. Stale legal versions are rejected before creating the user.

Recovery retains the web's generic existing/missing-account response, hashed single-use 30-minute token, password confirmation and revocation of old sessions. The native reset form accepts a validated `https://dentalai.tr/reset-password` link pasted from email, and the existing custom app scheme can route to it while the unauthenticated UI is mounted. Production email links remain HTTPS. Universal/App Link association and signed-in link handling are not certified.

`NativeAccount` has expandable Personal Information, Professional Information, Account Security and Email sections. It supports name, username, private profile-photo selection/upload, current-password-protected password change and code-confirmed email change. A successful identity update refreshes the main app's current user. Revoking changes notify the existing session-expiry boundary so clinical screens and credentials are cleared and login returns. Read-only professional fields come from actual account data; professional-title/document verification editing remains unfinished.

| Rule | Preserved behavior |
|---|---|
| Username | Existing 15-day change cooldown, including its HTTP 429 response |
| Password | Requires current password; minimum/confirmation checks; all sessions revoked |
| Email | Current password and same-session code; attempts/expiry and uniqueness rules; old sessions/recovery credentials revoked |
| Admin | Fixed mailbox cannot change; new account adapters require the existing web AdminVerifiedSession authority and do not mint MFA claims |
| Photo | Existing web sanitizer/crop/storage; own-photo native retrieval, bearer authorization and private/no-store; wrong-user retrieval rejected |
| Consent | Current web text/version, three explicit acknowledgements; no prechecked consent |

## Validation

- TypeScript passed; **211 Node tests passed / 0 failed** (18 session, 46 realtime, 147 beta).
- Selected Python boot/patient/upload/chat/request/admin/account/security/social suite: **192 passed / 0 failed**, 291 deprecation warnings.
- Five new backend cases validate consent/title/role/OTP, username cooldown and password revocation, generic single-use recovery, session-bound email change and admin MFA/fixed-email/private-photo rules. Canonical handlers execute; a minimal template-response fixture supplies their contexts without claiming browser-rendering coverage.
- Four new mobile cases exercise actual native signup through OTP and SecureStore, safe reset-link parsing, account identity refresh/session expiry, and rejection of arbitrary photo URLs/premature registration credentials.
- Android and iOS Expo/Hermes exports succeeded. No dependency changes were needed; native prebuild/build/signing/device testing was not repeated for this change.
- CI is checked after push and recorded on PR #257 / issue #258. Local passes do not certify remote CI.

## Open acceptance

No authenticated production account creation, real email delivery, physical Android/iOS, OS autofill, background/deep-link handoff, release APK/IPA, load test or store acceptance was performed. Backend adapters are not deployed. The installed APK does not receive these functions from a source commit.

Native admin MFA entry, full professional/document/expert verification, academic publication/profile functions, detailed active-session management and the rest of the original module criteria remain open. Email verification is not a claim that every web two-factor flow has been ported. See the master tracker for all modules.
