# Pending web profile email change

This work is on `work/logout-history-20261009`. It has not been deployed.

The personal-information section accepts a new address and current password. A
hashed six-digit challenge expires after ten minutes and permits five failures.
Only the initiating authenticated session can confirm. Refresh preserves the
pending screen; explicit resends have a shared three-per-ten-minute limit.
Failure, expiry, exhaustion and delivery failure leave the old address usable.
No polling, AI calls, paid service or runtime dependency was added.

Completion rechecks active session, account/password state, mailbox occupancy and
the deleted-account blocklist under transaction locks. Registration and email
completion use the same canonical-mailbox PostgreSQL advisory lock, without
serializing unrelated addresses. Completion removes all web/native session
records, old password-reset links and old expert-device authentication grants.
E2EE public keys and clinical records remain intact. Account erasure removes any
pending change, including its old/new address and verifier fingerprints.

Before publication run `python -m app.migrate` using the release migration
process. Revision 10 adds `emailchangechallenge`; do not start this release
against revision 9. The SQLite migration is tested twice with existing user
records retained. PostgreSQL migration and concurrent-confirmation tests are
included in security CI, but have not been executed in this local environment:
PostgreSQL is unavailable and its installation was blocked by local privileges.
Real Brevo delivery, physical-device UI and PostgreSQL concurrency remain release
validation requirements. Existing verification codes use the current Brevo
sender; no actual email was sent in local tests.

The web settings implementation is complete. This does not add a native Android
email-edit screen, old-address security alert/reversal workflow or email-provider
account recovery when the user has forgotten their password.
