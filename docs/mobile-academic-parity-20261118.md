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
