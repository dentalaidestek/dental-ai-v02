# Dental AI mobile — consolidated parity handoff (2026-11-10)

Repository: dentalaidestek/dental-ai-v02. Mobile: mobile/ (Expo SDK 54, React Native, TypeScript). Web is the behavioral reference; mobile should use native navigation and dialogs, not copy HTML. Work branch: feature/mobile-web-parity-20261110; PR #257. Do not merge/deploy without approval.

## Mandatory invariants
- Reuse existing backend endpoints, authorization, business rules, moderation, privacy checks, persistence, and realtime events. Never duplicate server-side decisions in UI.
- User-owned patient media must remain authenticated; no public URLs or leaking identifiers in logs.
- Preserve drafts across slow requests, screen changes, failed uploads, and logout; prevent duplicate submissions.
- Android back, iOS safe area, keyboard avoidance, loading/error/empty states, accessible controls, and responsive widths on every overlay.
- CI must be green and actual Android/iOS devices tested before claiming release-ready.

## Web-to-mobile gap register
| Feature | Web reference | Mobile evidence / outstanding |
| --- | --- | --- |
| Dental Akış | Latest main release #255, comment system #254 | SocialScreens.tsx has feed, comments, compose, follow, profile navigation. Audit all permissions, moderation, publication, relationships, avatars, link previews, pinning, edit/delete/report and nested replies against current web implementation. |
| Expert profile | app/templates/_expert_social.html | Web has Posts / Publications / About tabs and follower/relationship + publication dialogs. Mobile currently mainly shows posts and counts. Implement native tabs and equivalent authorized endpoints. |
| Expert discovery | app/templates/expert_support.html | ExpertDirectory search exists; debounce/error retry added. Web filter sheet parity unverified. |
| Patient gallery | app/templates/patient_detail.html | MediaGallery upload/list; full-screen authenticated preview added. Confirm gallery delete and clinical annotations with backend permissions. |
| Expert consultation | app/templates/expert_case_room.html | ConsultationChat exists; web annotationModal image editor not ported. Requires careful image tooling and clinical confidentiality checks. |
| Profile/account | app/templates/account.html, expert_profile_edit.html | Web crop dialogs, account deletion confirmation; mobile parity unverified. |
| Program | app/templates/program.html | Web programCopySheet; mobile Program exists but copy dialog parity unverified. |
| Voice exam | Web voice exam flow | VoiceExamEntry present; ensure full transcript retention, taxonomy-constrained clinical review, source verification, finish/retry, no implicit patient writes. |
| Academic AI | Web academic flow | Academic screen present; compare document uploads, 150MB policy, question generation, loading and source attribution. |
| Push | app/mobile_api.py + app/mobile_push.py | Backend registration/send behind MOBILE_PUSH_ENABLED. Expo native registration, lockfile packages, token lifecycle, deep-link response, physical device tests unfinished. |
| Dental chart | Web tooth/surface/history | NativeToothChart exists; compare FDI quadrant selection, surfaces, history, materials, and persistence. |

## CI blocker
Last known green commit for four PR checks: 0413d2a05ba8a887cded20181a56317eb8b6b661. Subsequent commits show failure in Mobile Android CI, Expert social profile regression, Security recovery regression and Admin security regression, including after reverting UI changes. GitHub job logs endpoint returned BlobNotFound/404 and job step API returned no steps; do NOT attribute all failures to TypeScript without logs. Diagnose runner startup/billing/permissions vs actual test errors via GitHub Actions UI or alternative authenticated logs. Never claim checks pass before verified.

## Recent branch changes
- Push backend and token registration/logout groundwork, with cross-account token ownership conflict returning 409.
- ExpertDirectory debounce, stale response protection, retry UI.
- Social profile visitor cannot open owner composer.
- Social full-screen sheets and accessible close.
- Patient media full-screen authenticated preview.
- Earlier gallery/social preview changes were reverted during CI isolation; later patient preview was reintroduced independently.

## Acceptance checklist
1. Capture a feature inventory from current main web templates, scripts, endpoints and tests; map every action to a mobile screen.
2. Implement each missing native flow using existing API and authorization. Add component tests for modal dismissal, stale requests, duplicate posts, drafts, keyboard/safe area.
3. Run npm ci, npm test, Expo Android+iOS export, APK build, backend targeted tests, and CI checks. Fix actual failures rather than repeatedly retrying.
4. Validate on physical Android and iOS, including slow/offline transitions and multiple accounts.
5. Review scalability for 60k registered users, not conflating this with 60k concurrent users; measure queue, database and upload performance.
6. Only merge or deploy on explicit authorization.
