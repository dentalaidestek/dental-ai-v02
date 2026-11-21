# Program PostgreSQL scale acceptance — 2026-11-17

## Web/native query paths reviewed

The web Program and native Program share the same ScheduleEvent rows and reminder queue. The native calendar calls:

- `app/main.py::_user_schedule_occurrences`: owner-scoped bounded date query, followed by weekly recurrence expansion and patient hydration.
- `app/mobile_program_api.py::_program_snapshot_changed`: checks whether an owner has created or updated an event after the page watermark. A cursor page performs this check before and after loading.
- `app/main.py::_process_program_reminder_jobs`: claims the oldest due PENDING reminders in a bounded batch with `FOR UPDATE SKIP LOCKED`.
- `app/main.py::_cancel_pending_program_reminders` and `_cancel_user_program_reminders`: cancel pending jobs by event or owner.

## New query indexes

Added additive composite indexes to the SQLModel metadata:

- `ix_scheduleevent_owner_start_at(owner_user_id, start_at)` — bounded owner calendar reads and ordering.
- `ix_scheduleevent_owner_created_at(owner_user_id, created_at)` and `ix_scheduleevent_owner_updated_at(owner_user_id, updated_at)` — owner-scoped snapshot invalidation without scanning all historical rows for that owner.
- `ix_programreminderjob_status_run_at(status, run_at)` — due reminder selection in run order.
- `ix_programreminderjob_event_status(schedule_event_id, status)` — event-specific cancellation and reconciliation.
- `ix_programreminderjob_owner_status(owner_user_id, status)` — account-scoped reminder cancellation.

These indexes add write and storage cost. The PostgreSQL integration test therefore checks actual planner selection against a synthetic multi-account dataset rather than treating the existence of an index as proof of improvement.

## Revision 16 migration

Revision 15 remains the stable Program idempotency schema. Revision 16 adds only the six indexes above.

The migration:

1. Takes session advisory lock `71048238` to serialize migration processes.
2. Uses an AUTOCOMMIT connection for `CREATE INDEX CONCURRENTLY`; it does not hold a table-wide write-blocking index build transaction.
3. Detects and drops an invalid index left by an interrupted concurrent build, then retries that index.
4. Verifies `pg_index.indisvalid` for every index.
5. Advances `dental_schema_revision` from 15 to 16 only after all six indexes are valid.

No migration was run against production in this work. The code remains on the feature branch and the normal pre-deploy migration gate is unchanged.

## PostgreSQL regression/scale coverage

`tests/test_postgres_optimization.py` now includes:

- A revision-15 to revision-16 migration test that drops the six indexes, applies the migration, and verifies all indexes are valid.
- A synthetic planner test with 60,000 distinct account owners, a busy owner with 2,000 calendar events, 60,000 future reminders and 1,000 due reminders.
- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` assertions for the owner/date, owner/snapshot and status/due queue paths.

The existing Security Recovery workflow already provisions PostgreSQL and runs `tests/test_postgres_optimization.py`; no extra hosted service or production credentials were added.

## Read-only plan report

For a disposable or staging PostgreSQL database, the new script emits only plan summaries (execution time, rows, buffer counts and index names); it does not print selected row values:

```sh
DENTAL_TEST_DATABASE_URL='postgresql://...' \
DENTAL_ALLOW_PROGRAM_PLAN_REPORT=1 \
DENTAL_PROGRAM_BENCHMARK_OWNER_ID=1 \
python scripts/program_query_plan_report.py
```

The explicit opt-in is required. Do not point this diagnostic at production as part of this unapproved branch work.

## Current validation boundary

The new PostgreSQL integration tests and report script are committed, but this run could not execute them against PostgreSQL. The current GitHub Actions jobs again failed before exposing any steps or logs (see the PR run links); this is not a passing query-plan benchmark.

No 60,000-user capacity claim is made. The remaining evidence needed is a successful disposable/staging PostgreSQL run with plan output, realistic reminder churn, concurrent calendar readers/writers, and end-to-end push delivery. Any production rollout requires the user's separate approval.
