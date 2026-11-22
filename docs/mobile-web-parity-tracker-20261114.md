## Latest CI and upload-recovery follow-up — 2026-11-22

Starting head `ec31691f093918f72936264a31a7f1ca4ed681e3` was checked against live GitHub Actions before further edits.

- Mobile Android run [#44978631156](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44978631156) completed successfully. Its typecheck, session/auth, realtime/pagination, beta regression, Android+iOS Expo export and internal APK jobs all completed successfully; the APK artifact was uploaded. This is a CI internal test APK, not a store-signed or device-accepted release.
- Security recovery [#44978631170](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44978631170) ran the Python suite: 613 passed, one failed. The only failure was `test_registered_clinical_media_routes_use_the_expected_private_handlers`: it compared Python callable object identity across FastAPI router inclusion and found zero matches for the canonical `app.mobile_api.mobile_patient_media` symbol. Native security jobs all passed. PostgreSQL and duplicate-submission steps were skipped because the Python step failed.
- The route regression now compares the unwrapped fully-qualified endpoint symbol (module + qualname), while still requiring exactly one mounted route with the expected HTTP method and path. It continues to assert the actual private handler implementation and ownership boundary.
- The security workflow now explicitly executes `tests/test_web_analysis_upload_recovery.py`; that file existed but was omitted from the Python CI command. A workflow-contract test prevents this coverage from silently disappearing again.
- The partial-upload test now advances the 30-second grace receipt and exercises the existing garbage collector, verifying that both orphaned files are deleted and both durable cleanup rows are consumed. The committed-asset test still verifies that a live reference prevents deletion.

These changes are committed on `feature/mobile-web-parity-20261110`. Final-head CI is still required to validate the route-symbol correction and newly wired web cleanup tests. No local pytest execution is claimed in this connector-only session. No main merge, live deploy, production database mutation or patient-file operation was performed.

---

# Dental AI mobile completion tracker

## Working contract

Continue the existing React Native / Expo application in `mobile/`; preserve completed code, web rules, FastAPI/PostgreSQL/Render orchestration and Modal inference. Target Android `tr.dentalai.app`, iOS and Expo `dentalai47/dental-ai`. Do not replace functioning flows with mock data, WebViews or decorative screens. A successful APK build or unit test does not establish device acceptance.

Branch: `feature/mobile-web-parity-20261110`. PR: #257 (draft). Tracking issue: #258. No main merge, live backend deployment or store publication without separate approval. No patient information, passwords, codes, session tokens, clinical images or private messages in logs/reports.

## Order and evidence

| Priority / heading | Existing native entry | Current evidence | Remaining acceptance/work |
|---|---|---|---|
| P0 Android CI / API / session | api.ts, sessionExpiry, useSessionHealth | At this run's start, PR head `70436c9` had 0 workflow runs and 0 combined commit statuses. Mobile Android, Android APK and Security Recovery remain `workflow_dispatch`-only. Previously retrieved hosted runs failed before their first step with `runner_id=0`, `runner_group_id=0`, empty steps and unavailable logs; npm/tsc, Node, Gradle and pytest did not start. No workflow was dispatched in this run, so no notification storm was restarted. This is an external hosted-runner allocation failure, not evidence of a TypeScript source error; the repository API does not expose the exact owner/billing cause. No green CI or Android typecheck is claimed. |
| P0 Login / registration / recovery | NativeAuth, authApi, mobile_account_api | Native registration, web consent/title rules, OTP, generic password recovery, single-use reset and session revocation tested locally | Real mail/device/OS links, native admin MFA, refresh/session lifecycle acceptance |
| P0 Patients and loading states | App Patients, NativeNewPatient | Real owned records, pagination, create/duplicate selection, calendar birth date; errors separated from empty data | Authenticated production/device spinner reproduction, large-list/slow/offline acceptance |
| P1 Patient profile | NativePatientProfile / History / Media / Appointment | Web/native profile edit shares a SHA-256 revision fingerprint over editable fields and address; PostgreSQL row locks plus stale-revision 409 prevent stale snapshots overwriting newer data. Native preserves draft and offers explicit reload/reapply. Treatment create/update now use durable server receipts, SecureStore request keys and treatment `edit_revision`; the web flow has no delete action, so no extra native delete was invented. Native profile and tooth chart now share the same account/patient intent scope | Backend/native regressions are committed but CI cannot execute; two-account web/native physical-device acceptance and full treatment history/device acceptance remain open |
| P1 Tooth chart | NativeToothChart, NativeToothVisual | Same FDI32/20, bundled enamel atlas/implant, web status paths/gradients, patient/tooth history and save APIs. Treatment create/update now use durable account+patient intents, stable request keys and treatment `edit_revision`; uncertain responses recover explicitly. Native chart now also renders the web's patient-right/patient-left labels on both jaws and preserves the complete web FDI quadrant order | Six treatment/visual regressions are committed but unexecuted because Actions has no runner. Native extracted-tooth rendering now applies the shared enamel atlas through an SVG grayscale/70%-brightness matrix matching the web CSS; Android/iOS screenshot comparison, small-screen fidelity and clinical acceptance remain open |
| P1 Clinical media | NativePatientMedia and MediaGallery | Web-first gallery parity includes multi-select/sequential archive upload, encrypted local pending intent, stable per-file request keys, server receipt/status reconciliation after process restart, batch quota, byte-level progress, gallery/zoom/owned deletion/delete-all and saved+new analysis composition. Shared sanitizer strips EXIF/ancillary metadata. New receipt source hashes are HMAC-SHA256 with dedicated secret and owner+patient scope; old receipt hashes upgrade lazily on authenticated replay/status lookup | Configure stable `PATIENT_MEDIA_RECEIPT_KEY` before deployment; historical receipts not accessed yet retain legacy hashes; legacy archived originals are not rewritten; camera/background/large-file/offline and Android/iOS visual/device acceptance remain open |
| P1 Image AI | NativeDentalAI / NativeClinicalReview, mobile_clinical_api, mobile_analysis_api | Web result/review flow retained; native gallery combines up to four saved and new images in one durable VISION intent; clinical-information-only requests create a receipt-backed PRELIMINARY job with no fake ImageAsset; shared sanitizer now cleans new direct uploads and selected-media analysis copies before classification/provider work | Mixed-media, clinical-only and sanitizer regressions are committed but not fully executed; legacy archive originals remain unchanged; native note-intent recovery across process restarts is now implemented; server-side idempotency receipts for web/native note writes and production inference/device/concurrency acceptance remain open |
| P1 Voice examination | VoiceExamEntry / NativeVoiceRecorder / NativeVoiceApproval | Real Expo Audio chunk recording, pause/resume, sequential transcription, secure text draft/recovery, finish-only clinical handoff, canonical explicit approval/appointment and idempotent receipt; native entry mirrors web's anonymous-new-patient action; long examinations match web's 72k-character / 216 KB envelope with 12k/36 KB extraction chunks and scoped SecureStore checkpoints; cumulative MM:SS duration now persists across 15-second file rotations, pauses and draft restore (legacy drafts default to zero) | Duration accumulation/restore regressions are committed but not run. Long-transcript/checkpoint repository regressions also remain unrun. Physical Android/iOS audio/noise/Bluetooth/interruptions, production ASR/final/source quality, raw-file retention/encryption, process death/durable jobs and clinical acceptance remain open |
| P2 Program / appointments | NativeProgram / Editor, shared patient appointment entry | Web-derived day/week/month occurrences and pagination, shared full editor, edit/copy/complete/delete, reminder-queue parity, recurrence and owned conflict advice tested locally | Device/real notifications, atomic concurrency/idempotency and performance acceptance; conflict advice is not an atomic exclusion guarantee |
| P2 Dental Flow | SocialScreens / socialApi | Web-first audit closed specialty filters, per-author follow, expert-directory/support entry and canonical sharing. Native media viewer now has bounded zoom/pan/gallery navigation. Owner moderation refresh reuses the existing owner-checked `/moderation-status/POST/{id}` endpoint (minimal status/version/metadata only); app resume and navigation return refresh at most five owned PENDING/REJECTED cards, two concurrent, with a 15-second duplicate-event gate and account/token/version guards. No polling or new backend route. Evidence: `docs/mobile-dental-flow-moderation-resume-20261118.md` | Admin moderation queue is not claimed as native; full React renderer/backend pytest and repository typecheck remain blocked by runner allocation; Android/iOS foreground/two-account device acceptance and 60k-load validation remain open |
| P2 Academic AI | NativeAcademic / NativeAcademicComposer / Source / File / AnswerText, mobile_academic_api | Owned course/material flows, native progress/index, durable run receipt/reopen, structured grading/learning/source/feedback/history and current-run cancellation mirror canonical web handlers; the fixed question composer preserves drafts and the web 8,000-character limit. Native multi-file selection now persists the complete <=12-file batch in chunked SecureStore before the first upload, then sequentially hashes/uploads each item with owner/course/request-key receipts, SHA-256 binding, v2-to-v3 recovery and legacy single-intent migration. Receipt mismatches preserve local files and queue state. Fresh uploads avoid a redundant receipt read | Fourteen queue/hash/migration/receipt regressions are registered in `test:beta` and the manual-only `native-academic-security` job but not executed; Android typecheck/CI runner, 150 MB physical-device time/battery, offline/process-death, provider/Modal acceptance, rich math/clipboard, Android image zoom and 60k load acceptance remain open. Evidence: `docs/mobile-academic-upload-batch-recovery-20261119.md` |
| P2 Expert profile / publications | NativeExpertProfile / NativePublications / directory | Native public identity/hero and Posts/Publications/About tabs, real performance, native management, structured CRUD/version/DOI/ORCID/share and busy-profile entry; prior application/document/rules preserved | Remaining settings/import drafts and real provider/device/concurrency acceptance; native private relationships and owned performance/policy/event panel now use canonical web helpers/APIs |
| P2 Consultation request | NativeConsultationRequest | Owned patient/media, fee/urgency/context, canonical receipt and uncertain-create recovery tested earlier | Real two-account lifecycle/payment/deadline/background acceptance |
| P2 Messages | Consultations / ConsultationChat / NativeChat tools | Replies, images/PDF/audio, annotation copies, selected case media, web lifecycle actions and authorization tested locally | Durable text/media idempotency, retained drafts/reconnection/deletion deadlines and full two-account Android/iOS behavior |
| P2 Account / profile | NativeAccount | Name/username/photo, password/email security, separate professional/document and expert accordions, title/document/application/rules/availability and shared identity refresh tested locally; native self-erasure now invokes the canonical web deletion handler with username + current-password confirmation and admin exclusion | Native self-erasure endpoint/UI and backend/React regressions are committed but not executed in this runtime; real device, session revocation, deletion job/storage cleanup and live acceptance remain |
| P2 Notifications | Existing center, native target resolver and read-state API | Web case, expert directory/profile, Program, patient and `/support-request?ticket_id=` targets map to authenticated native screens; full unread count is independent of the 20-item list page; explicit cutoff-scoped read-all preserves newer notices; Home badge refreshes on focus; premature OS permission prompt removed | Expo push token acquisition/registration, killed-app response routing, OS delivery, token rotation/account-switch/device acceptance; committed backend/native tests still need CI execution |
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

Evidence so far: `mobile-mixed-analysis-media-20261116.md`, `mobile-p0-verification-20261114.md`, `mobile-chat-patient-audit-20261114.md`, `mobile-patient-profile-parity-20261114.md`, `mobile-auth-account-parity-20261114.md`, `mobile-program-parity-20261114.md`, `mobile-professional-parity-20261114.md`, `mobile-expert-publications-parity-20261114.md`, `mobile-voice-workflow-20261114.md`, `mobile-academic-workflow-20261114.md`, `mobile-academic-upload-content-binding-20261119.md`, `mobile-academic-upload-batch-recovery-20261119.md`, `mobile-clinical-workflow-20261115.md`, `mobile-relationships-20261115.md`, `mobile-analysis-upload-20261115.md`, `mobile-vision-viewer-20261115.md`, `mobile-expert-performance-20261115.md`. Selected-media clinical context: ba5969a / 8d36c7a / 6f8fe33 / 464770e / ffacfd9 / a0d62c4. Regression sources are committed but not executed in this runtime; do not mark them green. Counts belong to their individual commits and must not be presented as current evidence after untested edits.

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


## Durable clinical note recovery — 2026-11-16

Compared the web result/viewer note handlers and native clinical review. The web handler appends exact text to `clinical_notes` without a request receipt, while native previously kept its uncertain-note lock only in component state. Added bounded account/analysis/FDI-scoped note intent validation, SecureStore persistence before POST, exact-line reconciliation against the canonical workspace after process restart, and explicit server-check-before-retry UI. An already-committed note clears locally without resubmission; an absent note retains the exact draft and blocks edits/automatic retries until the clinician explicitly checks and confirms retry.

Commits: `d0bdfb8`, `64f9b50`, `3499ed2`, `32ebf33`, `bcc3403`. Node regressions cover uncertain write persistence, server-present/server-absent restore, retry gating, FDI/account scoping and canonical line format. They are committed, not executed. This does not provide server-side idempotency across independent devices; a durable server receipt and concurrent PostgreSQL regression remain required. No main merge, deploy or app publication.

## 2026-11-16 — Patient profile form validation follow-up

Web-first flow checked: `app/templates/patient_detail.html` → `POST /patients/{id}/edit`; native counterpart: `NativePatientProfile` → `editPatient` → `PUT /api/mobile/v1/patients/{id}`. The web and canonical mobile backend both require first/last name and accept an optional phone only when it matches `05[0-9]{9}`. Native had the backend rule but no matching client preflight and an oversized 2,000-character TextInput limit.

Added the shared pure validator, native 11-character phone cap and pre-network rejection. T.C. identity validation was deliberately not strengthened beyond the web's existing max-length contract. Renderer and helper regressions cover the validation matrix, no request on invalid input, valid request payload and expected-revision preservation.

Commits in this pass: `d14b720`, `93e87fe`, `750534f`, `56c0e05`, `f0d902f`. The test file is already part of `npm run test:beta`; no package script change was necessary.

### Latest CI root-cause check

At starting HEAD `a50e861eb572084788ada4cc2bb81546f7eb30aa`, latest PR runs were Android `43922638450`, Security recovery `43922638514`, Admin security `43922638623`, and Expert social `43922638505`. Android typecheck job `133493654462` and security job `133493654917` completed failure with no step records; both log downloads returned Azure `BlobNotFound 404`. The combined commit status was empty. Thus npm install, `tsc`, Node tests, Gradle and pytest never started. The repeated `runner_id=0` / blank runner / empty-step signature from earlier runs is consistent with hosted-runner allocation failing before workflow execution. Repository code and the available GitHub Actions records do not expose the account billing/hosted-runner entitlement needed to fix that administrative cause. It is not evidence of a source-level TypeScript or security assertion failure, and no CI pass is claimed.

No workflow was weakened or redirected to an untrusted runner to mask this blocker. No main merge, production deploy, migration, APK/IPA publication or patient-data mutation. The new profile tests are committed but await a functioning Actions runner (or an owner-run checkout).

Next priority follows issue #258's package order: voice-exam functional parity (native start/pause/stop, durable transcript recovery, extraction/uncertainty handling, clinician approval and approved-field persistence without automatic chart writes). After that, complete the remaining tooth-chart surface/history parity and then clinical-media / AI image-analysis result parity. Android/iOS device appearance and 60,000-user load acceptance remain open.

## 2026-11-16 — Tooth-chart close-panel parity

Reviewed the canonical `app/templates/tooth_chart.html` before editing. The web chart's selected-tooth sheet has an explicit close button; native previously left the detail card open until another tooth or dentition was selected. Added the accessible native close control and a guarded dismissal handler. Normal dismissal clears only transient selection/editor state and preserves the FDI tooth and all persisted clinical data. Dismissal is disabled during writes or while a durable treatment intent is pending, so the clinician cannot hide the only reconciliation path for an uncertain mutation.

Commits: `af96bf1` (native close action), `b501e8b` (normal dismissal regression), `01ec19d` (pending-intent safety regression), `63b3d8b` (tooth-chart evidence note). This tracker update is the fifth commit in the tooth-panel follow-up. Both tests are part of the existing `test:beta` command.

Latest code-head CI recheck: Android run `43927164752` (typecheck job `133509569657`, beta-APK job `133509570297`), Security recovery `43927164668` / job `133509571306`, Admin security `43927164241` / job `133509567447`, and Expert social `43927164467` / job `133509570706` all concluded failure. Typecheck and security job-step queries returned empty arrays; all five log downloads returned `BlobNotFound 404`; combined commit status was empty. No npm install, repository tsc, Node regression, Gradle or pytest step started. This is a pre-runner execution failure, not a reported assertion/compiler diagnostic. Separately, the changed patient-profile presentation helper was copied from the committed source into an isolated check: strict TypeScript compile passed and nine validation assertions passed. This does not substitute for the React Native renderer suite or full project typecheck. No full checkout/dependency tree, Expo export, Gradle build or device screenshot test is available here.

No main merge, production deployment, schema change, APK/IPA publication or patient-data mutation. Next: continue issue #258 in order with voice-exam functional parity; then finish remaining tooth-chart surface/history behavior, clinical-media and AI image-analysis parity, program/appointments, Dental Akış, academic AI, expert support, account/notifications and 60,000-user load acceptance.


## 2026-11-16 — native prior voice-history parity

Web references checked first: `app/templates/voice_exam_panel.html`, `app/static/voice-exam.js` history handlers, and `app/voice_exam.py` history route. Native previously lacked the web “Önceki bilgiler” read/confirm/add flow.

The web query is now shared through `reviewed_history_payload`; the mobile GET adapter uses the same completed `VOICE_REVIEW` records, patient-owner check, field allowlist and 12-record bound. The mobile response is `private, no-store`, varies by Authorization and excludes raw audio/transcript. Native displays the prior approved fields with their source analysis ID, requires a separate patient-confirmation action before adding them to the draft, and leaves final field selection unchecked. Current-vs-prior conflicts remain visible as uncertainty; history retrieval never writes to the patient chart.

Tests added: native API request/provenance validation, native confirmation/conflict UI flow, and backend owner/completed-job/non-voice archive isolation. Commits: `4a714ad`, `21023b1`, `cb12383`, `058593c`, `cdcaa14`, `e138111`, `5166a77`, `97af24f`.

The tests are committed but were not run here. Latest Actions still report runner allocation failure (`runner_id=0`, no executed steps, job log `BlobNotFound 404`); do not treat this as a compiler/test result. No main merge, production deploy, schema migration, APK/IPA publication or patient-record mutation.

Next module after this voice-history parity increment: remaining tooth-chart surface/history parity, then clinical-media and AI image-analysis result parity. Voice microphone/device acceptance and provider accuracy still require real Android/iOS devices.


## Latest continuation — voice evidence visibility (2026-11-16)

Web-first comparison: `app/templates/voice_exam_panel.html` + `app/static/voice-exam.js` render an expandable supporting quote for every extracted field and distinguish prior approved history. Native previously showed only the extracted value in both the review and final approval checklist. Added a shared native evidence presenter and displayed the exact bounded quote, history/current provenance, missing-evidence warning and clinician-edited marker in both stages; tooth selections show their supporting quote too. Field quotes remain display-only and are not added to the patient profile payload. No provider/API/schema/automatic-write changes.

Commits: `b952919` helper, `8c60646` review UI, `a8539cd` approval UI, `b96c1d5` regression suite, `d0ab2cf` payload assertion, `90b6574` test registration, `b0caa94` CommonJS test fix, `995974e` voice workflow evidence note. Four isolated helper tests passed; integration/source-contract test is registered but not yet run with the full mobile dependency tree. No full typecheck, beta suite, Android/iOS device test or clinical acceptance is claimed.

The next gate remains execution of the full suite on a working runner and physical-device review. No main merge, production deploy, patient mutation or store publication.


## Newly confirmed next voice gap — uncertain ASR retry (2026-11-16)

Web/native endpoint comparison found a remaining reliability and cost issue. `mobile/src/nativeVoiceAudio.ts` uploads each retained clip without a stable segment request key. `app/mobile_api.py:mobile_voice_audio` streams the clip and calls `core.extract(..., transcription_only=True)`, then returns the transcript without a durable receipt/deduplication record. If Gemini completes but the response is lost, the native recorder correctly keeps the local clip and a retry can invoke transcription again; the caller cannot reconcile the first result and may append a duplicate segment.

No quick client-only fix is safe: the server must be able to replay the exact result after a lost response, while transcript data is sensitive and raw audio must remain unpersisted. Next voice work should evaluate a short-lived, encrypted, owner+patient+segment-key+audio-digest receipt with strict TTL/size bounds, same-key/different-content rejection, cross-account isolation and process-death recovery. This is an identified open issue, not implemented or accepted.


## Implemented — native voice ASR idempotency and recovery (2026-11-16)

The previously open uncertain-retry finding is now implemented on
feature/mobile-web-parity-20261110. Before changing native code, the browser flow
was rechecked in voice_exam_panel.html and voice-exam.js and compared with the
mobile_voice_audio endpoint. The browser keeps its pending audio result in the
page flow; the native adapter had no durable receipt after its Gemini call.

Changes:
- NativeVoiceRecorder now sends its persisted SecureStore segment UUID as
  X-Voice-Request-Key. A retry of the same retained clip reuses the same key.
- The backend computes a keyed HMAC fingerprint over canonical MIME plus streamed audio
  bytes and scopes the receipt by authenticated owner, patient and segment key. Same key/different
  bytes is rejected with 409 before Gemini.
- The existing WorkJob table is reused without a schema migration. The only
  stored result is an AES-GCM encrypted transcript plus patient revision; raw
  audio is not stored and no patient chart field is written.
- A 180-second processing lease distinguishes an active request from an
  abandoned one. A completed receipt replays the exact transcript. An expired
  in-flight lease becomes terminal OUTCOME_UNKNOWN; it is not automatically
  submitted to Gemini again because the provider may already have completed.
- Capacity/configuration rejections classified before provider invocation are
  RETRYABLE with the same key. Other ambiguous provider failures are terminal.
- The native UI preserves the clip and offers a new-key attempt only after an
  explicit warning that another Gemini call and provider charge may occur.
  The new key is written to SecureStore before the in-memory draft is changed.
- The encrypted result expires after 24 hours. A bounded worker cleanup clears
  ciphertext and retains tombstones for seven days; cleanup is throttled to
  five-minute intervals and processes at most 100 receipts per pass. Receipts
  whose patient no longer exists or is no longer owned by the receipt owner are
  removed during the same bounded cleanup.
- render.yaml declares VOICE_ASR_RECEIPT_KEY as a secret. It must be set to a
  32-byte random value encoded as 64 hex characters before native audio uploads
  can be deployed. Missing configuration fails closed with HTTP 503.

Verification performed in this workspace:
- Native ASR client harness: 5/5 tests passed on Node 22.16.0.
- Strict TypeScript check for nativeVoiceAudio.ts passed with local Expo/API
  declaration stubs; NativeVoiceRecorder.tsx transpile/syntax check passed.
- AES-GCM round-trip, plaintext-absence and AAD tamper rejection checks passed.
- 12 Python regression tests were added for replay, different-content conflict,
  owner/patient isolation, active/expired leases, 24-hour TTL, retryable
  pre-provider failures, tamper rejection, cleanup and typed core errors.
  They were not executed here because SQLModel is not installed in the local
  sandbox; GitHub Actions jobs also failed before exposing any runner steps.
- Latest Android typecheck, beta APK, voice and security jobs have empty step
  arrays and their log downloads return BlobNotFound. This is a GitHub Actions
  runner/log-artifact infrastructure blocker, not an observed compiler/test
  assertion. The repository cannot repair runner provisioning through a code
  patch. Full project CI and Python regression execution remain required.

Implementation commits now end at 2c4507fd2fec4aace8602239e50318963db06889 (27 commits since starting HEAD 9dadd0c); this tracker update follows. No main merge,
production deployment, APK/IPA release or patient-record mutation occurred.

## 2026-11-16 — Clinical media receipt fingerprint privacy hardening

Web-first audit confirmed the native gallery already has durable encrypted upload intents, stable per-file request IDs, server-side replay/status receipts, batch quota and byte-level progress; the earlier tracker row was stale and is corrected above. The remaining source-level privacy gap was in the receipt itself: `WorkJob.source_hash` stored an unkeyed SHA-256 fingerprint of the sanitized image plus metadata. A database reader with a candidate image could compare that digest offline, and equal uploads could be correlated across patient scopes.

Added a dedicated `PATIENT_MEDIA_RECEIPT_KEY` (32 random bytes / 64 hex characters) and version-1 HMAC-SHA256 fingerprints. The MAC input includes a domain/version label, authenticated owner ID, patient ID and canonical legacy payload digest. The plain legacy digest remains transient only. New receipt payloads carry `fingerprint_version: 1`. Old receipts upgrade lazily, in the same transaction, on authenticated replay or status lookup; changed-content reuse is rejected before mutation. Status-only recovery can key an old digest without reading the image. Missing key returns 503 before file persistence. No table/schema migration, raw image persistence, provider call or bulk receipt scan was introduced.

The secret is declared in `render.yaml` as `sync: false`; the Render value was not configured here. It must be generated independently and kept stable before deploying. Historical receipts not replayed/status-checked yet still have their old unkeyed hash; no claim of a complete historical backfill is made.

Commits: `2b8224d` helper; `9fd799e` mobile upload/replay integration; `28c20fc` Render secret declaration; `1b8712a` helper tests; `722facf` route-level keyed/missing-key/legacy-upgrade tests; `4b9b438` Security recovery workflow registration; `333f777` owner/patient scope and strict version checks; `8203410` tamper regressions; `2b64d14` transient-only legacy digest comment; `8e1a2bc` evidence note. Eight helper tests passed in an isolated scratch harness using the committed helper logic. The complete repository pytest suite and Android typecheck remain unexecuted.

At the starting code HEAD for this pass, `8e3505767e64d61133d323fbba8e337033676836`, Android run `43949158750` and Security recovery `43949158751` failed before a runner step. Rerun attempt 2 created Android jobs `133590671393` / `133590671776` and Security job `133590693258`; each had `runner_id=0`, blank runner name, `steps=[]`, and log downloads returned `BlobNotFound 404`. No npm install, tsc, Gradle or pytest step ran. The workflow definitions use `ubuntu-latest`; the available records do not expose the repository/account-level hosted-runner or billing cause. Do not treat this as a source compiler/test failure.

No main merge, production deploy, APK/IPA publication or patient-data mutation. Next: configure the dedicated secret before any deployment, get GitHub-hosted runner allocation restored, then run the committed Python/security and Android suites and perform physical Android/iOS upload/recovery/visual acceptance.

### CI after clinical-media privacy changes

The code commit that triggered the final verification for this pass was `2b64d14723349d7847ff5762c79155132fb37f66` (the branch tracker-only commits followed it). Current PR runs for that code head:

- Android `43952904636`: typecheck job `133599818758`; beta-APK job `133599818293`.
- Security recovery `43952904610`: job `133599818459`.
- Admin security `43952904639`: job `133599817894`.
- Expert social `43952904559`: job `133599817063`.
- Voice examination `43952904546`: job `133599818446`.

The raw GitHub jobs endpoint confirms every job has `runner_id=0`, empty `runner_name`, `labels=[ubuntu-latest]`, `steps=[]`, and a two-to-three-second start-to-failure interval. Android typecheck, Android APK, Security recovery, Admin security, Expert social and Voice all failed before any workflow step. Job-log downloads for typecheck/security/voice return Azure `BlobNotFound 404`; combined commit status is empty. No npm install, tsc, Gradle, Node regression, pytest or provider test ran. The workflow YAML uses standard `ubuntu-latest`; the available GitHub API does not expose the owner/account-level runner quota, billing or hosted-runner entitlement required to fix this externally. No source-level compiler/test failure has been established.

### Native clinical-media recovery-state correction

A follow-up web/backend/native error-path review found that the newly explicit missing-key 503 was still classified by the native gallery as an ambiguous upload. The route returns this 503 before reading/persisting the file, so the UI must not imply that the server may already have committed it. Added `clinicalMediaRecovery.ts` and updated `NativePatientMedia`: 503 is now a known configuration rejection, the encrypted local draft remains intact, and the user is told not to delete it or create a new batch until the server key is configured. 409/429/5xx/timeouts remain uncertain and continue to require receipt reconciliation.

Commits: `a897a46`, `fb67566`, `e3f374a`, `04413be`. Four isolated Node classifier tests passed; the committed fifth UI/source assertion and full beta/typecheck suite remain unexecuted. No main merge or deploy.


## 2026-11-16 — AI viewer modality-specific attention parity

Web-first references: `vision_service/templates/radiograph_viewer.js`, `vision_service/templates/intraoral_viewer.js`, `app/templates/analysis_viewer.html`, `mobile/src/NativeVisionViewer.tsx` and `mobile/src/visionModel.ts`. The web radiograph viewer includes the `gradcam_attention` pool; the web intraoral viewer intentionally excludes it. Native previously merged that pool for every image modality, allowing an intraoral photo to receive a radiographic attention overlay that the web did not render.

Changed native vision parsing to receive the selected authorized asset's `image_type`. Grad-CAM is now included only for `PANORAMIC`, `BITEWING` and `PERIAPICAL`; `INTRAORAL_PHOTO` and unknown/missing types exclude it. The viewer passes modality on load/focus and reloads when the selected asset or modality changes. Ordinary finding pools, confidence threshold, geometry checks and unlocalized-list behavior are unchanged. No provider/API/DB/polling change.

Regressions added for panoramic/bitewing inclusion, intraoral/unknown exclusion and the viewer-to-parser modality handoff. `visionViewer.cjs` was already part of `test:beta`. This is a source-level parity correction; full beta suite, full Android typecheck/APK, backend pytest, real-device radiograph/intraoral screenshots and clinical acceptance remain required.


### Verification and security-workflow coverage follow-up — 2026-11-16

- The isolated modality parser harness passed **5/5** Node tests (radiographic include, intraoral/unknown/missing fail-closed, unchanged ordinary-finding threshold, invalid-geometry rejection). The exact `visionModel.ts` helper passed strict TypeScript compilation with the installed global compiler.
- `mobile/tests/visionViewer.cjs` source syntax was parsed and its registration in `test:beta` verified. The full React renderer test file and full mobile beta suite were not executed in this runtime because `react` / `react-test-renderer` dependencies are not installed and npm registry access failed with DNS `EAI_AGAIN`. This is not a pass for the full viewer integration test.
- A security-workflow audit found that the new `app/voice_asr_receipts.py` implementation and `tests/test_voice_asr_receipts.py` regression file were missing from both the `security-recovery.yml` pull-request path filter and the security pytest command. Added both paths and added the receipt suite to the command so future changes to the encrypted/idempotent ASR receipt actually run in the security gate.
- Latest code/workflow head at this checkpoint: `5d574b38e2cfd6dd0e4d053a39d596a9de91ff70`. Security recovery run `43957084568`, job `133614369015`, failed with an empty step list; log download returned `BlobNotFound 404`. Therefore the newly wired pytest command did not execute. Android run `43957084397` and Voice run `43957084377` were still queued at the time of this note; their outcomes must be checked again before reporting.
- Full repository typecheck, beta suite, backend pytest, PostgreSQL concurrent receipt test, APK build, physical Android/iOS viewer screenshots and 60k capacity acceptance remain open. No main merge, production deploy, APK/IPA publication or patient-record mutation.


### Final CI result after ASR security-gate wiring — 2026-11-16

Code-bearing head: `5d574b38e2cfd6dd0e4d053a39d596a9de91ff70`; the branch subsequently received tracker-only head `366252b38c053d5241c01e2d19497879609b9ab3`.

- Android run `43957084397`: typecheck job `133614367751`, beta-APK job `133614366918`.
- Security recovery run `43957084568`: job `133614369015`.
- Voice examination run `43957084377`: job `133614368291`.
- All inspected jobs completed failure with empty step arrays; all three log downloads returned `BlobNotFound 404`. Combined status checks are empty. `npm ci`, TypeScript, Node beta tests, Gradle and pytest did not start. The security workflow now includes the ASR receipt test, but that test has not executed yet.

This confirms a pre-step GitHub Actions execution/runner problem, not a failing assertion or compiler diagnostic. The exact owner-level hosted-runner/account/billing cause is not exposed by the available repository records. The repository owner must inspect Actions runner availability and usage/billing. Do not report CI green.


## 2026-11-17 — Native image viewer tab parity

Web-first inspection compared app/templates/analysis_viewer.html, vision_service/templates/radiograph_viewer.html, vision_service/templates/intraoral_viewer.html and their embedded JS with mobile/src/NativeVisionViewer.tsx and NativeClinicalReview.tsx.

The native image viewer previously had only the findings list. The web viewer exposes Bulgular / Tedavi / Klinik Bilgi in the same image context. Added the dark navy three-tab native layout. Treatment selection delegates to the existing authenticated selected-teeth route and canonical PRELIMINARY WorkJob; parent ClinicalReview remains the only job poller/retry owner. Clinical Information delegates to the existing parent durable note-intent/reconciliation path, so uncertain writes preserve the draft and never auto-resubmit. No new API, schema, AI/provider call, polling loop or automatic patient-chart write.

Five renderer regressions added to the already-registered mobile/tests/visionViewer.cjs: tab availability, permanent FDI selection/delegation, confirmed note save, uncertain save preservation, and canonical treatment-result rendering. They are committed but not executed because current Actions jobs fail before runner allocation. Full typecheck, Node suite, Android/iOS device and clinical acceptance remain open.

Commits in this pass: c284ae3 (native viewer UI), e0ec071 (canonical parent actions), 80b3030 (renderer regressions), 580ab8c (viewer documentation); tracker update follows. PR #257 remains Draft. No main merge, live deploy, APK/IPA publication or clinical record mutation.


Follow-up safety review (2026-11-17): completed treatment results now suppress a second Analiz Et action; failed/cancelled retryable jobs use the canonical retry action. An uncertain clinical-note acknowledgement restores the exact pending text into the parent encrypted note workflow and locks a second write until reconciliation. Two more renderer regressions cover these guards. Seven new viewer renderer cases are committed; none is claimed executed while Actions still fails before the first step.

Final viewer interaction pass: tooth chips and both clinical text inputs are now disabled while a parent mutation or unresolved note is pending, preventing the visible draft from diverging from its encrypted intent. One additional renderer test covers the parent-busy treatment lock. Eight new viewer renderer cases are committed in total; still unexecuted until GitHub Actions allocates a runner.


## Dental Flow parity pass (2026-11-17)

Web-first sources reviewed: `app/templates/expert_following.html`, `app/static/expert-social.js`, `app/expert_social_relationships.py`, and the existing native `SocialScreens.tsx` / `socialApi.ts`.

Commit chain from starting HEAD `d566fb2`: 15 focused commits — `5093e35`, `3b237c4`, `fd88507`, `47d5571`, `4a45690`, `702c553`, `d30b3d7`, `30be276`, `aec4576`, `bf99ace`, `790d344`, `c242581`, `0bdf1e4`, `8544034`, plus this final tracker update.

New gaps closed in native code:
- The web's eight authoritative `EXPERT_SPECIALTIES` options are now returned only on the first feed page; subsequent pages do not repeat the static taxonomy. The mobile API validates server metadata and has a compatibility fallback for an older deployed backend.
- Native Discover/Following now exposes horizontally scrollable, accessible specialty chips. The selected specialty is part of the paged-record scope and query, so changing it invalidates prior pages rather than mixing specialties.
- Feed cards now expose per-author follow/unfollow controls. A successful follow updates every visible card for that author; unfollowing from the Following feed removes that author's cards immediately. Writes are serialized per author across all visible cards to prevent duplicate concurrent toggles.
- Native cards expose the web's expert-profile and availability-gated support actions, routing support to the canonical native consultation screen.
- Published cards can share the canonical `/expert-support/expert/{id}?post={id}` URL through the OS share sheet. Pending/unpublished cards disable like/share, and closed comments are shown as closed rather than opening an unusable sheet.
- Security recovery now runs `tests/expert_social/test_dental_flow.py` when the social feed/relationship route changes. Mobile CI path filters also include `app/expert_social_relationships.py`.

Regression coverage added:
- Backend asserts first-page taxonomy metadata and that later cursor pages omit it.
- Mobile API tests cover Turkish query encoding, old-backend fallback, malformed/duplicate taxonomy, removed specialty selection and safe canonical share URLs.
- Native screen tests cover follow propagation callback, expert support action, share sheet payload, pending/closed action guards and filter-scope contracts.

Validation boundary: the isolated Node contract harness passed 11/11 cases; 30/30 source-contract checks against the committed GitHub files passed. Repository `npm run test:beta`, full TypeScript, React renderer, Android build and backend pytest remain unexecuted because GitHub Actions jobs complete with runner ID 0 and zero steps. No patient data is used. No merge/deploy was performed.


## 2026-11-17 — Academic AI fixed composer

Web-first references: `app/templates/notes_ai.html` (`study-chat-clean-footer`, `study-chat-clean-composer`) and `app/static/style.css` compared with `mobile/src/NativeAcademic.tsx`.

The native Academic question input was previously inside the conversation FlatList header and scrolled away with older messages. Added `mobile/src/NativeAcademicComposer.tsx` as a fixed footer sibling to the history list. The course screen retains ownership of the draft; switching between Study, Sources and Questions does not lose it. The composer preserves the 8,000-character web limit, rejects blank sends and locks while sources are not ready, a run is active or an uncertain intent requires recovery. No provider/API/database/polling behavior changed.

Commits: `6d12116` composer component; `543fff2` screen integration; `fd0f1db` standalone renderer tests; `d3456b4` beta-suite registration; `ae3fbe3` integration/draft/tab regressions; `9810556` workflow evidence.

Source-contract checks against the committed files passed **11/11**. React renderer tests are committed but not executed here; full `npm run test:beta`, project typecheck, Android/iOS build and physical keyboard/safe-area acceptance remain open.

Latest code-bearing head `ae3fbe3` CI: Android run `43984303486`, Security recovery `43984303514`, Admin security `43984303446`, Expert social `43984303506`, Voice `43984303433`. All jobs failed before runner allocation (`runner_id=0`, `steps=[]`, `ubuntu-latest`, 2–3 seconds); typecheck logs return `BlobNotFound 404`. This is not a compiler or pytest result. Exact owner-level hosted-runner/account/billing cause is unavailable from repository APIs.

No main merge, live deploy, APK/IPA publication or patient-record mutation.

## 2026-11-17 — Expert Support message/media recovery

Web-first comparison: `app/templates/expert_case_room.html` already sent client intent IDs, but canonical text/media handlers only echoed those IDs. Native text kept its key in memory and native media had no stable key. A response loss or process death could therefore create duplicate consultation messages/attachments.

Implemented:
- Added compact composite-key `ConsultationMessageReceipt(case_id, sender_user_id, client_message_id)`; stores only payload SHA-256, message ID, timestamp. No message text, file bytes, filename, or extra lookup indexes.
- Text/media handlers now replay same-key/same-payload messages and return 409 for same-key/different-payload. Message, receipt, and durable realtime events commit together.
- Media hash binds raw bytes, media kind, and reply target; excludes filename. Chat retention deletes receipts in the same transaction as messages.
- Added participant-checked, sender-scoped mobile receipt lookup with `Cache-Control: private, no-store`.
- Native text: encrypted draft remains the only stored copy of clinical text; a separate encrypted intent stores only key/scope/reply target. Draft is deleted before key after success/reconciliation so process death cannot restore an already-sent message as a fresh draft.
- Native media: SecureStore retains only key/scope/type/size/reply metadata; no URI, bytes, or filename. Restart reconciles receipt first; if absent, user reselects same file and retries with the same key.
- Web media: sessionStorage retains only key, type/size signature, and reply target; refresh/retry reuses the key and does not persist clinical content.
- Schema revision 14; security workflow path includes migration changes.

Regression tests added (committed, not executed): `tests/test_mobile_chat_actions.py`, `mobile/tests/consultations.cjs`; legacy synthetic key updated in `tests/test_legacy_pr215_repairs.py`.

Open acceptance: PostgreSQL migration/concurrency run, full Node/Python suite, TypeScript 5.9.2, Android build, real Android/iOS process-death and account-isolation tests, push/realtime replay checks, and 60k-user load/storage measurements. No main merge, production deploy, app-store release, or patient-record mutation.

## 2026-11-17 — Expert chat media recovery race

Web-first review of `app/templates/expert_case_room.html` and native `ChatAttachmentComposer.tsx` found that native camera/document/send controls were active before asynchronous SecureStore intent recovery completed. A process-death retry could therefore race a new request key against an already-committed attachment. Added a restore gate, receipt reconciliation before enabling a new send, and fail-closed handling for corrupt/unreadable local intent. No media bytes, URI, filename or clinical content were added to the stored intent.

Added two mobile regressions to the existing `consultations.cjs` beta suite. PostgreSQL migration revision-12 coverage now drops and verifies recreation of all four study tables before revision 14 is recorded. Added a two-worker PostgreSQL same-key consultation message replay test, including changed-payload 409 and one-message/one-receipt assertions. Security recovery path filters now include `tests/test_postgres_optimization.py`.

Commits: `0451e1b`, `0fe7915`, `e00257b`, `a35dd60`, `809b608`, `e5e1957`, `8752d35`. The new Node/PostgreSQL tests are committed but not yet executed; the latest Actions run still fails before any step with empty step arrays and `BlobNotFound 404`. No full typecheck, pytest, Android build or device acceptance is claimed. PR remains Draft; no merge/deploy or clinical record mutation.


## 2026-11-17 — Native account and notification reconciliation

Web-first comparison of `base.html`, `account.html`, `main.py` and the mobile notification API found that the native center lacked the web's cutoff-scoped read-all behavior. Added bearer-authenticated `POST /api/mobile/v1/notifications/read-all`: it only changes active unread notices owned by the caller and created no later than the captured cutoff; future timestamps are clamped, prior read timestamps are preserved, and one durable `NOTIFICATIONS_READ` event is emitted only when rows change. The mobile notice list uses a SQL count over all active unread rows rather than counting only its 20 visible cards. The read-all response and its durable realtime event carry the server-authoritative remaining unread count, avoiding an optimistic undercount when more than 20 notices arrive after the cutoff. The native screen now exposes an explicit read-all action, updates only its captured list snapshot, and reconciles remote read events. Home refreshes its unread badge when focused again. Native notification timestamps without an offset are interpreted as UTC, matching the web renderer's `created_at + "Z"` behavior; explicit offsets are preserved so device-local timezone does not change the cutoff decision.

Also found that first-run native onboarding asked for Android notification permission despite having no Expo token registration or push-response listener. Removed that premature permission request and made the current in-app-only state explicit. Backend push registration/transport exists, but `expo-notifications` is not yet installed or wired in native; do not claim OS push delivery. The support-ticket target was already implemented in the resolver, so the older tracker statement that it was unsupported is corrected.

Added `tests/test_mobile_notifications.py`, `mobile/tests/notifications.cjs`, beta-suite registration and security workflow coverage. These tests are committed but not yet executed. Latest inspected GitHub Actions runs at the starting head failed with zero steps and no runner assignment; no green typecheck, pytest, Gradle or full beta result is claimed. Main merge, live deploy, APK/IPA publication and patient-record mutation remain prohibited.

## 2026-11-17 — Patient profile mutation/delete safety follow-up

Re-read the PR base web flow first: `patient_detail.html` and `main.py` patient edit/delete handlers. Native profile comparison found that the two-stage delete action could remain available while a SecureStore treatment intent was still restoring, corrupt, or awaiting receipt reconciliation. An ambiguous profile edit could also be cleared by a manual acknowledgement before a successful server read.

Added a fail-closed native delete gate covering busy/uncertain profile mutation, incomplete or corrupt treatment-intent restore, and unresolved treatment receipt. The second destructive confirmation rechecks the live gate. Replaced manual profile-edit acknowledgement with an authenticated GET comparison of all seven editable fields; a matching server snapshot confirms the save, a mismatch preserves the draft and refreshes the edit revision for explicit resubmission, and a failed read keeps the operation uncertain.

Added five mobile renderer regressions and two backend/security regressions. Backend delete remains deliberately conservative: owner-scoped, 404 for another user's patient, and 409 when clinical dependencies exist. No cascade deletion or new erasure policy was introduced.

Commits: `65c8603`, `65915e9`, `548166a`, `7790335`, `b127168`, `0e2519e`; tracker update follows. The pure presentation helper was checked with Node 22 and TypeScript transpilation. React renderer tests require packages not installed in this runtime; Python API tests are committed but not run. At starting HEAD `364062f`, Android typecheck/APK and Security recovery jobs had zero steps; direct step queries returned empty arrays and logs returned BlobNotFound 404. No npm/tsc, Gradle or pytest ran. Exact GitHub hosted-runner/account cause remains unavailable. Real device and full suite acceptance remain open.

No patient records changed; no main merge, live deploy or store publication.

Follow-up hardening: separated `profileUncertain` from `treatmentUncertain` after a second-order race review showed that one shared flag could be cleared by the wrong mutation's receipt. Profile edits now wait for treatment-intent restore and are blocked while a treatment intent is pending; treatment writes are blocked while profile state is uncertain. The two-stage delete confirmation now also checks that the original account/patient scope is still mounted before sending the destructive request. Added renderer tests for these overlaps and stale alerts plus a Python security invariant. The pure presentation helpers passed Node/TypeScript checks; full React renderer, API pytest, Android typecheck and APK remain unexecuted because the current GitHub jobs still have no steps and the local runtime lacks the mobile dependency set.

Final destructive-dialog lifecycle check: the two-stage patient delete now also requires the profile to remain focused, not merely mounted. This closes the case where a native Alert remained actionable after navigation blurred the profile. Renderer coverage exercises both account/patient switch and blur before the final confirmation.

Patient identity hardening: profile initial load, revision-conflict reload and ambiguous-edit reconciliation now reject any response whose `patient.id` differs from the requested patient route. A mismatched response cannot render another patient's details or clear the uncertainty/delete gate. Renderer and Python source-invariant regressions were added.

## 2026-11-17 — Tooth chart clinical-write gate

Re-read the PR-base `tooth_chart.html` and `main.py` flow before native changes. Found that NativeToothChart blocked tooth selection/panel close for a pending treatment receipt but left status, surface, note and save controls active; the first render was also interactive before SecureStore intent restoration completed. Added a shared fail-closed gate for all tooth/surface writes, handler-level guards, disabled controls, restore/corrupt-state messaging, and patient-ID checks on chart refresh responses. The existing idempotent treatment receipt verification remains available; no new treatment row is inferred from a tooth observation. Added deferred-restore, pending-intent, wrong-patient and Python source-invariant regressions. Full renderer/typecheck/API/Gradle execution remains blocked by the same GitHub runner jobs with empty step arrays.
Tooth-chart final review: Notes tab, treatment edit controls, and all treatment form fields now respect the durable-intent gate; disabled fields remain controlled. Added patient identity equality checks on initial load and every refresh path. The changed JSX control fragments passed TypeScript transpilation; pure gate helper passed six Node assertions, new test snippets passed syntax checks, and the Python security test snippet passed AST parsing. Full renderer/Android/Python integration execution remains unavailable because Actions jobs have no steps.


## 2026-11-17 — Native voice session UI and private-audio cleanup receipt

Web-first review completed on the PR base before native edits: `voice_exam_entry.html`, `voice_exam_session.html`, `voice_exam_panel.html`, `voice_exam_device_check.html`, `voice-exam.css`, `voice-exam.js`, `voice-exam-live.js`, `voice-device-check.js`, `voice-pcm-worklet.js`, and the canonical `voice_exam.py` / `voice_exam_live.py` / voice core/source/final modules.

Found a privacy defect in native ASR success handling: the transcript removed its segment from SecureStore before cache-file deletion, and deletion errors were swallowed. A failed deletion could leave an untracked temporary clinical audio file. Native segments now retain a `transcribed` cleanup receipt until app-cache deletion is verified. Restart cleanup removes completed files without another Gemini request; failure blocks new recording and offers a cleanup retry. SecureStore writes are now confirmed before in-memory state is advanced.

Native recorder presentation now includes a web-parity microphone focal point, timer, metering progress, waveform, pause/finish controls and recent transcript preview. It still uses bounded local 15-second recording segments rather than the web's PCM16 WebSocket interim transcript; this difference is explicit and awaits native streaming capability work.

Also fixed two `voiceWorkflow.cjs` test calls that omitted the mandatory persisted ASR request key. Added regression assertions for idempotent transcript receipts, valid cleanup state, cache deletion recovery and the native UI contract. Security recovery now watches and runs the canonical web voice route/core/source/final modules plus `tests/test_voice_exam.py` and `tests/test_voice_exam_live.py`.

Evidence and exact remaining acceptance: `docs/mobile-voice-exam-parity-20261117.md`. Full project TypeScript, beta suite, Python integration, Expo export, Gradle and physical-device tests remain unverified because the previous current-head Actions jobs had no steps and typecheck logs returned `BlobNotFound 404`. No green CI is claimed.


## 2026-11-17 follow-up — Program create idempotency

- **Completed in branch:** native Program create request key, owner-scoped durable receipt on `ScheduleEvent`, unique database index, receipt reconciliation endpoint, SecureStore request-key recovery, and PostgreSQL race/migration regression coverage.
- **Privacy:** only a random request key is held in SecureStore; server rows contain keyed fingerprints rather than appointment text, notes or patient identifiers.
- **Release gate:** schema revision 15 requires `python -m app.migrate` before app startup. No merge or deploy was performed.
- **Still open:** full Android typecheck and integration suites (GitHub runner did not execute steps), stable snapshot pagination, native OS push/deep-link delivery, and 60k-user load certification.
- **Evidence:** `docs/mobile-program-idempotency-20261117.md`.


## 2026-11-17 — AI analysis privacy and receipt fingerprint hardening

- Web-first review covered `analysis_new.html`, `analysis_viewer.html`, the mobile analysis API and native analysis detail/upload flow.
- Found and fixed unnecessary direct patient identifiers in the mobile analysis workspace response. It now returns only internal scope ID, anonymous ID, age and chief complaint; native rejects extra fields and falls back to anonymous ID for a restored patient choice.
- Found and fixed an unkeyed SHA-256 fingerprint in `UPLOAD_RECEIPT.source_hash`. New receipts use HMAC-SHA256 with the dedicated `PATIENT_MEDIA_RECEIPT_KEY`, a separate analysis-upload domain and owner/patient scope. Legacy receipts upgrade lazily on authenticated lookup/replay.
- Missing receipt key fails closed with 503 before clinical allocation; changed same-key content remains 409. No schema migration or periodic scan.
- Added Python receipt/privacy tests and native analysis-response tests; registered the helper in Security recovery.
- Evidence: `docs/mobile-analysis-receipt-privacy-20261117.md`. Tests are committed but full repository execution remains blocked by current-head Actions jobs failing before runner allocation; no green CI is claimed.
- Deployment prerequisite: configure the stable 64-hex `PATIENT_MEDIA_RECEIPT_KEY` secret. No main merge, production deploy, store build or clinical record mutation.


## 2026-11-17 — Program snapshot pagination

Native Program continuation now uses an owner/view/day-bound, 15-minute snapshot cursor with a deterministic `(start_local, event_id)` key. Schedule writes after page one invalidate later pages with 409 rather than mixing old and new calendar rows. Legacy offset remains for older builds. The date-window occurrence helper still materializes the owner's schedule rows to produce weekly recurrence and day counts; query-plan and 60k load tests remain open. Evidence: `docs/mobile-program-idempotency-20261117.md`.


## 2026-11-17 — Program month-grid visual parity

Web `program.html` uses the first three daily event types as semantic color dots and an overflow dot. Native month cells now use the same first-three/overflow rule and the web tone colors; week view retains day counts. Backend and native regression coverage added. Evidence: `docs/mobile-program-idempotency-20261117.md`.


## 2026-11-17 — Dental Akış native media and link-preview parity

Web-first review covered `expert_following.html`, `_expert_social.html`, `expert-social.js`, `dental-flow.css`, and the expert-social API/safety/relationship modules. Native gaps found: one-photo picker, no ordered remove/reorder controls, no safe link-preview receipt, raw URL-only cards, duplicated link cover in the gallery, and owner actions that differed from the aggregate web feed.

Native now supports up to four sequential JPEG/PNG/WebP uploads (8 MiB each), persisting each successful media ID before continuing; secure-draft remove/reorder; HTTPS-only calls to the existing SSRF-safe `POST /preview`; bounded preview receipt persistence and validation; preview-aware post creation; metadata/cover link cards; cover exclusion from the gallery; and web-equivalent owner management routing and tab wording. No backend schema, migration, new background polling, patient data flow, merge or deployment.

Regression coverage added to `mobile/tests/social.cjs` and `mobile/tests/socialScreens.cjs`. These tests are committed but not claimed as executed. Full Android typecheck, beta tests, Expo export and backend social pytest remain blocked until GitHub Actions assigns runners. Evidence: `docs/mobile-dental-flow-parity-20261117.md`.


### Dental Akış follow-up hardening

Restored preview drafts now require HTTPS without URL credentials/nonstandard ports; cover URLs must exactly match their media IDs. Native preview opening repeats the HTTPS guard. A newly found retry defect was fixed: `attempted=true` drafts now allow the existing "Tekrar dene" action to submit the frozen payload with the same idempotency UUID, while media/link edits remain disabled. Regression tests cover preview URL/cover binding and ambiguous-send retry.

Latest observed head before this tracker update: `d5c415afa37b3f09eb937e1f6471e6f3fb3d78ef`. Android run `44030198756`, Security `44030198821`, Expert Social `44030198735`, Admin `44030198867`, Voice `44030198773`: six inspected jobs had empty step arrays and all six log downloads returned `BlobNotFound 404`. No compiler, Node beta, Gradle or pytest step executed. Evidence: `docs/mobile-dental-flow-parity-20261117.md`.


## 2026-11-17 — Expert support incremental realtime parity

Web-first review covered `expert_case_room.html`, `messages.html`, `_message_row.html`, the case-room `messages-live?after_id` flow, durable `MESSAGE_CREATED` / `CASE_READ` / `CASE_STATUS_UPDATED` payloads, and native `Consultations` / `ConsultationChat`.

New native gaps found: each `MESSAGE_CREATED` event reloaded the 50-row inbox; the open chat reloaded its latest 100-message page on each message/reconnect; successful text sends and recovered receipts also forced a full case GET. This did not match the web room's incremental cursor and caused avoidable database/network work.

Added a participant-scoped mobile `messages-live` endpoint with a bounded 100-message `after_id` cursor and a minimal case snapshot (no patient ID or clinical summary). Inbox rows now expose `last_message_id`; native applies preview/unread/status changes locally and ignores duplicate/out-of-order events. Native chat coalesces incremental catch-up, merges message IDs idempotently, applies status/read events in place, and appends send acknowledgements/receipts without a full reload. Case creation, detected event gaps, and case/report mutations retain an authoritative refresh path.

Regression coverage: `tests/test_mobile_consultation_live_api.py`, `mobile/tests/consultations.cjs`, and `mobile/tests/consultationRealtime.cjs`; the realtime test is registered in `mobile/package.json`. No migration or new polling was added. Evidence: `docs/mobile-expert-support-realtime-20261117.md`.

Validation remains limited: latest Android/Security jobs still have no runner assignment and no steps, so the committed tests, TypeScript typecheck, pytest, beta suite, and Android build have not run. No main merge or production deployment.


## 2026-11-17 — Expert room media acknowledgement, cache privacy and presentation

- Re-read the canonical web expert room and message templates before native changes.
- Native attachment success/recovery previously forced a full case GET even though the upload or receipt returned the persisted message. The composer now passes that message to the chat; the chat merges it by ID and advances its cursor. Deleted receipts without a message retain an authoritative reload path.
- Added a shared `private, no-store` response policy with `Pragma: no-cache` and `Vary: Authorization` to the mobile consultation inbox, full room snapshot, incremental messages and message-receipt endpoints. Inbox previews and chat snapshots contain private conversation content, so explicit response policy is required even when the client requests no-store.
- Native room status labels, media reply previews and annotation labels now match the web room's Turkish presentation.
- Added Python cache-header assertions, native attachment-ack source regression and pure status/preview reducer tests. Added `tests/test_mobile_consultation_live_api.py` to Security recovery path filters and pytest invocation.
- Evidence: `docs/mobile-expert-support-room-hardening-20261117.md`.
- Tests are committed but not executed. Starting head `e2e6cb6` had five failed-before-steps workflows; job step arrays were empty and log downloads returned `BlobNotFound 404`. No typecheck, beta, pytest, Gradle or Expo export pass is claimed.
- No schema migration, main merge, production deploy, APK/IPA publication or clinical record mutation.


## 2026-11-18 — Native voice interrupted-recording recovery

Web-first recheck covered `voice_exam_entry.html`, `voice_exam_panel.html`, `voice-exam-live.js` and `voice-pcm-worklet.js` before native changes. Found that a process interruption left `ready=false` M4A intents with no per-segment recovery action, and `cut()` discarded the active segment ID before recorder stop and SecureStore persistence completed. Also found that the ASR receipt used a literal escaped newline and that several renderer selectors still targeted previous Turkish button labels.

Native restore now checks only the direct app-private cache file and marks a segment ready only when it exists within the server's 100-byte–8-MiB contract. Missing files remove only their stale segment reference; earlier transcript text remains. Unverified/undersized/oversized files stay blocked and can be removed individually after explicit confirmation. Active segment identity survives stop/persistence failure; if the platform has already stopped, a separate finalization action retries the durable write without stopping twice. Background/unmount cleanup attempts to finalize the same intent. ASR transcript receipts now use actual newline characters.

Added renderer regressions for bounded interrupted-file recovery, missing-file transcript preservation, stop retry, and newline semantics. Corrected stale test selectors to the current native labels. Security Recovery now includes `voiceWorkflow.cjs` alongside `nativeVoiceAudio.cjs`.

Tests are committed, not yet executed. Starting HEAD `365ddb4740e88ca25728e562b1759245a6a5c8e4` had Android typecheck job `134532184679`, Security job `134532183748`, and native voice job `134532184250` with empty step arrays. Typecheck/Security logs returned `BlobNotFound 404`; no npm/tsc/pytest/Gradle step started. Exact hosted-runner/account/billing cause remains unavailable. Native live PCM16 WebSocket parity and physical-device acceptance remain open. No main merge, production deploy, APK/IPA publication, migration, or patient-record mutation.


## 2026-11-18 — Durable clinical-media object cleanup

Web-first review of the patient gallery and native media API found that database deletion could commit before R2 object deletion. A failed remote delete then left an unreferenced clinical object without a durable retry record; delete-all also loaded all rows and performed remote deletes synchronously. The existing WorkGarbage queue now accepts only strict server-generated web/native patient-media object keys, records cleanup in the same transaction as metadata deletion, protects any object still referenced by a live PatientMedia row, and retries storage failures after five minutes. Web delete-all processes 100-row chunks under the patient row lock to bound ORM memory. The native single-delete route uses the same queue. New focused tests cover allow-listing, dedupe, rollback, live-reference protection and retry. No schema migration or new service. Tests are committed, not run; Actions runner evidence remains a pre-step failure, not a source-test result. No main merge or production deployment.


## 2026-11-18 — Dental Akış yönetici MFA sınırı ve web kuyruk yarış düzeltmesi

Web-first review: `admin_social.html`, `expert-social-admin.js`, `expert_social_api.py` and `main.py` admin login/OTP. A real web UI race was found: changing kind/status or switching from moderation queue to reports while a request was in flight silently discarded the new load because one global loading flag blocked it. The old response could then remain visible under the newly selected filter. The web queue now snapshots mode/kind/status/cursor per request and uses a generation guard; reset loads supersede stale requests while pagination stays single-flight. Item pages are bounded to 30.

A security review confirmed native admin moderation must remain closed for now: `actor()` deliberately does not populate `social_admin` for Bearer requests, while `admin()` requires `_admin_only` cookie + `AdminVerifiedSession` created only after the fixed-mailbox OTP flow. A role-only native screen would bypass the current second factor. No native admin endpoint or fake admin button was added. A dedicated short-lived/revocable native step-up/MFA contract is the blocker before native admin queue parity.

Added `tests/expert_social_admin_queue.cjs` for stale filter/mode response suppression and expanded `tests/expert_social/test_native_auth.py` across queue, reports, detail and decision routes, including verified-cookie non-transfer to Bearer requests. Registered Node and Python regressions in manual-only Admin Security/Security Recovery workflows.

Commits in this batch: `af0fe88`, `7cc7312`, `ed29a6f`, `be21348`, `ff5a3ea`, `a629c0b`.

The new Node/pytest tests are committed but were not executed in this connector runtime. Full mobile typecheck, beta suite, Expo export, Gradle and physical-device tests remain unverified. Workflows remain `workflow_dispatch` only; no dispatch was sent. No main merge, live deploy, production migration or admin decision.


## 2026-11-18 — Patient approved-anamnesis foreground recovery

Web-first review of `patient_detail.html` confirmed that the profile renders only doctor-approved voice-exam fields and a fresh server snapshot on page open. Native `NativePatientVoiceHistory` refreshed on navigation focus and realtime events, but not when the app returned from background; the parent profile's general patient refresh did not refresh this separate anamnesis request. Added a focused background/inactive-to-active refresh policy, with no polling or new API, and kept the existing patient/account generation guard. Five renderer regressions cover resume, repeated active events, blurred screens, patient switching during a pending response and listener cleanup. The existing beta test registration already included this test; Security Recovery's native clinical job now includes it too.

Evidence: `docs/mobile-patient-voice-history-resume-20261118.md`. Standalone helper Node test 1/1 and strict helper TypeScript compile passed. The five committed React renderer tests and full app checks were not executed here. Current-head PR CI remains without an associated run; the last inspected old Android push run failed before steps with an empty job record and `BlobNotFound 404`. No main merge, production deploy, migration or patient-data mutation.


## 2026-11-18 — Native patient treatment-history pagination

Web-first review covered `app/main.py::patient_detail` and `patient_detail.html`: web fetches the full history but renders the first three rows and reveals the rest only after an explicit action. The mobile detail endpoint previously fetched every Treatment row even though the native screen initially showed only three. This was unnecessary transfer and ORM memory on larger patient histories.

Native patient detail now returns three treatments plus an owner/patient-bound opaque cursor. The new GET history endpoint returns 20 rows per request, uses stable `created_at DESC, id DESC` keyset pagination and a max-ID snapshot so inserts after page one do not shift later pages. Both endpoints explicitly disable shared/persistent caching and vary on Authorization. The cursor carries IDs/timestamps only; it is not an authorization token, and every page re-checks the authenticated patient's ownership.

Native UI loads older rows only after “Diğer tedavileri göster”, preserves existing rows and cursor on failures, rejects duplicate rows/cursor cycles, prevents double taps, and invalidates delayed responses on account/patient change or unmount. Existing edit revisions, pending treatment intents, create/update receipts and 409 conflict behavior remain intact.

Added composite `ix_treatment_patient_created_id(patient_id, created_at, id)` and schema revision 19. PostgreSQL uses a concurrent, advisory-lock migration with validity/column verification and retry handling for invalid interrupted indexes; SQLite uses transactional DDL for local tests. Migration code is committed but was not run against production or another connected database.

Regression coverage added to `tests/test_mobile_patient_parity.py`, `tests/test_postgres_optimization.py`, `mobile/tests/patientApi.cjs` and `mobile/tests/patientProfileUI.cjs`; Security Recovery now includes the two native patient test files. Tests are committed but not executed here. Starting HEAD `900e2117` had no associated PR workflow run; the last inspected Android typecheck/Security jobs had empty step arrays and `BlobNotFound 404`, so no compiler, pytest, PostgreSQL migration, Expo or Gradle step started. Automatic triggers remain disabled. No main merge, production migration, live deploy, APK/IPA publication or patient-record mutation.


## 2026-11-18 — Native clinical media response cache policy

Web-first review of `patient_detail.html` and the native gallery found inconsistent response privacy headers: the paginated native media list had no cache policy, while image-file, upload-receipt and upload-acknowledgement responses set only `Cache-Control` and omitted `Pragma` and `Vary: Authorization`. Reused the existing `_mobile_private_no_store` helper on all successful clinical-media list, file, receipt, upload and idempotent replay responses. Ownership checks, page limits, cursor behavior, sanitization, receipts and storage cleanup were left unchanged.

Added an owner-isolation and cache-header regression to `tests/test_mobile_patient_parity.py`; the existing Security Recovery pytest command already includes that file. Source/workflow registration was reviewed, but the Python test and full CI were not executed in this run. Current-head combined status and PR workflow-run list were empty. No CI pass is claimed. Evidence: `docs/mobile-patient-media-cache-hardening-20261118.md`. No patient data or media changed; no migration, main merge, production deploy or APK/IPA publication.


## 2026-11-18 — Patient-screen app-resume duplicate-read guard

Web-first review re-read `patient_detail.html`, `tooth_chart.html` and the corresponding ownership/revision routes in `main.py`. Found five native screens that loaded on navigation focus and also refreshed on every AppState `active` event without checking whether the app had actually resumed: patient profile, analysis history, tooth chart, clinical media gallery and calendar. Repeated `active` notifications could repeat the same private GETs. Added a shared background/inactive-to-active gate, reused it in the existing voice-history policy, and added a registered regression/source-contract test. Normal focus and realtime refresh paths remain unchanged; no polling or new endpoint was added. Evidence: `docs/mobile-app-resume-refresh-20261118.md`. Pure helper test 1/1 and standalone strict TypeScript compile passed locally; full mobile typecheck/beta/Expo/Gradle/device checks remain unrun. Actions remain manual-only; no workflow was dispatched. No main merge or production deploy.

## 2026-11-18 — Native voice recorder rotation guard and compact session parity

Web-first review: `voice_exam_entry.html`, `voice_exam_session.html`, `voice_exam_panel.html`, `voice-exam.css`, `voice-exam-live.js`, `voice-pcm-worklet.js`, `voice_exam_live.py`, and `mobile_api.py::mobile_voice_audio`.

New bug: during a normal 15-second native M4A chunk rotation, Expo Audio can publish `isRecording=false` after `recorder.stop()` but before the next `record()`. The previous status marker was not cleared until after file inspection and SecureStore persistence, so the recorder status effect could treat the expected transition as an unexpected microphone stop and clear `wanted`, preventing the next segment from starting.

Changes on this branch:
- Added `mobile/src/voiceRecorderLifecycle.ts` with a dependency-free transition classifier.
- Clear the previous recording marker before `recorder.stop()`; preserve genuine unexpected-stop handling outside the owned transition.
- Added regression coverage for rotation, real unexpected stop, clinician pause, stale status without an active segment, and the component integration contract.
- Web-first visual parity: hide the mic/timer before first use, show meter/wave only during recording, reduce mic focal point from 94px to 76px, and stack full-width actions vertically.
- Existing `npm run test:beta` already registers `tests/voiceWorkflow.cjs`; no new workflow or polling was added.

Commits: `5c9af0b`, `e260bb7`, `fa6c7cb`, `d21b560`, `42ff30d`, `c7b79b2`, `a8d0ad5`, `e68d911`.

Validation: strict TypeScript compilation of the pure helper passed; four isolated Node tests passed (4/4); GitHub source-contract checks passed (15/15). The full mobile TypeScript check, beta suite, Expo export, Gradle/APK, Python security suite, PostgreSQL concurrency, and physical Android/iOS rotation tests were not run. These helper tests do not replace the full React Native suite.

Native PCM16/WebSocket/interim-transcript parity remains open: the native recorder still uses bounded local M4A segments and the existing authenticated ASR receipt endpoint. No new provider or audio transport was introduced.

No transcript, audio, patient record, or production data changed. No workflow was dispatched; no main merge, migration, live deploy, or APK/IPA publication.



## Consent withdrawal regression — 2026-11-19

Re-inspected the web voice flow before changing native behavior. Found that both web and native consent controls were disabled while the microphone was active; the live browser controller had no consent-change handler, and the native recorder could continue into ASR if opt-out raced its finish gate.

Fixed the web live and MediaRecorder paths, made consent withdrawable during active capture, and added native abort/pause plus a ref-backed guard against stale drain/finish callbacks. Existing app-private recording recovery and exact ASR receipt keys are preserved. The web file-recorder blob is held only in page memory after opt-out and requires explicit re-consent/retry.

Regression coverage added in `mobile/tests/voiceWorkflow.cjs`, `tests/voice_live_browser.cjs`, and `tests/voice_exam_browser_state.cjs`. Documentation: `docs/mobile-voice-consent-withdrawal-20261119.md`.

Commits: `6f9add4`, `24c9e23`, `1c21765`, `6ea169a`, `b2dfcf1`, `8cd747d`, `bd1bc9e`, `272979d`, `d559e27`, `fad4c8f`, `1b4c4e8`, `6c5c2e6`, `9a7edae`, `917aef9`, `e528967`, `051b7f9`.

Tests are committed but not executed. The current-head workflow has no run/check; earlier hosted jobs had runner ID 0, empty steps and missing log blobs. Physical Android/iOS and real-browser acceptance remain open. No main merge or production deploy.


## Program cache privacy and day grouping — 2026-11-19

Web-first review of `program.html`, `mobile_program_api.py`, the shared `_mobile_private_no_store` helper and native `NativeProgram` found two gaps: account-scoped Program responses lacked explicit private/no-store headers, and the native weekly occurrence list did not identify the date for each day's events. All nine Program response paths now use `Cache-Control: private, no-store`, `Pragma: no-cache` and `Vary: Authorization`. Native event lists now add one accessible date heading per date boundary, including correct continuation across appended cursor pages. The count-only conflict-advice path also skips patient-row hydration; it keeps the same owner-scoped schedule query and overlap count but avoids a patient SELECT and in-memory patient map. Python route-header/query regressions and the native renderer regression are committed and already registered in Security Recovery / `npm run test:beta`; none of those suites was executed in this connector-only run. Details: `docs/mobile-program-cache-and-day-groups-20261119.md`. No migration, main merge or deploy.


## 2026-11-19 — Dental Akış comment pagination refresh lease

Web-first review re-read `expert_following.html`, `_expert_social.html`, `expert-social.js` and the comments cursor route before native changes. Found a native-only deadlock: when an older comment page was in flight and the member pulled to refresh, the first-page request advanced the generation. The stale page's `finally` then correctly avoided changing current UI state, but also skipped clearing the old boolean pagination lock. Every subsequent “Diğer yorumlar” action returned early.

Replaced the boolean with a request-ID lease in `mobile/src/SocialScreens.tsx`. A first-page refresh invalidates the prior page lease; only the request that still owns the lease may release it. Stale responses remain generation-fenced and cannot clear a newer page request's lease. No backend, API, schema, auth, storage, polling or patient-data changes.

Added an interactive renderer regression to `mobile/tests/socialScreens.cjs` covering initial page → in-flight older page → refresh → new older page → late stale response → next cursor. The test file is already registered in `npm run test:beta` and Security Recovery's `native-social-security` job.

Evidence: `docs/mobile-dental-flow-comment-pagination-20261119.md`. Commits: `7e726d9`, `63b38d3`, `21aa505`, `deca4e3`, `337e374`, `c25944e`, `3a8d935`, `55689a4`, `a3470b9`, `0274dd9`. The test is committed but not executed in this run. PR head before changes `c84238c` had empty combined status and no associated PR workflow runs. The historical Android/Security runner failures still have runner ID 0, empty steps and missing log blobs; no source-level typecheck or pytest failure is established. Full typecheck/beta/Expo/Gradle/Python/PostgreSQL/device/60k-load acceptance remain open. No main merge or live deploy.


## 2026-11-19 — Native new-patient phone-field parity

Re-read `app/templates/patient_new.html`, `app/main.py::create_patient`, `app/mobile_api.py::mobile_create_patient` and `mobile/src/NativeNewPatient.tsx` before changing the form. The web create form requires a Turkish mobile number (`05[0-9]{9}`), but native allowed an empty phone and sent it to the API. Added a pure native validator, digits-only 11-character normalization, required-field label, telephone autofill metadata and pre-submit validation. API optionality remains for backward compatibility with older clients. Added pure helper and native renderer regressions and registered both in `npm run test:beta`.

Commits: `1e5004c`, `6a93643`, `de95b2b`, `d92503b`, `774b7ad`, `17b4f9b`, `2c59187`. Documentation: `docs/mobile-patient-create-form-parity-20261119.md`.

The test sources are committed but the full Node/React Native suite and Android typecheck have not been executed in this runtime. No backend schema/API behavior, patient data, main merge or live deployment changed.


## 2026-11-19 — Patient directory search and privacy parity

Web-first review compared `patients_all.html`, `patient_search.html`, `main.py::search_patients`, `mobile_api.py::mobile_patients` and native `Patients`/ `PatientRow`. Found that native search omitted TCKN although the web search accepts it; native rows displayed either phone or patient number instead of both; search order differed from web; and the patient-list response lacked the shared private/no-store headers.

Changes: added owner-scoped TCKN matching without returning TCKN in list payloads; applied `private, no-store`, `Pragma: no-cache` and `Vary: Authorization`; reused one filter set for page/count and changed count to `count(Patient.id)`; matched web surname/name ordering with an ID tie-breaker; normalized Turkish search whitespace; displayed both patient number and phone; added 100-character input bound, explicit no-match/clear state and guarded automatic pagination while retaining the manual fallback. Age zero now displays correctly in the tooth-chart patient selector.

Regression sources: `tests/test_mobile_patient_parity.py` covers web/native TCKN parity, partial matching, owner isolation, no-store headers, list-payload minimization and ordering. `mobile/tests/patientDirectoryPresentation.cjs` covers Turkish normalization, row labels, age zero, bearer-only query encoding and native list wiring; registered in `npm run test:beta`. Python and Node suites were not executed in this connector-only run. Full typecheck, beta, Security Recovery, Expo/Gradle, device and 60k-load acceptance remain open.

At starting HEAD `a156fc7`, no current-head workflow run or combined status existed. Workflows remain manual-only; a historical Android job had no steps and its log returned `BlobNotFound 404`, so the compiler/test process did not start. No dispatch was sent. The native list/detail path remains owner-only; ADMIN-wide web directory access was not copied into a list-only mobile change. Evidence: `docs/mobile-patient-directory-search-parity-20261119.md`. No patient data, schema, migration, main merge or production deploy.


## 2026-11-19 — Native patient profile three-way edit conflict handling

Web-first review re-read `patient_detail.html`, `main.py::edit_patient`, `mobile_api.py::mobile_patient_detail`, native profile and API mutation code. Found two native-only hazards: after HTTP 409, explicit reload discarded all local form edits; and a realtime/app-resume refresh could advance the detail revision while a dirty edit form remained unchanged, allowing a stale draft to overwrite concurrent edits without another 409.

Added a typed three-way merge helper. Unchanged local fields adopt the latest server values, local-only edits stay in the draft, and fields changed differently by both sessions require an explicit clinician choice. Saving is blocked until every same-field conflict is resolved. Dirty drafts keep their old revision across realtime refresh; the user must explicitly merge/review the latest snapshot before the refreshed revision can be used. Owner scope, no-store, optimistic revision contract, clinical history provenance and secure pending mutation behavior remain unchanged. No new endpoint, schema, query, polling, migration or patient-data mutation.

Regression sources in `mobile/tests/patientProfileUI.cjs` cover unrelated concurrent edits, same-field conflict choices, save blocking, refreshed-revision retry, and realtime refresh during an open dirty form. The file is already registered in `npm run test:beta`. These renderer tests are committed but not executed in this run.

Commits: `d482081` (merge helper), `b2268b0` (native conflict handling), `a43dc2d` (preserve draft across refresh), `cc350f6` and `135c8dc` (conflict/realtime regressions), `680b0ae` (documentation). Evidence: `docs/mobile-patient-edit-conflict-merge-20261119.md`.

At starting HEAD `817a879`, combined status and PR-associated workflow runs were empty. The PR body records 2026-11-16 Android typecheck/APK and Python security jobs with runner ID 0, no steps and missing log blobs; npm/tsc, Gradle and pytest did not start. Exact hosted-runner/account/billing sub-cause remains unknown. Full typecheck, beta, Python security, Expo/Gradle, physical-device and 60k-load acceptance remain open. No main merge or live deploy.


Follow-up review found that the network-uncertain profile-write reconciliation path had the same stale-revision overwrite risk after a successful read. It now applies the same three-way merge before clearing the uncertain-write lock; same-field conflicts remain blocked pending explicit clinician choice. Added `uncertain patient edit reconciliation merges remote-only fields before retry` to `mobile/tests/patientProfileUI.cjs`. Commits: `54eb7d2` and `4026540`; documentation follow-up: `c5fe57a`. The full renderer suite remains unexecuted because the connector runtime has no repository checkout and the current-head GitHub Actions workflow has not started.


A final privacy pass scoped the native in-memory patient edit snapshot to the composite account/token/patient identity. A component reused during an account switch now invalidates the old snapshot before the new profile request can resolve; an account-switch renderer regression with a delayed response is included in `mobile/tests/patientProfileUI.cjs`. Commits: `2b5fdde` and `47822d4`; documentation: `d643c2a`. No cross-account profile data is intentionally retained; full renderer/device execution remains pending.

The snapshot scope declaration was moved after the composite `scope` value is initialized, so account-scope invalidation is evaluated against the current identity without a temporal-dead-zone reference. Follow-up commit: `a60145b`.


## 2026-11-19 — Native microphone preflight cleanup verification

Web-first review compared voice_exam_device_check.html and voice-device-check.js (in-memory PCM16 AudioWorklet, no audio file) with NativeVoiceDeviceCheck. Found that native cache-file deletion errors were swallowed, file absence was not verified, and the URI was cleared regardless; the UI could present a normal microphone result without confirmed cleanup.

Added an exact app-private cache URI validator (direct M4A child only; rejects prefix siblings, traversal, nested and non-file paths). Native deletion now checks existence before and after delete through a dependency-injected helper, retains the URI until absence is confirmed, reports cleanup_failed instead of passed, and exposes a retry action while blocking a new check. The CJS test registers TypeScript transpilation explicitly, matching existing Node 20 test harnesses. Both microphone cleanup regression files are also included in the manual Security Recovery native-voice-security job, as well as npm run test:beta. Start failure, stop, background, blur and unmount use the same verified cleanup helper. No upload, SecureStore persistence, patient/account identifiers or API calls were added.

Regression sources updated: mobile/tests/voiceDeviceCheck.cjs and mobile/tests/voiceDeviceCheckUI.cjs. Both are already registered in npm run test:beta. The 13-test pure helper suite passed in an isolated Node 22.16 run using the fetched branch helper/test contents and an explicit TypeScript transpile registration; strict standalone helper TypeScript compilation passed. Twenty-one GitHub source-contract assertions passed and the UI CJS file passed node --check, but its actual renderer/source-contract execution and the full package remain unrun. Full app typecheck, beta suite, Expo export, Gradle, physical Android/iOS and simulated device filesystem deletion-failure acceptance remain open.

Commits: 6a336d0, d895fc7, 1468a1e, dc4b23a, 0d954eb, a76deac, 495aa0b, plus the documentation commits. Evidence: docs/mobile-voice-device-check-cleanup-20261119.md. No patient data, migration, main merge or live deploy.

## 2026-11-19 — Native voice draft account/patient scope isolation

Web-first review re-read `voice_exam_entry.html`, `voice-exam-live.js` and `voice-pcm-worklet.js`, then compared `NativeVoiceRecorder` and its SecureStore-backed M4A/ASR lifecycle. Found a stale async restore race: the old effect's `mounted.current=false` could be followed by the new effect setting the same ref back to true before an old SecureStore/cache read resolved. The stale read could then publish the previous patient's transcript through the new component callback or overwrite shared draft state.

Added `mobile/src/voiceDraftScope.ts` and an effect-local lease bound to the existing owner+patient draft key. New-scope restore waits for old-scope ASR/recorder cleanup; stale restore, persist, ASR drain and transcribed-file cleanup operations are fenced after awaits. Old recorder cleanup writes only to its captured old key and cannot replace the new in-memory draft. No token/transcript/audio is added to persistent storage.

Added `mobile/tests/voiceDraftScope.cjs` and a delayed SecureStore-read owner/patient-switch renderer regression in `mobile/tests/voiceWorkflow.cjs`; registered the helper test in `npm run test:beta` and Security Recovery's native voice job. Evidence: `docs/mobile-voice-draft-scope-isolation-20261119.md`.

Validation: isolated helper Node test 5 assertions passed; standalone strict TypeScript helper check passed; voiceWorkflow CJS syntax parse and package JSON/registration checks passed; 16/16 GitHub source-contract checks passed. The new React Native renderer regression, full mobile typecheck/beta suite, Security Recovery, Expo export, Gradle and physical-device tests were not executed. Current native capture remains bounded M4A + ASR receipt; raw PCM16/WebSocket parity remains open because the current Expo Audio recorder API used here does not expose the browser AudioWorklet raw-frame callback. No main merge, migration, live deploy or patient-record mutation.


## 2026-11-19 — Native appointment patient selector search and identity parity

Web-first review compared `program_form.html`, the shared schedule validation/owned-patient resolution, `mobile_program_api.py`, `mobile_api.py::mobile_patients`, `NativeProgramEditor` and `NativePatientSelect`. The web form keeps patient linkage optional and preserves the selected patient when editing. The mobile picker already used bounded 30-row owner-scoped pages, but its search field did not expose the backend's full supported fields or cap input at the API's 100-character limit; its result rows showed only the anonymous number, so same-name patients were harder to distinguish.

Added `patientSelectPresentation.ts` for normalized Turkish whitespace, a strict 100-character query bound, consistent loading/empty/error copy and safe patient-number/phone row details. Updated `NativePatientSelect` with a bounded search field, submit + 300ms debounce, name/surname/patient-number/phone/TCKN search hint, patient-number + phone result labels, accessible row names, keyboard-safe taps, automatic 30-row paging plus manual fallback, clear-search, retry and explicit empty/loading/error states. TCKN remains search-only; it is not returned in row text or accessibility labels. No backend, auth, patient record, schema, migration or appointment mutation behavior changed.

Regression: `mobile/tests/patientSelectParity.cjs` checks Turkish whitespace, the 100-character boundary, row privacy, empty/loading/error copy and component search/pagination wiring; registered in `npm run test:beta`. Local isolated Node 22.16 run passed 4/4 tests. Standalone strict TypeScript compilation of the two pure presentation helpers passed; the TSX file transpiled without syntax diagnostics; CJS syntax and package JSON were checked. The complete React Native project typecheck, full beta suite, Android/iOS export, Gradle and physical-device acceptance remain open.

Commits: `020444e` (presentation helper), `64e5531` (native picker), `0e59994` (regressions), `281f26b` (beta registration), `b875238` (feature evidence), `2684ab2` (correct the source-wiring assertion), `ffe4b3f` (retry-only pagination state), `ecebb85` (pagination regression), `8dafaba` (follow-up evidence). No main merge or live deploy.


## 2026-11-19 — Tooth-surface applicability follow-up

Re-read `app/templates/tooth_chart.html`, its `selectTooth` / `setSurface` flow, the owner-scoped tooth/surface routes in `app/main.py`, and the FDI observation helper before changing native code.

Found a native-only inconsistency: the tooth preview pin already mapped FDI units 1–3 to `INCISAL`, but the two native surface-choice lists exposed both `INCISAL` and `OCCLUSAL` for every tooth. Added `mobile/src/toothSurfaceOptions.ts` so permanent and primary FDI teeth expose only the applicable incisal or occlusal option, plus the four shared axial surfaces. Invalid FDI values expose no writable choices. The main surface picker, independent surface editor and preview-pin labels now share the same selected-tooth options and web terminology.

Added `mobile/tests/toothSurfaceOptions.cjs` to `npm run test:beta`. Isolated Node 22.16 helper tests passed 4/4 and standalone strict TypeScript compilation passed. GitHub source-contract checks verified both picker bindings, both label lookups, FDI guard and beta registration. The committed component-wiring test is not claimed as locally executed; full React Native typecheck, complete beta suite, Python security tests, Expo exports, Gradle APK and device acceptance remain open.

Commits: `bf7ede7` (FDI helper), `ca66763` (native integration), `dcbd349` (regressions), `20cd470` (beta registration), `a9a2533` (technical note), tracker evidence update. No schema change, main merge, production deploy or clinical record mutation.


## 2026-11-19 — AI analysis receipt-first crash recovery

Re-read the web analysis composer/viewer and backend upload receipt route before changing native code. Found a process-death window: after a successful upload receipt, native cleanup deletes encrypted local image files before deleting the SecureStore intent. On restart the old restore path validated/migrated local files before querying the server receipt, so a missing encrypted file could block recovery of an analysis already persisted on the server.

Changed `NativeAnalysisUpload` to reconcile the authenticated owner/patient-scoped server receipt immediately after parsing the durable intent, before local image validation or migration. A found receipt triggers idempotent local cleanup, intent deletion, and opening the existing analysis; a transient receipt lookup failure leaves the intent and files untouched; a missing receipt proceeds through the existing encrypted-draft and same-request-key retry path. No API, database, HMAC receipt, provider, or clinical behavior changed.

Added regressions to `mobile/tests/analysisUpload.cjs` for already-deleted encrypted local files with a valid server receipt and for transient receipt lookup failure without local cleanup. The tests are part of the existing beta suite but were not executed in this connector-only session. Full typecheck, renderer suite, Expo exports, Gradle, Python security tests and physical-device acceptance remain open.

Commits in this follow-up: `074bd54` (crash-window regression), `454570f` (receipt-first recovery), `1ab9bbb` (offline receipt lookup regression), `900947d` (technical evidence), plus this tracker update. No main merge, production deploy, migration, or patient record mutation.


## 2026-11-19 — Program cursor integrity hardening

Re-read the web Program page/form and the native range, create/edit, recurrence, reminder and copy adapters. Found that the 50-row cursor was base64 JSON with only a deterministic account tag; although all SQL remained owner-scoped, the client could rewrite its own watermark and last-item tuple to skip or repeat pages.

Advanced the cursor to v2 with HMAC-SHA256 over canonical JSON, keyed by a domain-separated derivation of the authenticated bearer session token. The /program range route now obtains the same token used by _mobile_user, verifies the MAC before parsing the payload, and retains the 15-minute expiry, 409 mutation invalidation, owner/view/day checks and private no-store headers. Session rotation intentionally invalidates old cursors; the native screen can recover through its first-page refresh.

Added backend tests for key derivation, token binding, tampering, expiry/future timestamps and authenticated endpoint cache/tamper behavior. The tests are committed but not executed in this connector-only run. Full pytest, Android typecheck, component suite, APK/device and 60k-user load acceptance remain open. No schema or dependency change, main merge, deploy or patient record mutation.


## 2026-11-19 — Android typecheck root-cause recheck

Rechecked the previously reported TypeScript TS2554 at ModernScreens.tsx:112. The failing call belonged to the duplicate legacy MediaGallery and invoked uploadPatientMedia with only the token, patient ID, file, undefined tooth and media type, while the current durable upload contract requires requestKey and batchId as well. The duplicate component and its direct upload path are absent from the current ModernScreens.tsx. App.tsx routes MediaGallery to NativePatientMedia; mobile/tests/patientMediaRoute.cjs asserts that the duplicate component/upload call stay removed and is included in test:beta. This confirms that specific TS2554 source is no longer present; it does not prove the full project typecheck passes.

Inspected .github/workflows/android-test-apk.yml, mobile-android.yml and security-recovery.yml. All use the valid GitHub-hosted ubuntu-latest runner label; none depends on a self-hosted runner. The latest inspected Android APK job (run 44273348890) has an empty step list, and log retrieval returns BlobNotFound 404. The current HEAD has no check-runs or commit status entries. Evidence therefore points to runner allocation/startup before checkout, not a TypeScript or Gradle diagnostic. The available GitHub result does not expose the precise platform-side quota/billing/provisioning cause. No workflow was dispatched to avoid repeating CI email notifications.

Full tsc --noEmit, npm test, Python security suite, Gradle APK and device acceptance remain unverified for the current HEAD.

## Academic AI answer actions — 2026-11-19

Web-first review found that native reactions triggered five unrelated workspace reads and that native answer cards lacked a share action. Native now has accessible share/like/dislike controls, strict feedback acknowledgement validation, optimistic rollback and a local message-only vote update. Nine helper/component/API regressions are registered in `npm run test:beta`; they were committed but not executed in this connector-only run. Native uses the system share sheet; one-tap clipboard parity remains open. Details: `docs/mobile-academic-answer-actions-20261119.md`. No dependency, migration, main merge, deployment or CI dispatch.

## 2026-11-19 — Academic upload content binding

Web-first review of `app/main.py::upload_study_materials` and `app/mobile_academic_api.py::upload_materials` confirmed that the server already streams SHA-256, binds it to owner/course/filename/MIME/size and stores the durable receipt atomically with the material. The native recovery path still compared only name/MIME/size and could delete a different same-size local file after a receipt lookup.

Native now hashes the private cache with Expo FileHandle in bounded 1 MiB reads, stores the digest in a v3 SecureStore intent before upload, verifies the server acknowledgement and compares local bytes to the durable receipt before cleanup. Legacy v2 intents remain readable and are upgraded before retry. Missing local data is cleared only after a matching receipt; mismatches preserve the file and intent. Leaving the screen during hashing cannot start a later upload.

New tests: six file-hash boundary tests, a mismatched upload-acknowledgement test, a same-name/same-size recovery mismatch test and a screen-exit-during-hash test. Registered in `test:beta` and the manual Academic Security Recovery job. Tests, full typecheck, Expo export, APK and device performance are not run because workflows remain manual-only and hosted runner allocation is unresolved. Details: `docs/mobile-academic-upload-content-binding-20261119.md`. No dependency, schema migration, main merge or deployment.


## 2026-11-19 — Analysis image download pool isolation

Web-first review compared `analysis_viewer.html` / `main.py::analysis_asset` with native `mobile_analysis_api.py` and the already-hardened patient-media download route. Native analysis asset and legacy-radiograph downloads previously hydrated R2 while a SQLAlchemy Session remained open. Both now copy the authorized storage reference, close the session, and offload `storage_ensure_local` through the Starlette threadpool. The shared private/no-store policy now also adds `Pragma: no-cache` and `Vary: Authorization`.

Three integration regressions cover analysis asset hydration, legacy-radiograph hydration and owner rejection before storage access. A security source-contract test protects the offload/cache behavior. Tests are committed but were not executed here; full pytest, Android typecheck, beta suite, Expo/Gradle and device acceptance remain open. Evidence: `docs/mobile-analysis-download-pool-safety-20261119.md`. No schema, dependency, main merge or production deployment.

## 2026-11-20 — Native AI analysis composer web parity and Android symbol fix

Web-first inspection re-read `analysis_new.html`, its `analysis-step-title` / `analysis-field-help` / `analysis-safety-note` CSS, the authenticated web GET/POST handlers, the mobile analysis API, and the native upload/gallery components before changing UI.

New visual gap: native already supported camera/gallery, encrypted upload drafts, receipt-first recovery, same-key retry, saved + new media and byte progress, but flattened the web's three numbered sections into one panel. It omitted the saved-media-specific “Ek görünt” title, the clinical-only helper and the clinical safety note; its 15/48 MiB display copy was hard-coded.

Changes:
- Added `analysisComposerPresentation.ts` to model the web's three steps and derive saved/new image copy from the canonical `uploadLimits.ts` values.
- Reworked `NativeAnalysisUpload` into numbered native sections, preserving camera/gallery, previews/removal, encrypted intent, receipt recovery, transfer progress and cancellation.
- Added the web clinical-only helper, safety note and full-width navy submit action.
- Found and fixed a real missing-symbol source defect: `analysisApi.ts` used `ANALYSIS_MAX_IMAGES` without importing it, while `NativeAnalysisUpload` and `NativePatientMedia` imported it from `analysisApi` even though it was not exported. The API now imports and re-exports the canonical shared constant.
- Added `analysisImageLimitContract.cjs` and `analysisComposerPresentation.cjs` to `npm run test:beta`; the composer suite also transpiles the actual TSX source and fails on syntax diagnostics. A non-native `fontWeight: '850'` value introduced during styling was corrected to React Native's supported `800` before the final component update.

Privacy review confirmed that web/mobile owner checks and saved-media ownership checks remain unchanged, the patient summary remains anonymous ID/age/complaint only, and native upload components remain keyed by account/patient scope. No schema, endpoint, provider, migration or patient record changed.

Isolated verification: 3/3 image-limit contract fixture tests, 6/6 composer presentation/TSX-syntax fixture tests, and a strict TypeScript shared-limit/import-export fixture passed. The TSX parser check used a minimal component fixture; the committed guard still needs to run against the actual repository component in CI. These fixtures are not the full repository checkout. Full `npm test`, Expo typecheck/export, Android Gradle/device tests and Python security pytest remain unexecuted because this runtime could not clone GitHub and the current workflows are manual-only. The current HEAD has no check runs or commit statuses; previously retrieved 18 November jobs failed before their first step with empty steps and unavailable log blobs, so they did not run the compiler or tests. No green CI is claimed.

No main merge, live deploy, migration, APK/IPA publication or clinical record mutation.


## 2026-11-20 — Native clinical result parity with the web result page

Web-first inspection completed before native edits:
- `app/templates/result.html` initial result order: likely condition, important findings, treatment options, treatment cautions, preferred approach, differential, then clinician questions and the web's question guidance.
- The FINAL branch uses the same six clinical sections in the same order inside the pale `#f5f8ff` final box; it does not show preliminary-only uncertainty, evaluation, or preliminary-assessment sections.
- `app/templates/analysis_viewer.html` and the authenticated web handlers were checked alongside `NativeVisionViewer` and `clinicalApi.ts`. The native manual-finding request is already routed through the owner-scoped web finding handler; no duplicate endpoint or persistence path was added.

New native parity gaps found and corrected:
- INITIAL / ANALYSIS_COMPLETE was labelled “Ön Klinik Değerlendirme” instead of the web’s “Klinik Değerlendirme”.
- Findings were rendered after all other sections instead of second, and treatment options had no ordered-list markers.
- Native rendered uncertainty, preliminary assessment and recommended-evaluation fields that the web result page does not render.
- The native clinician-question form omitted the web's explanation and “Kısa klinik cevap yazın...” placeholder.
- FINAL did not use the web's pale final-result container.

Implementation:
- Added `mobile/src/clinicalResultPresentation.ts` as a small, pure web-order/title contract.
- Updated `NativeClinicalReview.tsx` to render the six sections in web order, use bullet/ordered markers, apply the final-result background, and restore question guidance and placeholder copy.
- Added three presentation-contract tests and two component-level regressions in `clinicalResultPresentation.cjs` and `clinicalWorkflow.cjs`; registered the new suite in `npm run test:beta`.

CI/typecheck/security boundary:
- The previous Android typecheck import/export defect in `analysisApi.ts` remains corrected: the canonical image limit is imported from and re-exported from `uploadLimits.ts`.
- At the inspected starting head `c577998`, no workflow run or commit status existed for the current head. Android and Security Recovery workflows remain `workflow_dispatch`-only, consistent with the user's request to stop repeated CI notifications.
- Rechecked the last available Android typecheck and Security Recovery jobs (run 43772807470 / 43772807464): both reported completed/failure but returned zero steps; all three job-log downloads returned `BlobNotFound` 404. The compiler, Gradle and pytest did not start. This is an Actions log/runner availability failure, not evidence of a source-level test failure; the exact hosted-runner/account cause remains unverified.
- The new committed Node regressions, full Expo `tsc --noEmit`, Android Gradle build, and Python security suite have not been executed in this runtime. No green CI is claimed.

Commits in this run: `8158d10`, `d37a5ed`, `5627818`, `07d231c`, `de6d6d7`, and this tracker update. No auth, owner-scope, patient-data, database, provider, workflow-trigger or production code was changed. No main merge, deploy, migration, APK/IPA publication or clinical record mutation.


### Verification addendum — 2026-11-20

- The first isolated run exposed a CommonJS test-harness mistake: a top-level `const exports` redeclared Node's wrapper binding. The new unit test now uses `moduleExports`; this was fixed in commit `fe6efde`.
- Ran the committed presentation helper and corresponding test logic in an isolated Node 22 fixture: **3/3 passed**.
- Ran strict TypeScript compilation of the standalone presentation helper: passed.
- Ran a TypeScript TSX syntax fixture for the new ordered-result JSX: **0 syntax diagnostics**.
- These checks do not replace the full mobile test suite or full `NativeClinicalReview.tsx` typecheck. Component integration tests are committed but remain unexecuted because this runtime has no repository checkout or React Native test dependencies, and GitHub Actions remains manual-only.

Latest code/test head for this work: `fe6efde6d214d05d54fa3e1c67e14ac9d23af021`. No CI pass is claimed.


## 2026-11-20 — Web clinical media gallery paging and thumbnails

- Web-first comparison: `patient_detail.html` previously rendered every `PatientMedia` row and loaded the original full-resolution file for each small gallery card. Native already used 40-item descending-ID pagination and the private thumbnail derivative.
- The web profile now loads 40 media rows plus one look-ahead row and separately displays the total count. The authenticated cookie-session page endpoint returns only display metadata, uses an owner-scoped descending-ID cursor, and sets private/no-store + Cookie variance headers.
- Added a web-session thumbnail endpoint backed by the existing deterministic derivative helper. It releases the first DB session before storage hydration, then rechecks patient/media ownership and the unchanged file reference before serving. Orphan derivatives are removed when the record disappears during generation.
- Gallery cards use private JPEG thumbnails; the modal still opens the original. “Daha fazla görsel yükle” fetches 40-row pages without losing selected IDs. The four-image AI limit is enforced across pages. Dynamic cards use DOM APIs/textContent and exact same-origin path validation.
- Added `app/clinical_media_gallery.py`, `tests/test_clinical_media_gallery_pagination.py`, web route assertions in `tests/test_clinical_media_thumbnail.py`, and `mobile/tests/patientMediaWebGallery.cjs` (registered in `npm run test:beta`).
- Validation in this run: 17/17 GitHub read-back source-contract assertions passed. The committed Python/Node suites were not executed because this environment has no repository checkout/dependency runner. Full pytest, mobile typecheck, Android build/device, browser interaction, PostgreSQL query-plan, and multi-instance R2 concurrency checks remain open.
- Follow-up test-harness review moved the bounded-query assertion from the template fixture to `app/main.py` (commit `8913e7b`). Read-back confirms the test now checks the backend query. Query PR metadata for the live HEAD; this tracker is not a branch-head source. PR remains Draft/open. No merge, deploy, migration, APK/IPA publication or patient-data mutation.


## 2026-11-20 — Mounted patient analysis history parity

Web reference checked first: `app/templates/patient_detail.html` and `app/main.py::patient_detail`. The web profile marks an analysis as a voice review only when the patient's owner has a `VOICE_REVIEW` WorkJob in `DONE` state; it also allows an administrator to open an explicitly selected patient.

A route-order inspection found two GET handlers registered for `/api/mobile/v1/analyses`. `app.main` mounts `mobile_analysis_api.router` first and filters duplicate method/path pairs from `mobile_modern_api_v3.router`; therefore the latter handler was shadowed and its pagination/count changes were not active. The duplicate was removed to prevent future fixes from targeting dead code.

The mounted `mobile_analysis_api.mobile_analysis_history` now:
- returns the total matching patient/tooth count across cursor pages, not only the current page size;
- applies a repeated owner predicate to non-admin patient-scoped reads after the 404 ownership check;
- permits admin access only when an explicit patient ID is supplied, matching the web patient-detail permission boundary;
- derives `is_voice_review` from the completed WorkJob under the selected patient's owner, including admin-selected patients;
- marks the clinical-history response `private, no-store` with `Vary: Authorization`.

Native response validation now rejects a non-boolean optional `is_voice_review` value but continues to accept older servers that omit the field. Regressions cover cursor totals, only-DONE voice markers, owner isolation, explicit admin selection, cache headers, mounted route identity, malformed client values and legacy omission.

The Python integration tests are committed but were not run in this runtime because SQLModel and the project test dependencies are not installed here. The focused Node test is run separately against the exact extracted `getAnalysisHistory` helper; it is not a substitute for the full Expo typecheck or backend integration suite.

CI at starting head `b36ee8e62951ab39f13f00304b2123b4ba1608d6`: 0 check runs, 0 commit statuses and 0 workflow runs associated with that exact SHA. The latest branch-listed Android run `44273348890` points to older code SHA `5b692f7637d60136446f1efaa09178009ba1d209`; its job has `runner_id=0`, `steps=null`, and the step lookup is empty. It is not evidence of a typecheck or Gradle failure on the current head. Android typecheck, Gradle/APK, full Python security tests, real-device and 60,000-user load acceptance remain open.

No main merge, production deployment, migration, APK/IPA publication or clinical record mutation.


## 2026-11-20 — Web patient analysis and treatment history paging

Web-first review found that `patient_detail` loaded every analysis and treatment, then loaded all image assets and completed voice-review jobs for the full history. The web profile now uses a 20-row plus one look-ahead cursor page for both histories, deterministic `(created_at DESC, id DESC)` ordering, and page-scoped assets/voice markers. Cookie-session continuation routes re-check patient access and return private/no-store JSON with Jinja-rendered, autoescaped history fragments. The existing analysis modal/image groups/voice labels and treatment first-three collapse interaction are preserved across pages. New Python integration and Node source-contract regressions are registered in the manual Security Recovery workflow and beta suite. Read-back source checks 15/15, isolated cursor checks 8/8, Jinja partial syntax 2/2; full FastAPI/SQLModel integration, Node suite, Expo typecheck, Android build/device, browser and load tests remain unexecuted. Both Android and Security Recovery workflows remain manual-only while hosted jobs fail before step 1; no CI pass is claimed. No schema/migration, main merge, production deploy, APK/IPA publication or clinical record mutation. Details: `docs/web-patient-history-pagination-20261120.md`.


The patient-history integration fixture also places all 25 records at the same timestamp, exercising the descending ID tie-break at the page boundary; the newer concurrent insert remains outside the cursor walk.


## 2026-11-20 — Native patient-history stable cursor and treatment cards

Web-first review re-read `patient_detail.html`, `patient_treatment_history_items.html`, `patient_history_web.py`, `patient_history_pagination.py` and the mounted mobile analysis-history route before editing.

- Native analysis history now requests the backend's `stable_order=true` / `before_cursor` contract, matching web `created_at DESC, id DESC` order. Patient and FDI filters are validated on every page; duplicate IDs, malformed/looping cursors and mismatched patient rows fail closed.
- A first-page compatibility fallback retains numeric-ID pagination for older deployed servers that omit the stable cursor field or return `next_cursor: null` alongside a valid numeric `next_before`. Once a stable cursor is issued, the continuation must remain stable.
- Native treatment history now uses web-aligned bordered cards and metadata chips for tooth/date/material, while preserving result and doctor-note fields. The native edit action is disabled until profile/treatment/delete durable-intent gates are resolved.
- Added `patientAnalysisHistoryCursor.cjs`, updated `patientAnalysisHistory.cjs` and `patientHistoryRetry.cjs`, and added `patientTreatmentPresentation.cjs`. Both new tests are registered in beta and Security Recovery.
- Isolated strict TypeScript + Node checks: stable cursor helper 7 assertions; treatment presentation helper 13 assertions. Committed React Native / repository test files were not executed in this runtime.
- Current head `754d2be90ac0576b3f639b40db5e57e5f580b822` had zero status checks and zero PR workflow runs. Historical Android/Security jobs still have null/empty steps; no compiler, Gradle or pytest execution is evidenced. The independent audit's 13 Python patient-history failures remain unverified because the pytest trace and checkout environment are unavailable.

Details and safety limits: `docs/mobile-patient-history-treatment-parity-20261120.md`. A concurrent manual `app/mobile_analysis_api.py` cursor-validation change made after the initial read was preserved; the native work did not overwrite that file. No merge, deployment, migration or patient-data mutation.


## 2026-11-20 — media CI regression repair and patient-profile field parity

Starting head: `1b41c7f621b64efd5b74e0b613c922e8d036751d`.

The Android workflow at run `44790786839` completed successfully: TypeScript typecheck, session/auth, realtime/pagination, beta regression, Expo Android/iOS export and ARM64 internal APK all passed. The Security Recovery workflow `44790786710` ran its Python suite and reported `560 passed, 2 failed`; five native security jobs passed.

The two Python failures were test-contract defects, not a demonstrated authorization bypass:
- The original-media route test compared one formatted path in `main.app.routes` and found zero matches, despite the canonical router endpoint and request-level media tests being present. It now verifies the canonical endpoint identity in the source router and mounted application, and rejects a duplicate modern-router shadow.
- The media-owner security source assertion searched for whitespace-free text while the implementation uses normal Python spacing. It now normalizes whitespace before checking the patient/media owner predicates and private response helper.

The active original-file handler was inspected before editing. It checks both patient and media ownership, verifies `media.patient_id`, hydrates R2 outside the database session, then rechecks patient ownership, media ownership, patient relation, file path and original filename before returning a private/no-store response. No authorization condition was removed or weakened.

Patient profile web references were re-read first: `app/templates/patient_detail.html` defines the ordered editable fields `first_name`, `last_name`, `phone`, `tc_kimlik_no`, `birth_date`, `address`, and `chief_complaint`. The native screen already exposed these fields, but duplicated their metadata inline. The order, labels, date/text control choice, keyboard type, length limit and multiline behavior are now centralized in `patientProfilePresentation.ts`, consumed by `NativePatientProfile.tsx`, and compared directly with the web template by `patientProfileUI.cjs`.

Commits added in this pass:
- `6532440` canonical original-media route test by endpoint identity
- `d2a8496` whitespace-normalized media-owner assertion
- `66da0ea` centralized patient-profile edit field contract
- `23663b0` native profile renders the shared field contract
- `8d13ecc` web/native profile field parity regression

The source changes and new tests are committed. A fresh CI run for the final head is still required; no new test pass is claimed until the hosted jobs execute. No main merge, production deploy, patient-data mutation or production migration was performed.


## 2026-11-20 — latest-head CI root causes and tooth-history parity

Starting head: `887c35a794ca0ab3584ab4e159c643084319495e`.

The actual job logs for Android CI #4346 and Security Recovery #2045 were inspected:

- Android TypeScript typecheck passed; session/auth and realtime/pagination passed; Android/iOS Expo export passed; the ARM64 internal APK job passed.
- The beta regression suite had 249/250 passing. Its only failure was `native patient edit controls match the web patient_detail field contract`: the test's regular expression used a double-escaped word boundary and therefore parsed zero web input names. The native field contract itself returned the expected seven ordered fields.
- Python security had 561 passing and one failing. The failing assertion searched `main.app.routes` for a flattened endpoint. FastAPI's included-router representation did not expose the route as a direct endpoint item even though `app.include_router(mobile_router)` is present. The assertion now uses the public OpenAPI path surface, retains the canonical APIRouter endpoint identity check, and still rejects a duplicate modern-router shadow.
- The native clinical-security job repeated the same beta-suite profile parser failure (249/250); it was not a separate clinical authorization regression. Native Program, Voice, Social and Academic security jobs passed.

Web-first tooth-history comparison re-read `app/templates/tooth_chart.html` and the mounted native `NativeToothChart.tsx` flow. Both sides expose the selected tooth's surface observations, analysis history and separately persisted treatment records. Native treatment history has cursor continuation; selected-tooth analysis history receives the current FDI tooth. A new pure presentation helper centralizes Turkish labels for persisted surface/status codes while preserving unknown future values. New Node regressions cover all supported codes, forward-compatible unknown codes, the three web history sources and rendered selected-tooth cursor scoping.

Commits in this pass:
- fix the profile test's escaped word boundary
- verify the mounted original-media route through FastAPI OpenAPI
- centralize native tooth-history labels
- add the web/native tooth-history presentation contract tests
- add rendered selected-tooth history cursor coverage
- record this CI and parity evidence

The new tests are committed but their post-fix workflow result is still required. No clinical records, owner predicates, database schema, provider, dependency, main branch or production environment were changed. No merge, deploy, migration or APK/IPA publication.


## 2026-11-21 — clinical media camera parity and private image cache scope

Starting PR head: `e3b7b72b4571651cd162efbc4b2a8c5f2937e660`.

### CI evidence inspected before changes

- Android CI run [44840473644](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44840473644): the `npm run typecheck` step completed successfully; Android internal APK build succeeded. The job later failed in beta regression at 900/901 because the rendered voice-retry fixture did not publish the recorder's completed-session state.
- Security Recovery [44840473660](https://github.com/dentalaidestek/dental-ai-v02/actions/runs/44840473660): Python security passed; Native Program, Academic and Social passed. Native Clinical (253/254) and Native Voice (76/77) repeated the same voice workflow fixture failure.
- The failing assertion was the second source-only finalization call. `NativeVoiceRecorder` persists `ended: true` and publishes `finished: true` through `onSessionState`; the test called `onFinished` without reproducing that state callback. The fixture now emits the finished state before the final transcript callback. No production voice guard was weakened.

### Web-first clinical media comparison

Re-read `app/templates/patient_detail.html` and its inline gallery/upload scripts before changing native behavior. The web archive provides:
- a multi-file image input that can expose the mobile browser's camera/gallery picker;
- distinct PHOTO/RADIOGRAPH intent;
- bounded 12-file / 12 MiB per-file / 96 MiB batch validation;
- cursor-paged gallery, selection capped at four images, thumbnail cards and original-file preview;
- delete confirmation and explicit retry after gallery read errors.

Compared `NativePatientMedia.tsx`, `modernApi.ts`, `mobile_api.py`, and `mobile_modern_api_v3.py`. Native archive already had encrypted local drafts, per-file request receipts, batch reconciliation, byte progress, owner-scoped APIs, and thumbnail/original endpoints. Two parity/security gaps remained:
1. The archive only opened the photo library. The separate AI analysis composer already supported camera capture, but the patient archive did not. Added a camera action that uses the same normalization, encryption, 12/96 MiB checks, version-3 secure draft, batch ID and per-file request keys as gallery selection. It does not upload until the clinician explicitly presses Save.
2. Remote archive images used media-ID-only React keys and inline image sources. After an account/session switch, the same media ID could reuse an image component/cache identity. Added opaque per-component session-scope keys (without embedding bearer tokens in React keys) and a private source helper that validates canonical mobile media URLs, attaches the current Bearer token, and requests image cache revalidation.

Also removed the second hard-coded API base in `modernApi.ts`; it now imports the exported `API_BASE` from `api.ts`, keeping media and other modern endpoints on the same canonical origin.

### Added regression coverage

- camera capture is staged into an encrypted, account/patient-scoped draft before network upload;
- denied camera permission creates no draft and performs no encryption;
- owner/session/variant changes produce distinct image keys;
- private image source rejects external, malformed, query-bearing and unscoped URLs;
- private image source carries the current Authorization header and `cache: reload`;
- web/native archive camera and thumbnail/original behavior remains explicitly compared;
- modern API base import is checked against the shared API module.

- Rendered account-switch fixtures now use canonical mobile media URLs, so the private-source guard is exercised rather than bypassed with external test URLs.

The new HEAD must still run Android typecheck, all beta tests, Security Recovery and the native clinical/voice suites. No post-change pass is claimed before those jobs complete. No production patient data, database, migration, main branch or live deployment was touched.


## 2026-11-21 — runner-backed CI triage and regression repair

### Web-first source comparison

Before touching the failing parity tests, re-read the canonical web sources and compared their native counterparts:

- Dashboard program card and recent patient/search flow: `app/templates/dashboard.html`, `app/templates/patients_all.html`, `app/templates/patient_search.html`, `mobile/App.tsx`.
- Notification badge/read behavior: `app/templates/base.html`, `mobile/App.tsx`, `mobile/src/notificationRefresh.ts`, `mobile/src/ModernScreens.tsx`.
- FDI tooth chart entry and surface controls: `app/templates/tooth_chart.html`, `app/static/tooth-chart/surface-options.js`, `mobile/src/NativeToothChart.tsx`, `mobile/src/api.ts`.

### CI evidence at head `0ea3ad2`

The new runner-backed checks did execute; this was not the earlier zero-step/BlobNotFound runner-allocation failure:

- Android typecheck: passed.
- Session/auth and realtime/pagination checks: passed.
- Expo Android + iOS JS bundle export: passed.
- Internal Android release APK assembly: passed.
- Native security regressions: 558/558 passed across clinical (259), voice (77), social (86), program (45), support (19), and academic (72); zero skipped.
- Python security/identity recovery: 573 passed; PostgreSQL migration/concurrency: 29 passed; zero test failures.
- Mobile beta suite: 938/945 passed, seven failed. The failures were source-contract/test-harness drift, not TypeScript errors or demonstrated clinical-flow defects.

### Seven beta failures and exact repairs

1. Dashboard program navigation test expected the earlier `eventId`-only route params. The current native card intentionally adds `openRequestId` so tapping the same event can reopen its editor. Updated the assertion to the current route contract.
2. Notification badge test expected the old inline `loadUnread()` statement. The home screen now explicitly discards the promise with `void`, and the read-event predicate moved to `notificationRefresh.ts`. Updated the test to verify the focused refresh and effect dependencies.
3. Patient-directory test expected stale placeholder copy and did not read the web directory template. It now checks both canonical web search entry points and the current native copy, including name, patient number, phone and TC fields.
4–7. All four tooth-chart focus tests failed before reaching their assertions because `api.ts` now imports the shared `dashboardPresentation` validator. The isolated VM loader mocked the directory helper but treated the new, legitimate import as unexpected. The test now loads the real shared helper instead of weakening the API contract.
5. The Python dashboard security test previously caught every exception while importing Starlette `TestClient` and silently skipped itself. The security workflow explicitly installs `httpx`; removed the broad catch and skip so a broken test environment now fails visibly. The runner-backed Python suite at the preceding head imported TestClient and completed the dashboard test; this change removes the future false-green path.

### Commits on the development branch

- `2750ad0` — dashboard program open-intent assertion
- `64b35b6` — focused notification unread refresh assertion
- `1e26207` — compare native patient search fields with web templates
- `e9861cf` — load the shared dashboard validator in tooth-chart API tests
- `cd9a13a` — stop silently skipping the Python dashboard security test

These five commits change regression coverage/test harnesses only; they do not claim new production feature behavior. The seven failures have not yet been re-run against the repaired head.

### Current head and release boundary

Current branch head after these five commits: `cd9a13ae6fa81903b9ff4deb0036100a60c3233b`. Fresh PR-triggered Android and Security Recovery runs were created (Android run `44889780018`, Security Recovery run `44889780057`) and were still pending when this note was written; no green result is claimed for the repaired head yet.

No `main` merge, production deploy, database migration, store release, APK publication, patient-record mutation, or clinical audio upload was performed. Remaining next gate: complete both current-head workflows, then continue the next web-first native feature audit and real two-account/device acceptance. The 60,000-user target remains un-certified; this run did not execute load testing.


## 2026-11-21 follow-up — Voice Exam dashboard feature-flag parity

### Web-first finding

Rechecked `app/templates/dashboard.html` before changing native behavior. The web card is rendered only when `voice_exam_enabled()` is true **and** the account role is `DOCTOR` or `ADMIN`. The same feature gate is enforced by the voice API (`app.voice_exam_core.enabled()`); when disabled, native voice API requests return 503. The mobile home card previously checked only the role, so it advertised an unusable feature while the server flag was off. This was a real web/native behavior mismatch, not a test-only discrepancy.

### Branch fix

- `GET /api/mobile/v1/dashboard` now returns `voice_exam_enabled` from the exact shared `app.voice_exam_core.enabled()` helper used by the web template and API routes. This adds no database query and no extra mobile request; the dashboard remains private/no-store.
- Mobile `Dashboard` treats the flag as optional for old-server compatibility, but validates any supplied value as a boolean. A malformed value fails closed.
- Native Home now renders the Voice Exam card only when the role is `DOCTOR`/`ADMIN` **and** the server explicitly returns `voice_exam_enabled === true`. Missing flag on an older backend hides the entry rather than advertising a disabled route.
- Python dashboard regression covers enabled and disabled environment values. Native beta regression covers true, malformed flag, and the home visibility gate.

### Five commits

- `41165ae` — return the canonical voice feature flag from mobile dashboard
- `8799b73` — validate the optional dashboard feature flag in the native API client
- `aeb106b` — hide the native voice entry when the server feature is disabled
- `d0ea01b` — cover enabled/disabled backend behavior
- `c33be39` — cover native visibility and malformed feature-flag rejection

### Validation boundary

Current branch head: `c33be398b5dffc2ed1c5b1042b021118dd29f2dd`. The GitHub commit status endpoint currently returns no checks for this head, and no PR-triggered workflow run is attached to it. The prior run on `0ea3ad2` is useful historical evidence only: Android typecheck and APK/export passed, the six native security suites passed 558/558, Python security passed 573 and PostgreSQL passed 29, but the mobile beta suite had seven stale contract/harness failures. Those seven test fixes are committed earlier on this branch; the repaired suite has not yet been re-run against the current head. A local GitHub clone was not available in this run, so no local test result is claimed.

No main merge, live deployment, migration, store publication, or real patient/audio operation was performed. Next gate is a runner-backed Android + Security Recovery run against the current head. After that, continue the web-first patient-profile/tooth-chart/media visual and functional acceptance; the 60,000-user target remains un-certified.

## 2026-11-21 — Native voice audio-mode recovery

Web-first trace completed before edits: `voice-exam.js`, `voice-exam-live.js` and `voice-finish-draft.js`. New gap: Expo Audio's app-wide `allowsRecording` mode could remain enabled when a 15-second rotation's next `prepareToRecordAsync` failed, or when the recorder screen unmounted after stopping. The browser flow closes its owned microphone stream; native must additionally restore the app-wide playback route.

Added an explicit, testable `restoreVoiceAudioMode` helper and guarded restoration across normal cut, rotation/start failure, pause/finish failure, ASR drain failure, idle exits and unmount cleanup. The helper does not reset audio mode while the recorder is still active; a failed reset is surfaced in the foreground UI. No patient data, audio file, server endpoint, polling, database or production configuration was changed.

Regression coverage added to `mobile/tests/voiceWorkflow.cjs`: helper success/failure, synthetic second-chunk preparation failure after a successful first chunk, and unmount after recording. The suite is part of `npm run test:beta`.

Commits on this work package: `f3d2194` (restore helper), `30e15ca` (recorder failure/unmount restoration), `3c9d313` (idle and drain failure paths), `df65557` (regressions), `589c9a4` (evidence note), followed by this tracker update.

Latest verified starting-head CI before this work: PR HEAD `ecc024c` had Android typecheck, 77/77 native voice tests, Android APK, Expo Android/iOS bundles, Python security/PostgreSQL and six native security jobs all successful (Android run 44899242820; Security Recovery run 44899242833). The current branch HEAD has advanced; new runs 44902342039 (Android) and 44902342087 (Security Recovery) were created but their job lists are still empty/pending at the time of this note. No passing result is claimed for the new audio-mode regressions until those latest-head jobs complete.

Physical Android/iOS audio-route acceptance remains open, including Bluetooth, phone/notification interruption, app background/foreground and playback after stopping. No main merge, live deployment, APK/IPA publication or production patient-data operation.


## 2026-11-21 — session-key CI root cause

PR head `857feb3d9342e0af74244348cf4335af4b6e4b9a` had a passing `npm run typecheck` step, but the Android workflow failed later in realtime/recovery and beta tests; Security Recovery failed only in Native Clinical. The common runtime error was `nextSessionRenderKey is not a function`: the three VM-based CJS test harnesses for `NativeDentalAI` and `NativeClinicalReview` did not map the newly imported `./sessionRenderKey` module. This is a test harness integration defect; it does not establish a production component failure. The Native Clinical viewer test additionally asserted the obsolete user-ID-based key after the app had moved to opaque session keys.

Added a shared test-only TypeScript bridge and explicit module mappings in `analysisRefresh.cjs`, `analysisRecovery.cjs` and `clinicalWorkflow.cjs`; updated the stale key assertion; and added a regression requiring all harnesses to resolve the helper. Latest-head rerun is pending after these commits. Do not mark the Android beta/recovery suites green until the new CI jobs complete. No main merge, production deploy or clinical record mutation.


## 2026-11-21 — Voice Exam CI harness repair and web-entry parity

### Web-first inspection

Before editing native UI, compared `app/templates/voice_exam_entry.html`, `app/templates/voice_exam_panel.html`, `app/static/voice-exam.css`, `app/static/voice-exam-live.js` and `app/static/voice-exam.js` with `mobile/src/VoiceExamEntry.tsx`, `NativePatientSelect.tsx` and `NativeVoiceRecorder.tsx`. The web entry exposes a three-step flow, distinct new/existing-patient paths, a bounded patient search, and an explicit microphone/privacy notice. The native entry previously compressed those into one generic card and showed appointment-oriented search copy inside the patient picker. A supplied patient ID also stopped at the selection stage even though the web session URL opens the examination directly.

### Starting-head CI root cause

At `f48c1b39fa67508d64c971199a6ba607c0da83bd`, Android typecheck, session/auth, realtime/pagination, APK assembly and Android/iOS JS bundle export passed. The beta suite passed 969/974 tests; five VoiceExamEntry tests failed with `sessionRenderKey_1.nextSessionRenderKey is not a function`. Security Recovery reproduced the same five failures in native voice/clinical jobs. Python security/identity recovery, PostgreSQL migration/concurrency and native Program, Social, Academic and Support security suites passed. This was a test VM module-resolution/bridge failure; it was not an Android typecheck regression and did not demonstrate a clinical API authorization defect.

### Changes and commits

- `401e1f0` — load the actual production session-key helper through Node's CommonJS module loader.
- `9ca1907` — make all voice VM mappings tolerate extensionless and explicit TypeScript module specifiers; update patient-specific route tests to expect direct exam entry.
- `145c00c` — assert the shared helper export and all six VM mappings.
- `c734bfe` — add optional search title/hint/placeholder/empty-label props to the shared patient selector; appointment defaults remain unchanged.
- `276b8bc` — redesign the native Voice Exam entry hierarchy to match the web hero, steps, new/existing-patient cards and privacy note; verified `initialPatientId` now opens the exam stage without a redundant tap.
- `88b13d7` — cover contextual patient-search copy while retaining appointment defaults.
- `e508034` — cover web-first Voice Exam hierarchy, privacy guidance and direct patient-route parity.
- `4274406` — record the CI diagnosis and release boundary in the focused voice review.

### Validation and next gate

The repaired head has not yet received fresh completed Android/Security Recovery results in this work package. Do not call the five VM failures fixed until those jobs rerun green. No local typecheck/test result is claimed, no web/backend or provider behavior was changed, and no main merge, live deploy, APK/IPA release, migration or patient-data operation occurred. Next: verify current-head CI, then resume web-first patient-profile, clinical-media and AI-analysis parity; 60,000-user scale remains un-certified and needs dedicated load testing.


## 2026-11-22 — Revision-21 anamnesis index integrity and PostgreSQL CI correction

Web-first review was repeated before this follow-up: patient_detail.html renders only the owner-scoped voice_history.fields supplied by reviewed_history_payload; the native NativePatientProfile mounts NativePatientVoiceHistory, which reads the same root-mounted voice history API. The profile edit revision, treatment receipts, clinical media and FDI quick actions were not replaced or bypassed.

### Verified starting CI
- Android run #4682 on starting head 7b0ca8f: TypeScript typecheck, session/auth, realtime/pagination, 985 beta regressions, Hermes export, Android APK assembly and artifact upload all succeeded.
- Security Recovery #2381 on starting head 7b0ca8f: Python security suite succeeded; PostgreSQL optimization had 28 passed / 1 failed. The only failure was the second migrate.apply() assertion in test_program_pending_reminder_index_migration_upgrades_revision19_and_is_idempotent, which still expected revision 20. The migration log showed revision 21 after the approved-anamnesis migration. Updated only that final-state assertion to 21; earlier revision-20 partial-migration assertions remain unchanged.

### New source-level finding and correction
The approved-anamnesis query index was checked by name only. A malformed index with the expected name but wrong columns could therefore pass require_schema; a revision-21 migration retry could also silently accept it because CREATE INDEX ... IF NOT EXISTS does not replace a same-name index. The migration/startup guard now verifies the exact non-unique columns owner_user_id, patient_id, field_key, analysis_id and PostgreSQL indisvalid. A malformed same-name index fails closed without changing revision or existing ledger rows; a missing index is recreated when safe.

Additional voice regressions prove that partial approval of one field does not erase other previously approved fields, and a stale revision cannot replace or duplicate existing anamnesis.

### Commits in this follow-up
- d11028c — correct the repeated full-release migration assertion to revision 21
- 794f627 — validate the exact approved-anamnesis query index at migration and startup
- 2ead7cc — malformed/missing index migration and startup regressions
- db40960 — partial approval retention and stale-revision data-preservation regressions

The new tests are committed but have not yet been executed on this updated head. The only verified green Android run and the one-failure Security run above predate these commits. No local repository checkout or workflow-dispatch action is available through the current GitHub connector, so no new test result is claimed until a workflow run is associated with the new head. No staging or production database was modified; no main merge or live deployment occurred.


## 2026-11-22 — Current-head security correction and patient-profile warning parity

Web-first review:
- Re-read `app/templates/patient_detail.html`: the approved anamnesis card renders the backend-provided `voice_history.notice` once after the field rows.
- Re-read `mobile/src/NativePatientProfile.tsx` and `NativePatientVoiceHistory.tsx`: native uses the same approved-history endpoint and displays the server notice, but also appended a second native-only current-status warning. Removed the duplicate; the clinical caution remains in the canonical server notice.
- Rechecked the web profile action inventory (expert support, FDI chart, AI analysis, appointment, treatment, patient edit/delete, clinical media, analysis history, approved anamnesis and treatment history) against the native profile and its existing parity tests. No placeholder or WebView was introduced.

Starting-head CI evidence (PR head `5aa447dc052b60119357b32011b99fea92bc124f`):
- Android run #4688: TypeScript typecheck, session/auth, realtime/pagination, mobile beta regressions, Android/iOS Hermes export, and internal Android APK assembly/artifact upload all succeeded.
- Security Recovery run #2387: all six native security jobs succeeded. Python security ran 605 tests: 604 passed and one failed. The only failure was `test_require_schema_fails_closed_if_latest_history_index_is_missing`; its expected stable phrase `approved anamnesis query index` was split by the new error wording (`approved anamnesis owner/patient/field/source query index`). This was a message-contract mismatch, not a migration/index assertion failure.
- Fixed the production error message to retain the stable phrase and still explain the exact owner/patient/field/source columns. Strengthened the existing regression to assert the actionable detail; no test was weakened or removed.

Commits in this follow-up:
- `8830412` — keep the approved-anamnesis index error contract stable
- `96e15ab` — assert the actionable owner/patient/field/source detail
- `0b47b61` — remove the duplicate native-only anamnesis warning
- `a4fe29a` — verify the canonical warning is rendered exactly once

The next PR-triggered CI run is expected to execute on this updated head because the changed paths are included in the Android and Security Recovery workflows. Until that run completes, the updated Python regression and native warning test are committed but not claimed as passed. PostgreSQL staging migration/count/provenance/idempotency/rollback acceptance and 60,000-user load testing remain open. No staging or production database was changed; no main merge or live deployment occurred.
