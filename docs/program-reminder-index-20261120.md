# Program reminder queue index — 2026-11-20

## Web-first path inspected

The canonical web Program screen remains `app/templates/program.html`. Reminder execution is shared by web and native records and is not a separate mobile implementation:

- `ProgramReminderJob` in `app/main.py`
- `_next_program_reminder_at()` — earliest pending wakeup
- `_process_program_reminder_jobs()` — ordered, bounded due-job claim with PostgreSQL `FOR UPDATE SKIP LOCKED`
- `_program_reminder_worker()` — drains due batches and sleeps until the next pending run time

The native Program API delegates reminder creation/cancellation to the same backend event handlers. The optimization therefore changes the shared queue schema, not reminder semantics or the web/mobile API contract.

## Exact CI failure and root cause

Security Recovery run #1980 on the previous head `b431ddb502c699b47c34d0d40797bf01437610ea` completed the Python security/identity suite and all five native security jobs successfully. The PostgreSQL optimization step had 24 passed and one failure:

`test_program_hot_queries_use_owner_and_due_queue_indexes_at_scale`

The test expected `ix_programreminderjob_status_run_at`, but PostgreSQL selected `ix_programreminderjob_run_at`. The fixture intentionally had 60,000 terminal DONE rows with old `run_at` values, 60,000 future PENDING rows, and only 1,000 due PENDING rows. With an ordered `LIMIT 100`, the single-column run_at path could walk terminal history before finding eligible work. The old assertion exposed a real query-plan weakness, not an application security failure.

## Change

- `ProgramReminderJob` now declares `ix_programreminderjob_pending_run_at` on `run_at` with predicate `status = 'PENDING'` for PostgreSQL and SQLite.
- The redundant broad `ix_programreminderjob_status_run_at` and `ix_programreminderjob_run_at` indexes are removed by schema revision 20, after the partial index is built and validated.
- PostgreSQL creates the new index with `CREATE INDEX CONCURRENTLY`, a dedicated advisory lock, bounded lock/statement timeouts, and `indisvalid`/index-definition checks.
- SQLite uses a transactional partial-index build for deterministic local tests.
- Revision 19 remains the treatment-history index checkpoint; revision 20 is the pending reminder queue index. Re-running the migration validates/repairs the index and is idempotent.
- Reminder status transitions, due-time calculation, retry/backoff, batch size, notification receipts, realtime publication, and `SKIP LOCKED` worker semantics are unchanged.

## Regression coverage added

- Revision 15 upgrade traverses the existing migrations through revision 20, verifies the new partial index and confirms the two broad reminder indexes are absent.
- Revision 19 upgrade creates the partial index, removes legacy indexes, and remains safe on a second migration invocation.
- SQLite revision 19 upgrade checks the partial predicate and idempotent retry.
- The scale plan now mirrors the actual worker query, including `FOR UPDATE SKIP LOCKED`, and checks both the due-claim and next-wakeup queries use the pending-only index.

## Acceptance boundary

These are synthetic query-plan tests, not a measured 60,000-user or concurrent-user capacity result. The new code and tests are committed on `feature/mobile-web-parity-20261110`; the exact latest-head Security Recovery and Android CI results must be read after this change. No production migration, merge, deploy, APK/IPA publication, or patient-data mutation was performed.


## Follow-up verification and hardening — 2026-11-20

At head `2844f63ce792340d8ec6a8675549c15899d8c77c`, Android CI #4294 completed successfully: TypeScript typecheck, session/auth, realtime/pagination, all 883 beta regressions, Android/iOS Expo export and the internal ARM64 APK job passed. Security Recovery #1992 passed the security/identity suite and all five native security jobs, but its PostgreSQL migration/concurrency step failed with 26 passed and one failed.

The failing test was `test_program_pending_reminder_index_migration_upgrades_revision19_and_is_idempotent`. The isolated `pg` fixture creates application metadata but intentionally does not create `dental_schema_revision`; the test attempted to update that table before establishing the revision-19 state. This was a test-fixture defect, not a migration runtime failure. The test now creates the revision table and sets revision 19 before invoking the migration.

The same log review exposed a migration-validation weakness: checking that the generated index definition merely contains the words `status` and `pending` would also accept a broader predicate such as `status IN ('PENDING','FAILED')`. PostgreSQL validation now reads `pg_get_expr(indpred, indrelid)`, normalizes casts/parentheses, and requires the exact predicate `status='pending'` as well as a valid btree `run_at` definition. A wrongly defined same-name index is rebuilt before legacy indexes are removed.

Additional regression coverage now checks:
- PostgreSQL repairs a revision-20 index whose predicate also includes FAILED rows.
- SQLite repairs the same broadened predicate.
- The migration refuses to mutate an unversioned SQLite schema.
- The revision-19 PostgreSQL fixture is initialized explicitly.

These follow-up changes are on the PR branch after the CI head above. Their new Security Recovery and Android runs must complete before they are considered accepted. No live database migration was run.
