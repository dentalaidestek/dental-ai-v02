# Native Academic AI source adaptation — 2026-11-14

This continues PR #257 / issue #258 on the mobile branch. No main merge, deployment, provider change or store publication. Source adaptation is not production/device acceptance.

## Verified cause and change

The previous `ModernScreens.Academic` used course selection and synchronous `/ask`; it had no native material upload, indexing state, durable run recovery, structured quiz choices, saved feedback or learning panel. The web already has durable StudyRun requests and authoritative first-answer grading. `App.tsx` now opens `NativeAcademic`, backed by additive mobile adapters calling the existing web handlers and quiz/learning functions.

| Web function | Native adaptation |
|---|---|
| Course create/search/rename/delete | Owned library, bounded cursor pages and forms; destructive confirmation |
| PDF/JPG/PNG/WEBP upload | Native multipart task, byte progress, original filename metadata, web magic/150 MB/12-file validation and durable index enqueue |
| Index status | Actual per-file state, partial readiness, bounded foreground polling; no invented success |
| Saved extraction inspection | Native expandable source text, page selector, owned saved OCR/chunks; no new OCR/provider request |
| Ask, summarize, teach, generate questions | Same provider pipeline through durable StudyRun; local encrypted intent written before POST, stable UUID and read-only receipt lookup |
| Reopen/background | User/course-bound restore; active status polling only focused/foreground, errors and backoff; no automatic paid retry |
| Quiz selection | Real server question numbering, first answer immutable, hidden key before selection, rationale/source only after persisted answer; old-set answer receipt returns its quiz |
| Learning | Actual practiced/correct/wrong/due/weak facts and review prompt |
| Answers and sources | Native text/headings/emphasis/scrollable tables, source references, private PDF/source file access; no executable HTML/WebView |
| Feedback/new chat | Saved like/dislike, canonical history/learning/run clearing with confirmation |

New files: `app/mobile_academic_api.py`; `mobile/src/academicApi.ts`, `nativeAcademicFiles.ts`, `NativeAcademic.tsx`, `NativeAcademicFile.tsx`, `NativeAcademicSource.tsx`, `NativeAnswerText.tsx`; Python/Node regression files. Existing mobile router, App, package test script, security workflow and tracker updated. Existing old synchronous API remains for compatibility but is no longer the Academic entry.

## Mutation and privacy limits

Run receipt lookup includes DONE as well as active requests, preventing a lost POST response from becoming a second model request. The exact stored question/UUID is reused only on explicit retry; a malformed saved intent blocks new paid work. An explicit abandon first checks the receipt. New-course creation and material uploads do not gain fictional server idempotency: uncertain upload names survive in SecureStore and block another upload until the list is successfully refreshed and the user acknowledges checking it. File tasks have explicit deadlines even if native cancellation does not settle. Material validation and server authorization remain canonical. Private file URLs are strictly limited to this course's owned material/PDF routes before attaching a bearer token. Download caches are removed on unmount; native document-picker caches/process-death cleanup and extra raw-file encryption still need hardening/device acceptance. User-scoped secure intents survive restart; no tokens or source contents are logged.

## Validation

See the final checkpoint in PR/issue for exact fresh counts. Focused Python tests exercise real canonical handlers using isolated SQLite/synthetic fixtures: owned course CRUD, byte/magic upload/index enqueue, durable request-key receipt/conflict, hidden quiz key/immutable choice/grounded explanation, saved feedback, learning and clear ownership. Node tests exercise native double taps, intent recovery, known receipts, source errors, quiz choices, multipart progress/name, malformed account intent, nonsettling-upload timeout and native table rendering. Existing mobile/security tests and Android+iOS Hermes exports are rerun after integration.

## Acceptance still open

No actual Android release install, iOS signing/device run, production credentials/source inference/Modal indexing, two-device updates, full markdown/math/clipboard parity, accessibility/Android image pinch zoom, hard process-death recovery, upload deduplication transaction, background cache erasure or 60,000-user capacity claim. New adapters require a separately approved backend deployment before a production APK can use them. Remote CI previously failed without job steps and logs returned BlobNotFound404; local success is not a green remote CI run. Source work cannot certify these gates.

Final local verification after preserving gallery commits through `a9400e4771cfbcad0a08b9228f65fcaa6680455d`: TypeScript clean, **267/267 Node tests** (18 session + 46 realtime + 203 beta, including 12 Academic tests), **218/218 selected Python tests**, zero failures. Python emits 395 existing deprecation warnings. This is a selected acceptance suite, not the entire repository/browser/PostgreSQL suite. Prior broader-suite browser failures due unavailable Chromium/sandbox and skipped PostgreSQL checks remain open. Android and iOS Hermes export is repeated for the final source. Remote pre-push Android run `43629778794` has two failed jobs and no steps; typecheck job `132553593419` log fetch returned BlobNotFound404. The failing remote check's cause remains unconfirmed.
