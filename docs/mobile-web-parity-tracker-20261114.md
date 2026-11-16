# Dental AI mobile completion tracker

## Working contract

Continue the existing React Native / Expo application in `mobile/`; preserve completed code, web rules, FastAPI/PostgreSQL/Render orchestration and Modal inference. Target Android `tr.dentalai.app`, iOS and Expo `dentalai47/dental-ai`. Do not replace functioning flows with mock data, WebViews or decorative screens. A successful APK build or unit test does not establish device acceptance.

Branch: `feature/mobile-web-parity-20261110`. PR: #257 (draft). Tracking issue: #258. No main merge, live backend deployment or store publication without separate approval. No patient information, passwords, codes, session tokens, clinical images or private messages in logs/reports.

## Order and evidence

| Priority / heading | Existing native entry | Current evidence | Remaining acceptance/work |
|---|---|---|---|
| P0 Android CI / API / session | api.ts, sessionExpiry, useSessionHealth | Latest branch HEAD `255ab789`: Android push run `43814614950` (typecheck `133123704187`, beta-APK `133123704533`); PR Android `43814620640` (typecheck `133123723392`, beta-APK `133123723167`); Security recovery `43814620622` / job `133123723374`; Admin security `43814620617` / job `133123723194`; Expert social `43814620626` / job `133123723274`. All completed failure with `runner_id=0`, `runner_group_id=0`, empty runner names, `labels=[ubuntu-latest]`, `steps=[]`, 1–2-second completion. Re-running the current-head PR matrix was accepted; new Android jobs `133123852016` / `133123852310`, Security `133123860965`, Admin `133123871400`, Expert `133123879823` again failed with no runner and zero steps. Current typecheck and security log downloads return `BlobNotFound 404`. No `npm ci`, `tsc`, Node suite, Gradle or pytest ran. Source-level Android argument-count/revision defect is fixed; compiler/security verification remains blocked. Exact account/billing/hosted-runner entitlement cause is not exposed; repository owner must inspect Actions runner availability, usage/billing and concurrency. No current-head CI test/build is green |
| P0 Login / registration / recovery | NativeAuth, authApi, mobile_account_api | Native registration, web consent/title rules, OTP, generic password recovery, single-use reset and session revocation tested locally | Real mail/device/OS links, native admin MFA, refresh/session lifecycle acceptance |
| P0 Patients and loading states | App Patients, NativeNewPatient | Real owned records, pagination, create/duplicate selection, calendar birth date; errors separated from empty data | Authenticated production/device spinner reproduction, large-list/slow/offline acceptance |
| P1 Patient profile | NativePatientProfile / History / Media / Appointment | Web/native profile edit shares a SHA-256 revision fingerprint over editable fields and address; PostgreSQL row locks plus stale-revision 409 prevent stale snapshots overwriting newer data. Native preserves draft and offers explicit reload/reapply. Treatment create/update now use durable server receipts, SecureStore request keys and treatment `edit_revision`; the web flow has no delete action, so no extra native delete was invented. Native profile and tooth chart now share the same account/patient intent scope | Backend/native regressions are committed but CI cannot execute; two-account web/native physical-device acceptance and full treatment history/device acceptance remain open |
| P1 Tooth chart | NativeToothChart, NativeToothVisual | Same FDI32/20, bundled enamel atlas/implant, web status paths/gradients, patient/tooth history and save APIs. Treatment create/update now use durable account+patient intents, stable request keys and treatment `edit_revision`; uncertain responses recover explicitly. Native chart now also renders the web's patient-right/patient-left labels on both jaws and preserves the complete web FDI quadrant order | Six treatment/visual regressions are committed but unexecuted because Actions has no runner. Real Android/iOS rendering, extracted-tooth grayscale fidelity, small-screen screenshot comparison and clinical acceptance remain open |
| P1 Clinical media | NativePatientMedia and MediaGallery | Native profile mounts this section in web order; multi-selection/sequential archive upload, gallery/zoom/owned deletion and saved+new analysis composition remain; shared `app/clinical_media.py` now applies orientation and strips EXIF/ancillary metadata in web gallery, web patient/guest analysis, native gallery, native analysis and archived-media analysis copies; legacy v3 reuses the native helper | Durable gallery-upload receipts/process-death recovery, byte-level progress, legacy archived originals not yet migrated, camera/background/large-file and Android/iOS fidelity tests |
| P1 Image AI | NativeDentalAI / NativeClinicalReview, mobile_clinical_api, mobile_analysis_api | Web result/review flow retained; native gallery combines up to four saved and new images in one durable VISION intent; clinical-information-only requests create a receipt-backed PRELIMINARY job with no fake ImageAsset; shared sanitizer now cleans new direct uploads and selected-media analysis copies before classification/provider work | Mixed-media, clinical-only and sanitizer regressions are committed but not fully executed; legacy archive originals remain unchanged; durable note reconciliation and production inference/device/concurrency acceptance remain open |
| P1 Voice examination | VoiceExamEntry / NativeVoiceRecorder / NativeVoiceApproval | Real Expo Audio chunk recording, pause/resume, sequential transcription, secure text draft/recovery, finish-only clinical handoff, canonical explicit approval/appointment and idempotent receipt; native entry mirrors web's anonymous-new-patient action; long examinations match web's 72k-character / 216 KB envelope with 12k/36 KB extraction chunks and scoped SecureStore checkpoints; cumulative MM:SS duration now persists across 15-second file rotations, pauses and draft restore (legacy drafts default to zero) | Duration accumulation/restore regressions are committed but not run. Long-transcript/checkpoint repository regressions also remain unrun. Physical Android/iOS audio/noise/Bluetooth/interruptions, production ASR/final/source quality, raw-file retention/encryption, process death/durable jobs and clinical acceptance remain open |
| P2 Program / appointments | NativeProgram / Editor, shared patient appointment entry | Web-derived day/week/month occurrences and pagination, shared full editor, edit/copy/complete/delete, reminder-queue parity, recurrence and owned conflict advice tested locally | Device/real notifications, atomic concurrency/idempotency and performance acceptance; conflict advice is not an atomic exclusion guarantee |
| P2 Dental Flow | SocialScreens / socialApi | Existing feed/comments/follow/moderation implementation and selected regressions retained | Re-audit every web menu/media/profile action; moderation/reconnect/performance and two-account device acceptance |
| P2 Academic AI | NativeAcademic / Source / File / AnswerText, mobile_academic_api | Owned course/material flows, native progress/index, durable run receipt/reopen, structured grading/learning/source/feedback/history and current-run cancellation now mirror canonical web handlers; provider unchanged | Cancellation regressions are committed but unrun; provider-level hard interrupt is not claimed; production/device/Modal acceptance, rich math/clipboard, Android image zoom, transactional upload dedup/cache/privacy/performance acceptance |
| P2 Expert profile / publications | NativeExpertProfile / NativePublications / directory | Native public identity/hero and Posts/Publications/About tabs, real performance, native management, structured CRUD/version/DOI/ORCID/share and busy-profile entry; prior application/document/rules preserved | Remaining settings/import drafts and real provider/device/concurrency acceptance; native private relationships and owned performance/policy/event panel now use canonical web helpers/APIs |
| P2 Consultation request | NativeConsultationRequest | Owned patient/media, fee/urgency/context, canonical receipt and uncertain-create recovery tested earlier | Real two-account lifecycle/payment/deadline/background acceptance |
| P2 Messages | Consultations / ConsultationChat / NativeChat tools | Replies, images/PDF/audio, annotation copies, selected case media, web lifecycle actions and authorization tested locally | Durable text/media idempotency, retained drafts/reconnection/deletion deadlines and full two-account Android/iOS behavior |
| P2 Account / profile | NativeAccount | Name/username/photo, password/email security, separate professional/document and expert accordions, title/document/application/rules/availability and shared identity refresh tested locally; native self-erasure now invokes the canonical web deletion handler with username + current-password confirmation and admin exclusion | Native self-erasure endpoint/UI and backend/React regressions are committed but not executed in this runtime; real device, session revocation, deletion job/storage cleanup and live acceptance remain |
| P2 Notifications | Existing center and native notification resolver | In-app notice center maps canonical web case, expert directory/profile, Program and patient targets to real native routes; unsupported support-request target stays unread with an explicit message | Expo push token registration and OS delivery, support-ticket native screen, killed-app taps/deep links, foreground/background delivery, duplicate delivery and physical-device acceptance |
| P3 Security / privacy | Server authorization plus selected security suites | Local admin/account/owned-media/participant regressions; no token/photo/message logging introduced | Full endpoint audit, account/device isolation, EXIF/retention, upload safety, rate limiting and KVKK acceptance |
| P3 Performance / 60,000 users | Existing backend/native lists | Mixed analysis storage materialization, validation/copy, classification and persistence now use the worker pool; no capacity certification | Define registered versus concurrent traffic; DB pool/index/N+1, media, AI queue/Modal, retries/realtime/push; 5 concurrent posts and all original load scenarios |
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

Evidence so far: `mobile-mixed-analysis-media-20261116.md`, `mobile-p0-verification-20261114.md`, `mobile-chat-patient-audit-20261114.md`, `mobile-patient-profile-parity-20261114.md`, `mobile-auth-account-parity-20261114.md`, `mobile-program-parity-20261114.md`, `mobile-professional-parity-20261114.md`, `mobile-expert-publications-parity-20261114.md`, `mobile-voice-workflow-20261114.md`, `mobile-academic-workflow-20261114.md`, `mobile-clinical-workflow-20261115.md`, `mobile-relationships-20261115.md`, `mobile-analysis-upload-20261115.md`, `mobile-vision-viewer-20261115.md`, `mobile-expert-performance-20261115.md`. Selected-media clinical context: ba5969a / 8d36c7a / 6f8fe33 / 464770e / ffacfd9 / a0d62c4. Regression sources are committed but not executed in this runtime; do not mark them green. Counts belong to their individual commits and must not be presented as current evidence after untested edits.

The next high-priority acceptance remains P0 live-device/API/CI confirmation. General Program now has a source adaptation and local coverage; professional/account verification now has source adapters and native forms; public-profile/publication tabs now have a source adaptation; independent work continues on remaining clinical AI/voice/academic headings and the documented expert/device gaps, while keeping shared authentication changes coordinated. This tracker preserves the original scope; it does not certify the entire app as complete.


## Latest continuation note — 2026-11-15

Compared the web voice entry template and routes (voice_exam_entry.html, voice_exam_session.html, voice_exam.py) against VoiceExamEntry and NativePatientSelect. The web page has a first-class anonymous-patient action before existing-patient search; the native screen previously had only existing-patient selection. Added an authenticated, owner-scoped mobile endpoint, stable per-account request identity, SecureStore retry key, native entry action, and backend/API/screen regression cases. No ASR or clinical write is triggered by patient creation. Source changes are on the PR branch only.

Latest CI for code head 8512983: Android run #1986 (43750224085), security recovery #802 (43750224083), admin security #686 (43750224092), expert social #682 (43750224158). Each job reports an empty step list; logs return BlobNotFound 404. Re-running the preceding failed runs also reproduced the empty-step failure. This does not establish a TypeScript or Python test failure. New code tests are not yet executed; do not mark the module or CI complete.


## Native self-erasure parity — 2026-11-15

Compared `app/templates/account.html` and `app/main.py:delete_own_account` with `mobile/src/NativeAccount.tsx` and `app/mobile_account_api.py`. The web account has a guarded self-delete action (typed username + current password, ADMIN excluded); native account had only logout and did not expose the same action.

Added `POST /api/mobile/v1/account/delete` as a narrow adapter over the existing canonical `delete_own_account` handler. It does not implement a second erasure policy: the web handler still verifies the session, excludes ADMIN, compares the username case-insensitively, verifies the current password, runs the existing account-erasure coordinator, revokes sessions and returns the established completion redirect. The native adapter translates only the exact completion redirect to `{ok:true, requires_login:true}`; error statuses are preserved. The UI requires username and current password plus a second destructive confirmation, hides the action for ADMIN, and expires the local session only after server confirmation.

Commits: `b6ed321` backend adapter; `8c8f450` backend rejection/success/admin tests; `7faa1c4` typed client action; `3044abf` native confirmation UI; `be6cda6` client/UI regressions. Tests are committed, not executed in this runtime. No account was deleted during development. No main merge, live deploy or store publication.


## Long native voice transcript continuation — 2026-11-15

Web-source comparison found a real parity defect: web FinishDraft accepts 72,000 characters / 216 KB and processes 12,000-character chunks, while native VoiceExamEntry and appendVoiceSegment stopped at 18,000 characters. Native now accepts the same overall envelope, splits Unicode-safely into <=12,000-character / <=36 KB chunks, sends them sequentially to the existing `/voice-exam/text` endpoint, passes the previously extracted structured context to the canonical backend merge, and stores completed chunk cursor/revision/review in SecureStore. The checkpoint is bound to user, patient and SHA-256 of the exact transcript, expires after 24 hours, and is discarded on mismatch. Revision-conflict recheck clears the checkpoint before re-extracting. The final synthesis still receives the full transcript; no patient data is written automatically.

Commits: `9a33661`, `f62405e`, `26a3e4d`, `49c4a86`, `1936a42`, `dc10098`, `10fcdf9`, `40a9cd5`, `0ccc898`, `18cf93a`, `372a1bc`, `624238d`, `127af68`. The voice helper TypeScript file compiled in an isolated scratch check; Unicode chunk round-trip and exact comparison against the web `FinishDraft.splitTranscript`, 72k/216KB boundary, 19k append, checkpoint account/patient/hash/expiry, extraction resume/context-carry and mixed-revision rejection tests passed in an isolated Node harness. This is not the full repository suite or Android typecheck. GitHub Actions still does not allocate runners: latest PR jobs show runner_id=0, empty runner_name and zero steps; logs are BlobNotFound. No source-level CI failure has been observed because the tests never start.


## Mixed saved + new clinical media — 2026-11-16

Compared the actual web flow first: `new_analysis` preselects saved media and `create_analysis` accepts `existing_media_ids` and new `images` in one multipart form with a combined four-image limit and per-patient/per-owner checks. Native previously had two disconnected paths (saved-media-only and new-file-only). The patient gallery now opens the existing durable native analysis composer with selected saved-media previews, optional new camera/gallery images, FDI and clinical notes. The mobile upload intent carries both media sets; the gallery uses its own SecureStore namespace so it cannot race the Dental AI tab's pending draft. The backend mobile upload accepts both, verifies each saved row belongs to the patient/current owner, validates actual file format/size/pixels, stages all files before one VISION enqueue, and includes saved IDs in the idempotency digest. Historical new-file-only digest remains unchanged for older pending uploads.

Commits for this continuation: `6902abc` backend mixed-media endpoint; `4886c2a` backend ownership/atomicity/idempotency tests; `4a94614` upload-intent contract; `9d9690f` native composer; `4140f73` patient-gallery integration; `5563422` account-scoped profile prop; `e42ad5f` app identity plumbing; `6010bf3` native mixed upload tests; `5558297` submit-label test alignment; `57234c3` gallery account-switch tests; `3b22df5` composer source assertions; `d74413e` rendered gallery regression harness; `e45ae60` isolate gallery draft namespace; `9f9bf17` wire namespace; `0e1a444` security workflow trigger; `cb7acaf` remove duplicate trigger; `51e63ee` this evidence note. Tests are committed but not executed.

CI after the current head: Android #2075 (run 43764702173), Admin security #730 (43764706414), and Expert social #726 (43764706409) all failed before a step ran; raw jobs show runner_id=0, empty runner_name and steps=0. Security recovery #845 (43764662242) has the same pre-runner failure. Logs return BlobNotFound 404. This is not a source-level typecheck/pytest result. No live/device test, main merge, backend deploy or store publication.


## Mixed-media recovery and async-route load guard — 2026-11-16

A further audit found that a recovered SecureStore draft could contain a different saved-media set from the gallery's current selection. The native composer now sends its restored saved IDs back to the gallery so its preview reflects the exact pending request, not a newer selection. Definitive 404 for a missing saved item releases that local intent; network-uncertain outcomes retain the receipt and files. A second scale issue was corrected: R2/local materialization, saved/new image copy+validation, classification and persistence now run through Starlette's worker pool instead of blocking the async request loop. A focused backend regression records each delegated operation. This is an event-loop protection improvement, not a 60,000-user capacity certification.

Additional commits: `56d41ac`, `c4fd69c`, `3f4c1ed`, `afd908b`, `f759531`, `96a6497`. Latest code-head CI: Android #2087 (43765181240), recovery #851 (43765181263), admin #735 (43765181243), expert-social #731 (43765181265); all jobs again report runner_id=0, empty runner_name, zero steps and ~2-second failure. No typecheck, pytest or APK step ran. No main merge, live deploy or store publication.


## Native microphone device check — 2026-11-16

Compared the web entry/device-check route and its PCM worklet with the current native voice entry and Expo Audio 1.1.1 APIs. The web flow has a separate six-second, user-triggered microphone check; the native entry previously exposed only the clinical recorder. Added a native preflight panel with permission request, live metering, six-second local capture, explicit low/no-signal/inconclusive states, and cleanup on stop, app background, navigation blur and unmount. Expo Audio is file-based here, so a temporary file is written only to the app-private cache and deleted after the check. It is never uploaded, transcribed, added to a patient draft or passed to an AI provider. Unlike the web AudioWorklet, the current public native API does not expose the same PCM16 in-memory conversion path; this native check verifies capture + metering + non-empty temporary file only. It does not certify Gemini/ASR/Bluetooth or clinical quality.

Commits: `b2e6306` outcome model; `7b51d99` classification tests; `6f5f976` native check component; `bb677aa` entry integration; `fdd5540` lock clinical actions while checking; `7f7852f` privacy/lifecycle UI regressions; `35c52f0` include regressions in beta test script; `205789d` feature and CI evidence. Tests are committed but not executed. Physical Android/iOS microphone acceptance remains open.

Starting PR/branch head `5e2824b`: Android #2104 (43767959675) has failed `typecheck` and `beta-apk` jobs with no steps; security recovery #859 (43767959667), admin security #743 (43767959674), and expert social #739 (43767959663) likewise have empty job-step arrays. The step API returns `[]`, job logs return `BlobNotFound 404`, and artifact lists are empty. Thus compiler, Gradle and pytest commands did not run. This confirms a pre-step Actions execution/runner-allocation failure, but the precise hosted-runner/account/billing cause is not exposed. No speculative workflow runner change was made. Owner-side Actions availability/billing inspection is still required.


CI retry evidence after the 2026-11-16 inspection: GitHub accepted a rerun of all four failed workflows at the starting head. The new attempt again completed with empty step arrays for Android beta-apk/typecheck and all three security/regression jobs; the five new job-log downloads again returned `BlobNotFound 404`. This confirms the retry did not reach npm/tsc, Gradle or pytest. The rerun was deliberately against old head `5e2824b`, not the new microphone commits. The new head currently has no associated workflow run and combined status is empty. No CI pass is claimed.

## 2026-11-16 — Clinical-information-only analysis parity

Compared the web `analysis_new.html` form and `create_analysis` handler with the native composer and mobile analysis API. Web allows clinical information without an image and queues `PRELIMINARY`; native previously required at least one saved/new image. The existing native endpoint and composer now accept zero images only when an FDI tooth number or clinical note is present, retain patient ownership and request-key receipt idempotency, create no ImageAsset, and enqueue the canonical PRELIMINARY job. Image-backed requests continue to use VISION and the four-image maximum. Empty-context requests are rejected before allocating records. Regression tests were added for preliminary job/receipt behavior, idempotency/conflict, empty rejection, native button eligibility and multipart without a fake image. Tests have not run in a full checkout; no Android typecheck, pytest, device or production acceptance is claimed. Details: `mobile-clinical-only-analysis-20261116.md`.


Latest Academic AI cancellation parity evidence: `docs/mobile-academic-cancel-20261116.md`.


## Clinical media privacy boundary — 2026-11-16

See `docs/mobile-clinical-media-sanitization-20261116.md`. The shared sanitizer is called before durable storage or analysis classification on web gallery uploads, web patient/guest analysis uploads and selected archive copies, native patient-gallery uploads, native direct-analysis uploads and native selected archive copies. It applies orientation, strips EXIF/ancillary metadata, rejects animated/mismatched/oversized images and preserves only a bounded ICC color profile. Legacy archived originals are not bulk rewritten. The new regression file is committed; only six isolated sanitizer checks have been executed, not the full repository test suite.


## Latest CI observation — 2026-11-16 03:04 UTC

The current head triggered Android, Security recovery, Admin security and Expert social workflows. All jobs completed failure with no steps; the step API returned an empty array and each log download returned `BlobNotFound` 404. The combined commit-status endpoint returned no status entries. The security workflow now explicitly watches `app/clinical_media.py` and `tests/test_clinical_media_sanitizer.py` and includes the new test file in its pytest command; its current-head job was triggered but could not execute. Do not label these as code-test failures or green checks. The GitHub Status page showed `All Systems Operational` and `Actions Operational` at inspection, with a recent multi-product Actions incident on Nov 11 already resolved; no public status evidence identifies this repository's exact runner failure. See the live status page: https://www.githubstatus.com/.


## Latest continuation — clinical upload boundary and test fixtures

The shared sanitizer now also deletes a rejected staged file and preserves PNG palette transparency. The isolated sanitizer/fidelity/cleanup harness passed eight checks. The committed pytest file contains nine tests; the web upload-queue regression now uses a real JPEG with synthetic EXIF and asserts the persisted image is decodable and has no EXIF. `security-recovery.yml` watches `app/clinical_media.py`, `tests/test_clinical_media_sanitizer.py` and `tests/test_blueprint_boundaries.py`, and runs both regression files. The latest workflow job inspection above is for `cd2bf23`; no new workflow run was visible for the final test/workflow commits when this note was written.


## Final run verification — 2026-11-16 03:08 UTC

At final head `6ae3dd9`, Android #2229 and Security recovery #921 were triggered alongside Admin security #805 and Expert social #801. All six job records across these four workflows completed failure without executing a step. The step API returned empty arrays and log downloads returned `BlobNotFound` 404. The workflow now includes the shared media sanitizer regression and the web upload-queue test, but the current job could not execute them. The exact root cause remains outside repository code; do not claim a passing security suite or Android typecheck.


## 2026-11-16 — Cross-client patient profile revision

Web-first comparison covered `patient_detail.html`, `main.py:edit_patient`, `mobile_api.py:mobile_patient_detail/mobile_edit_patient`, `NativePatientProfile.tsx` and `api.ts`. Added a shared revision fingerprint, web hidden form token, PostgreSQL row lock and stale-write 409 on both web and mobile paths. Native sends the revision loaded with the patient, keeps the draft on conflict, and only replaces it after an explicit "Güncel hasta bilgilerini yükle" action. ADMIN access remains identical to the existing `_owned_patient` rule; revision is not authorization.

Commits after starting head `4f886e1`: `60ea56a`, `d0872f8`, `e1d642f`, `5dab6f6`, `0e61c16`, `a1718eb`, `fe7450f`, `3a95025`, `e3d4ca1`, `9b7a1e1`, `f133296`, `d8904d6`. Regression coverage was added to the backend patient parity test, native patient API test and native profile UI test. A separate local smoke of the revision algorithm passed 3/3; it is not a repository test.

Latest checked CI head `d8904d6` (latest code commit `9b7a1e1`) triggered Android #2255, Security recovery #934, Admin security #818 and Expert social #814. Typecheck/APK and all three Python jobs failed with empty step arrays; typecheck/APK/security log downloads returned BlobNotFound 404 and combined status has no entries. Reruns of the code-bearing head `e3d4ca1` also failed before steps. No TypeScript, pytest, Gradle or device test ran. Final branch head `1b5ca6d` is a tracker-only documentation commit with no associated workflow run. Do not report these as code-test failures or passes.

No main merge, production deploy, APK/IPA publication or patient-record mutation. Remaining patient-profile work includes treatment mutation receipts and two-account physical-device acceptance.


## Native tooth-chart treatment mutation parity — 2026-11-16

Compared the web tooth chart (`app/templates/tooth_chart.html`), its lazy treatment-history request and mobile patient-detail payload with `NativeToothChart` before editing. The API contract in `mobile/src/api.ts` requires four arguments for `createTreatment` and six for `updateTreatment`; the chart supplied only three and four, respectively, and did not retain `edit_revision`. `NativePatientProfile` already used a durable SecureStore intent, but the tooth-chart treatment editor bypassed it. This was a concrete TS2554-style source mismatch and a runtime validator failure, discovered despite CI not reaching TypeScript.

Fixed on the PR branch: `App.tsx` now passes `userId`; `NativeToothChart` uses the same `dai.treatment.{userId}.{patientId}` scope and `chunkedDraftStore` as the profile; create stores an idempotent request key before sending; update sends request key plus the selected treatment revision; uncertain requests are restored and explicitly verified with the same payload/key; missing revisions block update; 400/422 allow correction; stale 409 reloads current history; 403/404 clears stale edit state. No new endpoint, provider, table, polling loop or clinical log was added.

Added five `toothChartLifecycle.cjs` regressions: create-before-send and remount retry, update revision, definitive 422 retry, legacy missing revision, and cross-account draft isolation. They are in the existing `test:beta` command but are not claimed green.

Starting HEAD `91abd3d`; twenty commits advanced the branch to `08bdf89` (code-bearing HEAD `2981893`; subsequent commits update visual parity and verification notes). A follow-up source review also replaced an invalid draft-restore setter with explicit field restoration before committing. Latest-head Android push/PR, security recovery, admin security and expert-social runs all failed before steps: all seven jobs show `runner_id=0`, empty runner/group, `steps=[]`, and logs `BlobNotFound 404`. No TypeScript, Node, pytest or Gradle process ran. No main merge or live deploy.



## 2026-11-16 — clinical media upload recovery (branch-only)
- Web-first comparison: patient profile upload is a single multi-file form (maximum 12 images, 12 MB each); native previously used a 15 MB limit, in-memory-only pending selection, and count-only progress.
- Added owner/patient-scoped server receipts with sanitized-byte + metadata digest, replay protection, payload-mismatch 409, deleted-media tombstones, and a receipt-status endpoint.
- Native queue is persisted before transfer in SecureStore; retries reconcile the same UUID receipt before any resend. Native upload now exposes actual multipart byte progress.
- Regression coverage added for replay, owner isolation, retention, process-death reconciliation, stable-key retry, secure-store failure, and progress. Full local suites remain unrun because the private GitHub repository could not be cloned in this runtime; CI runner allocation is the current verification blocker.
- Remaining media gap: a picker cache URI can be evicted by Android before a pending upload is resumed. If no server receipt exists, the original image must be selected again; no extra unencrypted copy is created.


## 2026-11-16 — Native support request parity follow-up

Web-first comparison repeated against `app/templates/support_request.html`, `app/templates/_support_status_regions.html`, `app/main.py` and the existing native support screen/API.

Completed the three previously-open support items:
- Optional expert-conversation association: native fetches eligible conversations from an authenticated endpoint, displays the same participant-aware choices, and sends `case_id`. Server independently verifies that the authenticated user is a case participant and that a message exists, or the requester has reached the web timeout eligibility. The linked case is included in the durable idempotency payload and the choice is persisted with the pending SecureStore intent. The other conversation participant is not given access to the support ticket.
- “Bildirimlerim”: native now lists the authenticated user's moderation reports with status, case reference and date. Each report is associated with the canonical private `REPORT` support conversation (using the existing web helper that creates missing linked tickets); tapping a report opens the same paged conversation UI. Detail/read/reply endpoints allow `REPORT` tickets only after checking both ticket owner and the linked `UserReport.reporter_user_id`.
- Pagination: support ticket list now uses descending ID cursor pages (50 per request); the existing 20-message backend cursor is now exposed by a “Daha eski mesajları yükle” action that prepends messages without replacing the current thread. Ticket history has a “Daha eski destek taleplerini yükle” action.

Regression additions:
- Python: eligible case listing and linking, report list + linked thread, cross-account report detail/reply denial, and ticket cursor non-overlap.
- Node source-contract: case selection/persistence, report list/thread opening, ticket and message pagination. Wired into existing `test:beta` script.
- GitHub source-level assertions: 13/13 core implementation checks passed after correcting one assertion to match the explicit participant-set check. These are not runtime tests.

Latest commit: `e20f0b7645e50ac1b8d180eecfd5be804b59bfd1`. Latest-head Actions runs: Android #2459, Security recovery #1036, Admin security #920, Expert social #916; all concluded failure. Job records are exposed without runner step detail in the current response, so no TypeScript/Gradle/pytest pass is claimed. The previously observed runner-allocation/empty-step + BlobNotFound pattern remains unresolved; repository owner must inspect Actions runner/usage configuration.

PR remains Draft. No main merge, production deployment, database migration execution, APK/IPA publication or live patient/support record mutation.


## 2026-11-16 — Clinical media picker validation and gallery lifecycle

Web-first source comparison was completed before the native changes:
- `app/templates/patient_detail.html`: photo/radiograph upload, gallery preview, individual and bulk delete, existing-media selection.
- `app/templates/analysis_new.html` and `app/main.py`: the web GET page can carry up to 12 selected archive IDs, but the canonical analysis POST rejects more than four total images.
- `app/mobile_analysis_api.py`: the authenticated native analysis endpoint independently enforces at most four existing archive IDs and validates that every selected media row belongs to the same patient and authenticated owner.
- `app/mobile_api.py`: patient detail continues to enforce patient ownership (ADMIN exception remains unchanged).

The browser tool could not open the signed-in production site, so this pass used the branch's actual web templates, route handlers and API code rather than claiming a live authenticated browser walkthrough. The native four-image analysis cap was deliberately preserved: raising it to 12 would contradict both canonical create handlers.

### Changes on this branch
- `mobile/src/clinicalMediaPicker.ts`: rejects negative/NaN/infinite picker byte metadata and rejects a supported filename/source-URI extension disagreement before encryption or upload. The server still performs the authoritative image-byte/format validation.
- `mobile/tests/clinicalMediaPicker.cjs`: ten focused regressions cover JPEG/PNG/WebP, Android opaque content URIs, unsupported formats, MIME/extension disagreement, malformed size metadata, 12 MB/file and 12-file limits, unsafe URIs and unsafe filenames.
- `mobile/package.json`: includes the picker regressions in `npm run test:beta`.
- `mobile/src/NativePatientMedia.tsx`: gallery data now refreshes when the patient screen gains focus and when the app returns to foreground. The initial mount no longer starts a duplicate gallery request. This is event-driven; no polling interval or extra backend endpoint was added.
- `mobile/tests/patientMediaAccountSwitch.cjs`: adds a lifecycle regression for one initial load, no request on background, refresh on foreground, refresh on screen refocus, and listener cleanup on blur/unmount. Existing account/patient isolation tests remain in place.

### Commits in this pass
Starting branch head: `aa264af77749299fc5ee1fa66f740b05de5e7b05`

- `189a8f1` Reject ambiguous clinical image picker metadata
- `c14d408` Add clinical image picker validation regressions
- `54886b9` Run clinical media picker regressions in beta suite
- `cc150bf` Refresh clinical gallery on focus and foreground
- `f90402f` Test clinical gallery focus and foreground refresh
- `c5ce462` Disambiguate clinical media MIME regression fixture

Current code head before this tracker update: `c5ce462a86e5d7ed170ceba597f3332b7d870b27`.

### Verification actually performed
- Isolated Node test run for `clinicalMediaPicker.cjs`: **10/10 passed**.
- Strict isolated TypeScript check for `clinicalMediaPicker.ts` (`tsc --strict --noEmit --target ES2020 --module commonjs`): **passed**.
- GitHub source-contract assertions against the branch: **11/11 passed**, including picker guards, test wiring, focus/foreground lifecycle, the web/native four-image backend contract, and patient ownership checks.
- The full mobile `npm test`, full Android `tsc`, Expo export, Gradle/APK and full Python security suites were **not run** in this pass. The repository could not be cloned from this runtime; the isolated checks above are not substitutes for the full suites.

### CI and release boundary
At the starting head `aa264af`, Android typecheck/APK and Security recovery, Admin security and Expert social all failed with **zero workflow steps**; the step endpoint returned empty arrays, logs returned `BlobNotFound 404`, artifacts were empty and combined commit status had no entries. Therefore `npm ci`, `tsc`, Gradle and pytest did not start. This is a runner/execution-allocation failure, not evidence that source tests failed or passed. The exact repository billing/hosted-runner permission cause remains unexposed by the available GitHub records.

PR #257 remains Draft/open. No main merge, production deploy, database migration, APK/IPA publication or live patient-record mutation was performed.


### CI recheck after the media changes — 2026-11-16 10:52 UTC

The branch was checked again after the code and tracker commits. PR head is now `7bf7c686087b889e4079b6047d65f0c0948a24a1`. Four workflows were created for that exact SHA and all concluded failure:
- Mobile Android CI: run `43852618345` — `beta-apk` and `typecheck` jobs both have empty step arrays.
- Security recovery: run `43852618364` — `security` job has an empty step array.
- Expert social: run `43852618369` — `regression` job has an empty step array.
- Admin security: run `43852619602` — `security` job has an empty step array.

The job-log requests for Android typecheck and both security jobs returned `BlobNotFound 404`; all four runs exposed zero artifacts, and the code-bearing commit's combined status was empty. This confirms that the current CI failure is before any test/build step, not a red assertion or a TypeScript diagnostic. The 10/10 isolated picker tests and isolated strict TypeScript check above remain the only executed checks for this pass. Full Android typecheck/APK and server security regressions remain blocked.


## 2026-11-16 — Support-ticket notification deep links

Web reference checked before implementation: `support_request.html`, `_support_status_regions.html`, the authenticated support conversation handlers and the native `Notifications` / `NativeSupportRequests` flow. Previously, support notifications opened only the inbox root, so the user had to locate the relevant ticket manually.

- User-facing support-message and status notifications now carry the owned `ticket_id` in the same-origin `/support-request?ticket_id=...` target. Report updates use the linked report ticket when one exists.
- Native notification routing parses only the `ticket_id` query parameter, rejects malformed/zero/unsafe identifiers, and passes a numeric ID to the support screen.
- The native screen opens that ID only through the existing authenticated `getSupportTicket` owner-scoped API, then marks the returned conversation read. No notification payload is treated as ticket content or authorization.
- The web support page reads the same query parameter and expands/scrolls to the matching ticket already rendered for the signed-in owner. Unknown or unauthorized IDs reveal no ticket data.
- Added native route, support-screen contract, backend notification-target and web-template regressions.

Validation boundary: source-contract edits and Git object creation are complete; full mobile Node/TypeScript, Python support lifecycle, Android build and security suites still require a GitHub Actions runner. The latest pre-change CI jobs all failed with `runner_id=0`, empty runner names and `steps=[]`; no compiler, Gradle or pytest step started. No green CI is claimed.


## 2026-11-16 — Native patient-profile visual and action parity

Web-first source review: `app/templates/patient_detail.html` was compared with `mobile/src/NativePatientProfile.tsx` and `mobile/tests/patientProfileUI.cjs`. The web profile's order is retained: patient identity/complaint, expert consultation, four quick actions (tooth chart, AI analysis, appointment, treatment), collapsible patient information, clinical media, analysis history and treatment history. The public site could not be rendered in the browser tool in this run, so this is a template/handler-level comparison rather than a physical screenshot acceptance.

Changes on `feature/mobile-web-parity-20261110`:
- Added a pure, typed patient-profile presentation model for the four web-ordered quick actions and identity labels.
- Patient names with missing/blank fields now show a safe `İsimsiz Hasta` label; initials have a deterministic fallback; age zero remains visible as `0 yaş`.
- Replaced the plain text consultation action with an accessible navy CTA and gave the chief complaint its own readable summary panel.
- Replaced plain text action buttons with a responsive two-column native tile grid, retaining the exact existing navigation/mutation callbacks. Every tile has a screen-reader label/hint and at least a 44-point touch target. The treatment tile still opens the existing durable treatment-intent editor; no new API or clinical mutation was introduced.
- Added regression coverage for the presentation helper, action ordering, accessible targets, callback wiring, unnamed patient fallback and age zero. Existing account-scope, optimistic-write and treatment-recovery tests remain in the same test file.

Commits created in this pass:
- `patientProfilePresentation.ts` — typed presentation data and safe identity formatting.
- `bc6ac019` — profile identity, complaint and consultation CTA.
- `b589916a` — web-ordered native quick-action tiles.
- `f017e942` — profile presentation/action regression coverage.
- This tracker update records the evidence and limits for the pass.

Executed validation: isolated strict TypeScript compile of the new presentation helper passed; seven isolated runtime assertions passed. Repository React Native renderer tests, full `npm run typecheck`, `npm test`, Android Gradle/APK and Python security suites were not run in this environment; React Native/Expo dependencies and the full checkout are unavailable here.

CI root-cause evidence before this pass (code HEAD `31d8c7c`): Android run `43866434958` had typecheck job `133296063956` and APK job `133296063558`; Security recovery run `43866434947` had job `133296064194`; Admin security run `43866434983` had job `133296064492`; Expert social run `43866434981` had job `133296063796`. All five jobs returned `steps=[]`; log downloads were empty and no compiler, Gradle or pytest step started. This is a pre-step runner-allocation/execution failure, not a TypeScript diagnostic or a failing security assertion. The exact hosted-runner/account/billing setting remains inaccessible through the repository code API and needs repository-owner inspection.

PR #257 remains open/Draft. No main merge, production deploy, APK/IPA publication, database migration or live patient-data mutation occurred. Next module after this patient-profile pass: tooth-chart visual comparison on real Android/iOS widths, then the remaining clinical-media upload recovery acceptance.


## 2026-11-16 — native clinical-media batch quota parity

Web-first review was performed before changing the native upload path: app/templates/patient_detail.html posts the selected archive as one multipart request to /patients/{patient_id}/media; that handler validates the 12-file / 96 MiB batch before saving. The mobile flow intentionally uploads files sequentially to /api/mobile/v1/patients/{patient_id}/media, but the server previously enforced only the per-request/per-file limit. The native picker alone enforced 96 MiB, so a client that did not preserve the original selection boundary could exceed the intended single-batch aggregate across requests.

Changes on feature/mobile-web-parity-20261110:

- The native multipart contract now requires both a stable per-file request_key and a batch_id.
- The batch ID is stored in the SecureStore pending intent, survives retries/app restarts, and is added once to legacy pending drafts when they are reopened. The encrypted file payloads, per-file request keys and patient/account scope remain unchanged.
- The backend copy helper returns the original streamed byte count (before Pillow re-encoding). Each committed patient-media receipt stores that byte count and opaque batch ID in existing WorkJob result_ref/payload_json; no new table or migration was added.
- Under the owned patient row lock, the server sums only receipts for the same authenticated owner, patient and batch ID, then enforces the 12-file / 96 MiB aggregate before object persistence. Existing per-file receipts are checked first, so an exact retry does not consume quota twice. Malformed batch receipts fail closed.
- HTTP 413/422/400/403/404 responses are treated as definite rejections in the native screen, allowing the user to clear or split a rejected pending group instead of being stuck in the ambiguous-retry state.
- The native API test now asserts that the batch ID is actually sent. Added helper tests for stable/migrated batch identity and Python regressions for aggregate bytes across requests, exact receipt replay, file count, required batch metadata, and owner/patient isolation.
- Distinct batch IDs are distinct archive submissions. This change enforces the 12-file / 96 MiB limit for each declared submission; it does not introduce a per-patient/day storage quota.

Commits in this pass: 16 implementation/test/docs commits plus three tracker-bookkeeping commits (19 commits after the prior profile HEAD).

Implementation/test/docs: 89e4719, 1a65f7a, 102aee6, 4fe85ef, f01e035, a10eacd, be80f5d, 92a7c4e, 57e0255, 68b3e84, 9605eaf, 2b0f9c6, 837cc27, dd7e19e, 59eab4f, 7d4e009.

Tracker bookkeeping: fae04ea, 361cb8d, b854084.

Validation status: 14/14 source-level contract assertions passed, including batch-ID persistence/transmission, replay-before-quota ordering, owner/patient/batch scoping, pre-persistence quota admission, malformed-receipt rejection, test registration and whitespace checks. The new Python and Node regressions are committed and registered in mobile/package.json, but they have **not** been executed locally in this environment. No claim of a passing full Android typecheck or full test suite is made.

CI was rechecked at final code HEAD b854084bd425dd7003c5702cc9920ddb8e4069e2. Android run 43888944277 (typecheck job 133374591807; beta APK job 133374592262), Admin security run 43888944304 (job 133374591840), Expert social run 43888944618 (job 133374592494), and Security recovery run 43888944383 (job 133374592069) all started and failed within 2 seconds with runner_id=0, empty runner_name, steps=[], and no artifacts. Android job-log download returns Azure BlobNotFound 404; the combined commit status is empty. The same pre-step signature was present at the earlier profile HEAD. Therefore no TypeScript compiler, Gradle, pytest or security assertion has run; this is a hosted-runner allocation/execution failure, not evidence of a code-level test failure. The repository API does not expose the account-level hosted-runner/billing setting needed to identify the final administrative cause.

PR #257 remains open/Draft. No main merge, production deploy, APK/IPA publication, migration, or live patient-data mutation occurred. Next blocker: repository owner must restore GitHub-hosted runner allocation so the committed backend/native regressions and Android typecheck can actually execute. After that, continue web-first tooth-chart visual parity and real-device clinical-media recovery acceptance.

## 2026-11-16 — Web tooth-chart initial focus wired into native

Web-first comparison completed before native edits: app/templates/tooth_chart.html consumes latest_analysis_tooth; app/main.py selects only AI_ANALYZED, AI_FINAL, and VISION_READY analyses with valid adult/primary FDI numbers, ordered by created_at DESC, id DESC. The PR already contained /patients/{patient_id}/tooth-chart/focus at starting HEAD 64b7f66, but the native chart and mobile/src/api.ts did not call it. This left the API unused and the web's initial analysis-tooth focus absent from mobile.

Branch-only correction:
- Added getToothChartFocus with patient-ID validation, explicit null handling, and fail-closed FDI response validation.
- NativeToothChart now fetches the focus independently from the patient detail read; a failed focus request does not block the chart.
- The native chart opens the latest permanent or primary tooth, applies its saved status/note, and scrolls to the selected detail. A pending SecureStore treatment intent and any tooth already selected by the clinician take precedence over the asynchronous focus response.
- Added component regressions for permanent/primary focus and late-response selection safety; added API contract regressions for authentication, invalid patient IDs, malformed FDI values and no-analysis responses; wired the API tests into test:beta.
- A follow-up race review also protects an explicit manual dentition toggle: a late focus response cannot switch a clinician from primary back to permanent teeth (or vice versa). Added a dedicated lifecycle regression.
- Added backend parity/security coverage for latest eligible analysis, deterministic created_at/id ordering, ignored draft/invalid FDI rows, explicit no-analysis, and owner isolation (404 for another owner's patient and unknown patient).

Commits: e96e8ac (API contract), cdd5c1c (native integration), 21ec03f (component regressions), 9bee448 (API tests), cef5f4d (beta test registration), d721154 + dfa8b93 (backend ownership/order regression), b09a336 + 85cd88b (component assertion corrections), 2baca3a + 1181524 (manual dentition choice and late-response regression).

CI at the starting code HEAD 64b7f66: Android run 43889893814 (typecheck job 133377938483, beta-APK job 133377938044), Security recovery 43889893753 / job 133377938699, Admin security 43889893813 / job 133377940536, and Expert social 43889893789 / job 133377937796 all concluded failure. The GitHub job records exposed no executed steps (steps: null, no log URL); downloading job logs returned BlobNotFound 404. Thus npm ci, tsc, Gradle and pytest did not produce source-level results. The current records do not expose the precise hosted-runner/account/billing cause; repository Actions runner availability/usage remains an external blocker. These are not diagnosed TypeScript or security-test assertion failures, and no green CI is claimed.

The new regression tests and current code commits have not been executed by GitHub Actions in this run. No local full-repository checkout/dependency environment or physical Android/iOS device was available, so no full npm test, pytest, Expo export, Gradle build or device acceptance is claimed. No main merge, production deploy, database migration, APK/IPA publication or clinical record mutation.

Next: resolve hosted-runner allocation at repository/account level so the committed Android/security suites can execute; then continue the web-first clinical-media recovery and visual comparison on real Android/iOS sizes. The 60,000-user capacity target remains unverified.
