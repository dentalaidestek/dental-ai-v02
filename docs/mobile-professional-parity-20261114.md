# Native professional profile and verification adaptation

Continues PR #257 / issue #258. Source baseline `1f511982`; concurrent patient validation and duplicate-write regressions through `2574170a` are retained. No production backend deployment, main merge, store publication or replacement APK.

## Confirmed missing behavior

`NativeAccount` exposed professional title, university and specialty as static text. The web account has separate expandable professional/document and expert-management sections with distinct membership, expert-credential and title-change review authority. The native account lacked those mutation/document flows and own-expert editing/navigation.

The adaptation reads the existing account, profile-verification summary, expert profile and rules templates. It invokes the canonical web handlers rather than duplicating their lifecycle rules. `mobile_professional_api` exposes JSON/multipart adapters; it does not grant a new role or auto-approve documents.

## Mapping

| Web action / state | Native implementation |
|---|---|
| Mesleki durum ve belgelerim | Separate expandable account section, existing server title choices, current title and native explicit second confirmation |
| Verified expert title replacement | Existing identity stays active; requested title has AWAITING_DOCUMENT / PENDING_REVIEW / REJECTED states, rejection reason and document resubmission |
| Membership verification | Same document types, explicit ownership consent, 5 MB PDF/JPG/PNG upload and NONE/PENDING/VERIFIED/STALE/REJECTED state |
| Expert credential replacement | 10 MB document, canonical review transition, specialty approval reset and new-case intake made PASSIVE |
| Uzman profilim | Separate account heading, eligibility explanation, application/review state and existing public-profile navigation |
| Expert application / editing | Phone, specialty, institution, bio, price, ORCID identity and legacy publication statement; same photo/document requirements and server minimum price |
| Sensitive profile edit | Canonical specialty/title/document changes reopen review and close intake; non-sensitive edits retain the existing availability |
| Availability | Canonical AVAILABLE/BUSY handler, verification/phone/current-rules/policy/capacity checks; a profile edit does not overwrite newer availability |
| New-case rules | Text extracted from the existing web rule-card sections, current version from backend, explicit checkbox consent; stale-version acceptance rejected |
| Shared profile changes | Account identity reload after confirmed mutation, foreground/realtime refresh when drafts are closed, own-public-profile route |

ORCID identity is not publication ownership verification. The legacy publication statement remains user-declared content. Structured publication tabs, DOI matching/import and ORCID synchronization are still separate outstanding work; the text field does not complete those features.

## Data and failure behavior

Account ownership comes from the existing bearer session and admin MFA guard; clients cannot choose another user. Responses omit storage paths and private credential bytes. Server-side signature/document parsing rejects spoofed PDFs/images before invoking the relevant web uploader. Membership consent and duplicate pending-review guards remain server-authoritative. Native file-type/size checks are preliminary; backend checks remain mandatory.

Reads and mutations are scoped to the active token. Ref locks guard repeated taps; unknown/time-out/server outcomes freeze automatic resubmission and offer a server-state check. Definite validation errors retain editable fields. Pending writes guard native navigation; the parent accordion/sign-out actions receive the busy state. Selected credential cache copies are deleted when replaced, after successful submission, or on unmount if they belong to the app cache. This is not a durable OS-kill cleanup or encrypted-draft guarantee.

Canonical database work and document parsing are offloaded from async adapter handlers. No patient, token, password, message or image logging was added. The canonical storage/review workflows retain their existing concurrency and idempotency limitations; no new atomic upload receipt is claimed.

## Concurrent TypeScript correction

The latest concurrent patient fix used `Number.isInteger(status)` before comparing an optional `status >= 500`. TypeScript does not narrow `number | undefined` with that call; the local compiler reproduced TS18048 at NativePatientProfile line 11. An explicit numeric-type check fixes narrowing while preserving its validation-versus-uncertain-write behavior. All four concurrent patient/treatment regressions are retained.

## Verification

- Seven native component/API cases exercise second confirmation, account-switch isolation, malformed responses/file limits, actual expert form payload and write lock, rules consent, actual document picker/ownership consent/cache cleanup, and separate web account headings.
- Six backend cases exercise title identity preservation/document review, membership ownership/consent/no expert grant, real expert application and sensitive edits, authentication/invalid titles, availability/current-rule acceptance, and expert-document re-review/intake closure.
- `npm --prefix mobile test`: TypeScript passed; **229 Node tests passed, 0 failed** (18 session, 46 realtime, 165 beta), including the four retained concurrent patient/treatment regressions.
- Selected Python account/program/patient/boot/chat/request/admin/security/social suite: **203 passed, 0 failed**; 342 deprecation warnings.
- Bare `pytest -q` was also run. The initial workspace snapshot lacked several existing web templates and browser/PostgreSQL fixture modules; they were restored unchanged from GitHub, and the missing Playwright Python dependency was installed locally. Browser launch is still blocked in this environment by `socket() failed: Operation not permitted`; no test assertion was weakened or removed.
- Remaining full-suite browser cases: `test_mobile_profile_composer_publication_and_member_flow` at 360/390/430/1280; `test_four_images_upload_reorder_offline_retry_and_pending_visibility`; `test_management_inline_editor_tabs_and_settings`; `test_following_page_loads_one_feed_with_working_member_actions`. PostgreSQL cases without a configured test database are skipped. The final complete run: **256 passed, 7 failed, 5 skipped**, 554 deprecation warnings. Six failures are Chromium socket-permission launch errors; the relationship browser case expects a missing `/tmp/chromium`. These browser assertions did not execute; the full suite is not green.
- Android/iOS Expo-Hermes JS exports succeeded after the final concurrent-source update. They are not native signed builds or device acceptance.

## Remaining acceptance

The new backend adapters are not deployed, so this source work does not change the installed APK. No authenticated production document/admin review, actual push delivery, physical Android/iOS form/file-picker/back/background/keyboard acceptance, two-device concurrent edit or load test. Remote GitHub jobs continue to fail before exposing steps; check-run annotations exist but annotation retrieval is unavailable through the connector and job-log storage returns BlobNotFound404. The remote CI root cause is not confirmed.

Full P0–P3 scope remains in `mobile-web-parity-tracker-20261114.md`. The next source gaps include structured expert publication management/public profile tabs and the full clinical AI/voice/academic flows. P0 release/session/API/device/CI acceptance remains open. No module is certified fully complete by these local tests.
