# Dental AI native beta — audit and delivery ledger

Baseline: GitHub main `979b51c572eca6d510f517ce2572c80045780ba0`. PR #60 merged; #61 hardened native recovery/security. Comparing #60 head to main shows 321 later commits and no mobile file changes. `feature/mobile-social-voice-20261108` changes responsive web, not React Native.

## Existing state, before this branch

| Module | Usable code | Missing / unverified |
|---|---|---|
| Authentication | SecureStore, login, six-digit email verification, revoked session restoration | Registration, foreground expiry UX, remote logout retry, physical devices |
| Patients | Create, search, detail, photos, adult/primary FDI surface/status chart | List stops at first 30; silent errors; no anamnesis editor; no 3D gestures |
| AI | Native gallery, patient-bound multipart intake, durable WorkJob, websocket refresh | Camera, accessible history results, upload progress, persisted selected job, confidence filtering |
| Dental Akış | Existing web moderation, idempotency, versioned edits and threaded comments | No native screen; social auth accepts cookies only |
| Experts/messages | Directory, consultation creation, messages with retry identity | Native public profile, ORCID/publication editing, push; E2EE helper is not used by chat |
| Academic | Courses, paged messages, ask | File upload, indexing, quiz UI/export; 150 MiB server constant exists but end-to-end upload unverified |
| Voice | Web implementation only | Native recording/transcript/review absent |
| Android | Expo 54 / RN 0.81, lockfile, APK/AAB EAS profiles | No APK evidence; EAS project association/signing; actual phone tests |
| iOS | Shared React Native source | No bundle ID, permission descriptions, signing or TestFlight evidence |

## Design and ordered plan

Use the existing React Native screens and same API/database. Reuse social business handlers rather than duplicate moderation or data tables. Five tabs: Ana Sayfa, Dental Akış, AI Analiz, Hastalar, Profil. Program remains a stack screen reachable from home. No provider or inference changes. No merge/deploy.

1. Add tested native Bearer authorization to social routes only; retain cookie CSRF checks, verified-email/session checks, block rules and admin MFA boundary. Test revoked/expired/unverified/inactive identities, post retries and cross-user ownership.
2. Add native social API and feed/profile/comment screens with paged lists, server moderation states, explicit like/follow states, collapsed reply threads, versioned owner actions and SecureStore drafts with UUID retry identities. Keep draft on ambiguous network failure.
3. Repair home patient navigation, paginate patient search with stale-response guards, provide errors/retry, safe areas and five tabs. Verify TypeScript and component/data contract tests.
4. Restore analysis by ID from history, camera permission/picking, persist only job ID per account, refresh on foreground, enforce confidence >= 0.5 in display. No clinical correctness claim.
5. Add iOS metadata/permissions, explicit preview/production build commands and CI bundling for both platforms plus a debug APK artifact job. Run full mobile tests, Android/iOS Metro exports and backend regression subset. Build only where toolchain exists.

## Performance / release gates

Targets to measure on representative mid-range phones: cold-start interactive p95 <= 3s; cached tab transition p95 <= 200ms; feed 15 posts/page, at most 30; patient 30/page; no API request per scroll frame; no automatic mutation retries. Test 5 concurrent writers against disposable PostgreSQL. Registered-user count 60,000 is not concurrency. Do not flood production. Production-equivalent load, ownership sweep of every endpoint, store/legal review and physical devices remain required before release.

PostHog inspection: only Default project 318683 visible, onboarding incomplete, `ingested_event=false`; no production latency/error conclusions available. No patient content sent to analytics, no replay enabled. Figma account Dental Ai accessible; no existing file provided. HeyGen has a Demo brand kit only; no paid video generation needed for native compilation.

## Verification ledger

- Baseline: TypeScript and 23 mobile tests passed locally.
- Current mobile: TypeScript plus 34 tests passed (13 session/API, 11 realtime/analysis/paging, 10 social/draft/findings/rendered action contracts). Render-contract tests are simulated components, not physical-device E2E.
- Backend: 72 social/native regression tests plus 32 existing native/security tests passed. Disposable PostgreSQL: 8 concurrent-writer/comment-reaction tests passed. No production database was used or reset.
- Android/iOS Hermes exports passed before final review; final source exports are repeated before delivery. Native Android prebuild passed. APK compilation is pending; iOS IPA not built.
- Independent review found four important issues: Android Alert truncation, mutable-list refresh retention, late upload overwriting a reopened draft, and exhausted reply cache. All four have regression tests observed failing before the fix and passing after it. Minor storage-read recovery and in-flight comment-draft deletion were also repaired.
- Rulings: mutable feed/patient refresh replaces the current loaded page to remove deleted/blocked content; append-only chat/course history keeps existing merge semantics. Upload/send blocks composer dismissal until completion/error, with bounded social HTTP timeouts. Native admin tokens do not grant web moderation/MFA authority.
- Deferred: full public profile/cover/publication management, in-card follow shortcut (follow works in profile), pinch/swipe gallery, native anamnesis editing, complete analysis-upload progress/idempotency, full session-expiry UX, native voice and academic upload/quiz/export, push delivery, account deletion/consent, icon/splash, and store release.
- Device, APK install, TestFlight, clinical accuracy and 60k-user load tests: NOT RUN.
