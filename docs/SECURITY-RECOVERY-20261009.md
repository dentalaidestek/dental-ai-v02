# Security and privacy recovery — 9 October 2026

Base: `mobile/native-android-current` at `0427ccf3ffaf9ba837cbb404d2c0fca7b21f749c`.
Work branch: `work/security-privacy-recovery-20261009`.
No production deployment or modification of the original mobile branch.

## Verified findings and fixes

- Native restore deleted the token after every network/API error. Restore now deletes it only on HTTP 401. Transient errors retain the token and show a retry screen without opening protected screens.
- The clinical router calculated redacted copies but sent original fields. It now uses the redacted fields. Label matching supports tabs and preserves subsequent clinical lines.
- All clinical provider payloads now remove direct email, Turkish mobile phone and 11-digit identity tokens, including embedded structured vision text. Response schemas and image pipeline are unchanged.
- Registration referenced an undefined `login_key`, returning 500 after account creation. Removed that misplaced failure-reset call.
- Rate limit branches referenced an unimported `HTTPException`. They now return the intended HTTP 429.
- An expired/exhausted email verification challenge permanently blocked login. Explicit credential-verified renewal replaces unusable challenges; normal login does not resend, and a usable challenge is reused without another email. Web/native interfaces permit returning to login. Successful verification remains single-use and revokes earlier sessions.
- Verification and renewal use the same user-before-challenge lock order. Verification also checks challenge token identity, active state and current verification state.
- Socket authentication accepted unverified users. It now enforces the same verification requirement as HTTP/native sessions.
- Web verification dropped the intended destination. It now preserves only destinations accepted by the existing safe-redirect validator.
- Rejected/empty direct anatomy uploads could leave temporary image bytes on disk. Cleanup identity is assigned immediately after file allocation.

## Regression and build validation

- Security, identity recovery, account operations and web-push tests passed locally: 76 tests in the combined suite, plus two subsequently added endpoint-level login recovery cases (78 total).
- Native TypeScript check and seven behavioral session/API tests passed.
- Android Metro/Hermes export completed successfully (842 modules). This is a JS bundle export, not an APK or physical-device test.
- Python web dependencies used the repository's locked FastAPI, Starlette, SQLModel and SQLAlchemy versions. Local test environment is not claimed to be identical to Render.
- Existing security tests had brittle whole-file/formatting assertions and unverified authenticated fixtures. Updated their scope/fixtures without reducing the verification gate. Added actual prompt, outgoing request, upload cleanup and identity lifecycle tests.
- TypeScript was missing from mobile dev dependencies. Added it; Expo selected SDK 54-compatible SecureStore and its config plugin. Added a package lock and session tests to mobile CI, plus a dedicated backend security regression workflow.

## Remaining limits and priorities

- Previous Codex snapshots remain unavailable. The handoff follow-up recovered the original CI log containing 29 failing tests; see SECURITY-REMAINING-20261009.md. This is not a current count of distinct security vulnerabilities.
- Regex minimization does not guarantee full anonymization: unlabeled names, addresses, uncommon telephone formats and re-identification from clinical context need a separate provider-data audit. Academic provider and stored records were not comprehensively audited here.
- PostgreSQL concurrent race/deadlock behavior, actual Brevo delivery and Render migration behavior require integration validation. Local SQLite tests do not prove row-lock behavior.
- No physical-device APK test, end-to-end realtime audit, complete E2EE integration audit or account-erasure retention audit was performed in this batch.
- Before any production merge: validate those integration boundaries and triage the remaining PR #60 mobile/data-integrity findings against current code.
