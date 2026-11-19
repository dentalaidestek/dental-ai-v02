# Native Academic AI parity — 2026-11-18

## Web-first reference

Before editing native code, reviewed the branch versions of:

- `app/templates/notes_course.html`: course library, source upload/list, delete, rename, course deletion and entry to Academic AI.
- `app/templates/notes_ai.html`: index readiness, per-file status, source-bounded chat, fixed composer, quick prompts, 5/20-question generation, quiz answer feedback, learning progress, answer feedback, PDF artifacts, run cancellation/resume and upload.
- `app/mobile_academic_api.py`, `app/study_index_jobs.py`, `app/study_index_worker.py`, `app/study_rag.py`, and `app/academic_study_runs.py`: owner-scoped course/material/run access, durable index jobs, source versions, request-key run receipts and cancellation.

Native already has course pagination, 150 MB per-file upload limit from the server, PDF/image viewing, paginated message history, source page/quote display, learning/quiz tabs, durable run intent, cancellation, foreground-only polling, and per-file index polling. No provider, RAG, source taxonomy, or automatic clinical-record behavior was changed.

## Defects found and fixed

1. **Android TypeScript parser failure:** `NativeAcademic.tsx` contained a literal backslash-n between the `indexPending` declaration and `useEffect`; `academicApi.ts` contained literal backslash-n separators before two exports. These are source syntax defects, independent of the GitHub runner issue. Replaced them with real statement boundaries and added a TypeScript parser-diagnostic regression.
2. **Optional academic endpoints blocked the whole course:** `refresh()` used `Promise.allSettled` but treated learning, quiz and index-status failures like required workspace/timeline failures. A temporary learning or quiz outage marked the screen broken and blocked the composer. Learning/quizzes now degrade independently; index failure leaves the source/chat view readable but keeps generation disabled; workspace/timeline failures remain fail-closed.
3. **Academic upload accepted arbitrary file URIs:** `file://` prefix alone did not prove the file was inside the app's private cache. Upload now requires a normalized path under Expo's cache directory, rejects traversal/query/fragment/control characters and path-like filenames, and checks extension/MIME consistency before reading the file.
4. **Temporary file lifecycle:** a local academic file is deleted only after an explicit successful server acknowledgement. Timeout, abort or an ambiguous response preserves the local copy for reconciliation instead of deleting the only retry source.

## Regression coverage added

- `mobile/tests/academicWorkflow.cjs`: parser diagnostics, optional learning/quiz failure, index-status fail-closed behavior and required timeline failure.
- `mobile/tests/academicFileSecurity.cjs`: private-cache containment, encoded traversal, path-like filename, MIME mismatch, successful cleanup and timeout preservation.
- `mobile/package.json`: new file-security test registered in `test:beta`.
- `.github/workflows/security-recovery.yml`: dedicated `native-academic-security` job and path filters for Academic native code/tests.

The tests are committed but were not executed in this environment. The parser test is intended to catch the exact invalid statement separators found in this pass.

## CI evidence at start

PR #257 head was `58daa8fd8337d0f4ae661672cc67e2c4f7ef2805`. Current-head workflow runs included Android `44186032867` and Security Recovery `44186032879`. Android typecheck job `134402688483` and Security jobs `134402691151`, `134402691628`, `134402691767` reported empty step arrays; job-log downloads returned `BlobNotFound 404`. The compiler and regression commands did not start. This does not erase the source-level syntax defects found by reading the files, and it does not establish that the fixes pass a full typecheck.

## Remaining acceptance

- Run `npm ci && npm run typecheck` and the Academic Node tests on an allocated runner.
- Run full `npm run test:beta`, Android/iOS Expo exports and device checks.
- Verify upload reconciliation after a lost response against a staging backend; local cache retention is intentional until server state is confirmed.
- Exercise index worker recovery and source deletion with a staging PostgreSQL/worker environment.
- Continue performance and 60,000-user load acceptance; no capacity claim is made.

No main merge, production deploy, migration, APK/IPA publication or clinical-record mutation was performed.


## Additional recovery hardening — 2026-11-18

A second pass found two more ambiguous-write paths in the native library:

- Course creation previously exposed a manual “I checked the list; allow another create” override after a lost response. That could create a duplicate without a server receipt. The override is removed. The app now stores an account-bound intent in SecureStore (exact title/description plus IDs already visible), restores it after restart, refreshes the owner-scoped library using the exact title, and opens only a new matching course. If no match is visible, creation remains locked. The backend course-create endpoint still has no durable idempotency receipt; safe retry after a confirmed non-creation remains an open backend improvement.
- Upload recovery previously cleared its local marker after any successful workspace refresh, even if the material was not present. The marker is now structured and bound to user/course, URI, filename, file size when supplied by the picker, and pre-existing material IDs. Recovery requires a newly created same-name/same-size material row before deleting the private cache copy and clearing the marker. A failed lookup or missing row keeps the marker and local file; duplicate filenames in one batch are rejected. Legacy unstructured markers fail closed rather than being silently cleared.

Additional helpers and regressions cover exact course matching, same-name upload receipt matching, file-size mismatch, user/course-bound upload intents, and guarded cache cleanup. The upload recovery match uses the first workspace page (new materials are ordered newest first); if the row is not visible, it intentionally stays locked rather than risking a duplicate.


Course creation intent persistence is also covered across an app restart: the intent is written before the POST, bound to the user ID, and removed only after a new exact-match course row is found or the successful create response is reconciled. A malformed saved intent remains fail-closed.


## Latest CI retry evidence — code-bearing head 7c3c8ec

- Android run `44197159856`: typecheck job `134441492458` failed before any step. Its explicit retry `134441669316` also completed in seconds with `runner_id=0`, empty runner name, `steps=[]`, and log download `BlobNotFound 404`.
- Security Recovery run `44197159784`: `native-academic-security` job `134441492816` failed before any step. Retry `134441687400` likewise ended with `runner_id=0`, empty runner name, `steps=[]`, and `BlobNotFound 404`.
- Thus the new Academic parser, UI and upload-security regressions still have not executed on GitHub Actions. The source-level syntax fixes are committed, but Android typecheck and Node regression acceptance remain unverified until a runner is allocated.

## Native Academic router and response-contract pass — 2026-11-19

### Web-first comparison

Re-read the web course library and Academic AI chat in `app/templates/notes_course.html` and `app/templates/notes_ai.html`, then followed the same owner-scoped course, material, run, quiz, learning and indexed-page contracts through `app/mobile_academic_api.py` and the native `academicApi.ts` / `NativeAcademic.tsx` consumers. The native screen already has 50-item course/material/timeline paging, source-file links, quiz history, learning review, source-page inspection and durable run recovery; this pass preserves those flows and does not change providers, retrieval, indexing, or clinical data.

### Critical defect found and fixed

`app/mobile_academic_api.py` had a second appended copy of all 23 route declarations and a stray module-level closing parenthesis. The first copy was retained because it also contains request-key validation for course creation. The duplicate tail and unmatched parenthesis were removed. `app/mobile_api.py` imports and mounts this router, so the malformed module could prevent the mobile API (and application import path) from loading. The router now has 23 unique method/path declarations.

Added `test_mobile_academic_router_source_parses_and_registers_each_route_once` to the existing Python Academic workflow suite. It parses the source with Python AST and checks both declared and FastAPI-registered method/path uniqueness.

### Native response hardening

The mobile Academic API now rejects malformed or unbounded responses before they reach the UI:

- Timeline entries must have valid roles, timestamps, bounded text, unique ascending IDs and a consistent 50-row cursor.
- Nested quiz IDs must match their owning message; question numbers/options and answer state are validated.
- PDF artifact URLs are accepted only when they resolve to the same course's native Academic file route.
- Course-library and source-workspace pages validate descending IDs, cursors, material metadata and same-course file URLs; upload limits are capped to the web contract (150 MiB per file, 12 files).
- Learning summaries and review rows are bounded to the server's six-item review window.
- Indexed source-page responses must match the requested page and contain bounded, uniquely identified chunks.
- Run partial/error fields are type- and size-checked before rendering.

Added Node regressions in `mobile/tests/academicWorkflow.cjs` for duplicate/out-of-order timeline rows, oversized content, cross-course PDF links, malformed cursors, workspace file paths/limits, quiz state, learning review bounds, source-page mismatch and malformed run partials.

### Verification boundary

- Static source-contract checks: 10/10 passed (router import/mount, 23 unique routes, no dangling parenthesis, regression inclusion and API validator/test coverage).
- PR #257 head after this pass: `ca92938fe81b0e3a46c687c11c2257d2010832be`.
- GitHub workflow runs and commit statuses for that exact head: 0 / 0. The Security Recovery workflow remains manual-only; no CI dispatch was made, avoiding another runner-less run and notification noise.
- `npm run typecheck`, `npm run test:beta`, Python pytest, device testing and the 60,000-user load test were not executed in this environment. The new regressions are committed but not runtime-verified.

No main merge, production deployment, migration execution, APK publication or live clinical-data mutation was performed.

### Follow-up type boundary check

The canonical run serializer always includes `partial` and `error`, and either may be `null` before a provider result exists. The native type and validator now preserve that nullable contract instead of rejecting a valid queued/running run. A regression assertion covers `partial: null` and `error: null`.

The new validator logic was also copied into an isolated strict TypeScript check: compilation passed and six runtime assertions passed, including nullable run fields, a valid workspace, learning review, nullable source title, and malformed cursor rejection. The added Node and Python regression snippets passed syntax checks. These are focused checks only—not a substitute for the full mobile project typecheck or the repository pytest/Node suites.
