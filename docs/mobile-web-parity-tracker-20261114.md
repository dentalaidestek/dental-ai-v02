# Dental AI mobile completion tracker

## Working contract

Continue the existing React Native / Expo application in `mobile/`; preserve completed code, web rules, FastAPI/PostgreSQL/Render orchestration and Modal inference. Target Android `tr.dentalai.app`, iOS and Expo `dentalai47/dental-ai`. Do not replace functioning flows with mock data, WebViews or decorative screens. A successful APK build or unit test does not establish device acceptance.

Branch: `feature/mobile-web-parity-20261110`. PR: #257 (draft). Tracking issue: #258. No main merge, live backend deployment or store publication without separate approval. No patient information, passwords, codes, session tokens, clinical images or private messages in logs/reports.

## Order and evidence

| Priority / heading | Existing native entry | Current evidence | Remaining acceptance/work |
|---|---|---|---|
| P0 Android CI / API / session | api.ts, sessionExpiry, useSessionHealth | Local TypeScript/session checks; startup Query import defect fixed earlier; feature-specific errors do not directly invalidate sessions | Remote CI still failing with empty steps / inaccessible logs; reproduce fresh release requests on device; full live session/account isolation |
| P0 Login / registration / recovery | NativeAuth, authApi, mobile_account_api | Native registration, web consent/title rules, OTP, generic password recovery, single-use reset and session revocation tested locally | Real mail/device/OS links, native admin MFA, refresh/session lifecycle acceptance |
| P0 Patients and loading states | App Patients, NativeNewPatient | Real owned records, pagination, create/duplicate selection, calendar birth date; errors separated from empty data | Authenticated production/device spinner reproduction, large-list/slow/offline acceptance |
| P1 Patient profile | NativePatientProfile / History / Media / Appointment | Web section order, collapsed information, complete treatment details, actual scoped history, media and patient-linked appointment | Real-device design/flow acceptance, durable mutation receipts and simultaneous-edit handling |
| P1 Tooth chart | NativeToothChart, NativeToothVisual | Same FDI32/20, bundled atlas/implant, web SVG status paths and gradients, actual patient/tooth history and save APIs | Device rendering, shadows/grayscale equivalence, concurrency and clinical acceptance |
| P1 Clinical media | NativePatientMedia and MediaGallery | Multi-selection/sequential upload, gallery/zoom, owned deletion, selected-media analysis; post-commit async publication defect fixed | Byte progress, durable uncertain-upload reconciliation, all upload-path EXIF checks, camera/background/large-file device tests |
| P1 Image AI | NativeDentalAI, analysisApi | Existing durable server jobs/recovery, real patient selection, bounded reads, patient/profile/gallery entry | Full web result/doctor-review parity, application close/reopen/duplicate-start and live inference/device acceptance |
| P1 Voice examination | VoiceExamEntry and existing voice adapters | Prior closed-concept finish-review architecture retained; concurrent permission changes preserved | Full microphone/ASR/pause/resume/background flow, finish-only inference, sources/doctor approval and clinical end-to-end tests |
| P2 Program / appointments | NativeProgram / Editor, shared patient appointment entry | Web-derived day/week/month occurrences and pagination, shared full editor, edit/copy/complete/delete, reminder-queue parity, recurrence and owned conflict advice tested locally | Device/real notifications, atomic concurrency/idempotency and performance acceptance; conflict advice is not an atomic exclusion guarantee |
| P2 Dental Flow | SocialScreens / socialApi | Existing feed/comments/follow/moderation implementation and selected regressions retained | Re-audit every web menu/media/profile action; moderation/reconnect/performance and two-account device acceptance |
| P2 Academic AI | ModernScreens Academic and existing backend | Prior native source retained; provider decisions unchanged | Full document/index/question/answer/history/source/voting parity and durable long-job/device acceptance |
| P2 Expert profile / publications | NativeExpertProfile / NativePublications / directory | Native public identity/hero and Posts/Publications/About tabs, real performance, native management, structured CRUD/version/DOI/ORCID/share and busy-profile entry; prior application/document/rules preserved | Own follower/following drawers, detailed performance/settings, durable import/drafts, real provider/device/concurrency acceptance |
| P2 Consultation request | NativeConsultationRequest | Owned patient/media, fee/urgency/context, canonical receipt and uncertain-create recovery tested earlier | Real two-account lifecycle/payment/deadline/background acceptance |
| P2 Messages | Consultations / ConsultationChat / NativeChat tools | Replies, images/PDF/audio, annotation copies, selected case media, web lifecycle actions and authorization tested locally | Durable text/media idempotency, retained drafts/reconnection/deletion deadlines and full two-account Android/iOS behavior |
| P2 Account / profile | NativeAccount | Name/username/photo, password/email security, separate professional/document and expert accordions, title/document/application/rules/availability and shared identity refresh tested locally | Structured publication source adaptation now exists; detailed session controls, native admin MFA and live/device acceptance remain |
| P2 Notifications | Existing center/push registration | Existing real event/client source retained | Real push credentials/events, taps/deep links, foreground/background/closed app and duplicate delivery acceptance |
| P3 Security / privacy | Server authorization plus selected security suites | Local admin/account/owned-media/participant regressions; no token/photo/message logging introduced | Full endpoint audit, account/device isolation, EXIF/retention, upload safety, rate limiting and KVKK acceptance |
| P3 Performance / 60,000 users | Existing backend/native lists | No capacity certification | Define registered versus concurrent traffic; DB pool/index/N+1, media, AI queue/Modal, retries/realtime/push; 5 concurrent posts and all original load scenarios |
| P3 Store readiness | Expo native configuration | JS exports/prebuild from earlier steps; app id retained | Signed Android/iOS builds, real devices, icon/screenshots/privacy/store forms, accessibility, small screens, keyboard/back/network and final release gates |

## Preserved clinical decisions

- Live voice listening shows transcript; clinical extraction/final review happens on finish.
- Closed concept identifiers and verified-source workflow remain; distinguish unverified from false and evaluate clinician claims separately.
- No uncontrolled automatic write to patient records. Doctor approval is required.
- Retain actual production AI provider configuration and academic-provider decisions; do not swap providers while adapting native UI.
- Typing a patient name is not selection: use an authorized patient record id.
- Blank records and failed requests must remain distinct. Uncertain mutations require reconciliation before retrying.

## Working method for every heading

Read the latest branch/PR/CI and current web route/template/handler. Map each action, input, state, permission and save behavior to native code. Fix a reproduced/root-cause defect, add meaningful regression coverage, run relevant checks, preserve concurrent changes, commit to the development branch, update PR/issue and record unresolved device/live/CI criteria. Do not mark a module complete until all original acceptance conditions are met.

Evidence so far: `mobile-p0-verification-20261114.md`, `mobile-chat-patient-audit-20261114.md`, `mobile-patient-profile-parity-20261114.md`, `mobile-auth-account-parity-20261114.md`, `mobile-program-parity-20261114.md`, `mobile-professional-parity-20261114.md`, `mobile-expert-publications-parity-20261114.md`. Counts belong to their individual commits and must not be presented as current evidence after untested edits.

The next high-priority acceptance remains P0 live-device/API/CI confirmation. General Program now has a source adaptation and local coverage; professional/account verification now has source adapters and native forms; public-profile/publication tabs now have a source adaptation; independent work continues on remaining clinical AI/voice/academic headings and the documented expert/device gaps, while keeping shared authentication changes coordinated. This tracker preserves the original scope; it does not certify the entire app as complete.
