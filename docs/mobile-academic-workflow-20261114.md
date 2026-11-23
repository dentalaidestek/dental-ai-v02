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


## 2026-11-17 — Native Academic AI fixed-composer parity

Web-first comparison re-read `app/templates/notes_ai.html` and the academic chat footer rules in `app/static/style.css` against `mobile/src/NativeAcademic.tsx`.

A concrete mobile UX regression was found: the native question field and send action lived inside the conversation `FlatList` header. After enough messages, the composer scrolled away with history. The web keeps its `study-chat-clean-footer` outside the scrollable message region.

Added `NativeAcademicComposer.tsx` as a separate native footer and moved the controlled question input/send action below the conversation list. The message list now takes the remaining vertical space and keeps taps available while the keyboard is open. The draft remains owned by the course screen, so switching to Sources or Questions and back does not discard it. The composer is hidden on those non-chat tabs, and disabled when sources are not ready, an unresolved paid-run intent exists, the screen is in a broken recovery state, or a run is active. Blank messages are blocked and the web 8,000-character limit is retained. No provider, route, database, polling or clinical-data behavior changed.

Regression coverage:
- Added `mobile/tests/academicComposer.cjs` for the 8,000-character limit, accessible controls, blank-send rejection and disabled-send behavior.
- Extended `academicWorkflow.cjs` to assert the composer is outside the scrolling FlatList and that a draft survives tab changes.
- Registered the new test in `npm run test:beta`.

Validation boundary: 11/11 GitHub-source contract checks passed against the committed files. The React renderer tests are committed and registered but were not executed in this runtime because the repository's installed React/test-renderer dependencies are not available here. Full project typecheck, `test:beta`, Android/iOS builds and physical-device keyboard/safe-area acceptance remain open. No main merge, backend deploy, store release or patient-data mutation.


## 2026-11-17 — Academic AI cancellation, checkpoint retention and index polling

Web-first reinspection used `app/templates/notes_ai.html`, its `waitForIndex` per-file status loop, `study_run_status`, and the owned index status helper. The native route and API were then compared with `app/mobile_academic_api.py`, `mobile/src/NativeAcademic.tsx` and `mobile/src/academicApi.ts`.

### New issues found and fixed

- **Native cancellation was wired to a missing canonical web handler on this branch.** The mobile adapter called `web.study_run_cancel`, but the branch had no route/helper. Added owner+course+run scoped `cancel_run`, the canonical web POST route and the web chat stop button. The web UI reconciles a lost cancellation response against the run status and removes any partial text only after the server confirms cancellation. A late worker cannot commit after the row becomes CANCELLED because `complete_in_transaction` checks RUNNING under row lock.
- **Index polling used the aggregate `partial` state.** That state also remains partial when one file is usable and another has permanently failed, so native could poll the same failed file forever. Native now follows the web contract exactly: poll only while a file is `preparing` or `updating`; a ready+failed partial snapshot stops polling. Index status is checked at 15-second intervals, active run status remains 5 seconds with backoff, and the effect has no timer while neither work item is active.
- **Visible checkpoints were discarded on failure/restart.** Failed and interrupted StudyRuns now retain the last safe visible checkpoint; hidden PDF/structured output does not overwrite it, and the final visible stream chunk is flushed. Explicit cancel/clear still removes partial content.
- **Long academic generation had a low continuation ceiling.** Kept a bounded policy rather than adopting unlimited provider continuation: 240,000 answer characters and six continuation calls. Large Anthropic source batches/structured question sets receive a 32k per-call budget; ordinary turns retain the lower 7k default. Continuation remains enabled for batch partials within the aggregate cap.

### Regression coverage added

- Native API contract tests cover per-file `preparing`/`updating`, ready+failed partial snapshots, complete snapshots and malformed counts.
- Native screen source contract checks cover idle stop, foreground/focus dependencies and the 15-second index cadence.
- Python mobile Academic regression checks cover cancellation ownership/idempotency and reject a late completion after cancellation.
- New `tests/academic_v2/test_study_progress_retention.py` checks safe checkpoint retention, cancellation scope and bounded continuation policy.

### Validation boundary

The GitHub source-level patch checks passed for all changed contracts. The new Node/Python integration tests are committed but were not executed in this environment. The current-head GitHub Actions Android typecheck and Security jobs still have `runner_id=0`, `steps=[]`, no artifacts, and log downloads return `BlobNotFound 404`; npm/tsc, pytest and Gradle did not start. Do not report these as source test failures or green CI.

No provider credentials, clinical data, patient records, schema migrations, main merge, production deploy or store build were changed. Full local test suite, PostgreSQL concurrency, real provider cost/continuation behavior and Android/iOS device acceptance remain open.


### Native recovery UI follow-up

The native run card now renders the last safe `run.partial` checkpoint through the existing safe Markdown renderer. FAILED and INTERRUPTED runs expose an explicit “Aynı Soruyu Yeniden Dene” action; restoring or polling an interrupted run never starts a new paid request automatically. The retry uses the original question with a new durable request key only after the user taps the button. The React-renderer regression is committed but awaits the unavailable CI runner.
