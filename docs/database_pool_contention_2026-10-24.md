# Database pool contention — 2026-10-24

## Production evidence

- The shared web engine was bounded at two connections, no overflow, with a
  five-second acquisition timeout. Authenticated page loads start several
  parallel probes; embedded application/reminder work uses the same engine.
- PR #209 made terminal academic builds visible but did not address pool
  contention. Timeouts persisted after that deployment.
- PR #210 added throttled, data-free holder diagnostics without changing pool
  behavior. Single status probes and a small parallel status-only check did
  not reproduce the timeout after restart.
- Opening two Academic AI pages concurrently reproduced HTTP 500s at
  11:18:01 UTC. The holder snapshot identified `template_user_context`, reading
  account/profile metadata, with a checkout age of 0.30 seconds at the instant
  the waiting request timed out. Other probes recovered immediately afterward.
  This supports burst starvation in the two-slot shared pool; it does not prove
  that every historical timeout has the same cause or exclude other slow paths.

## Repair

- Reduce web authentication from separate token/user reads to one outer join.
  Preserve token expiry cleanup, inactive/unverified/orphan rejection, and
  per-request caching only. No cross-request identity cache is introduced.
- Set web capacity to four, with overflow still zero and acquisition timeout
  still five seconds. Router capacity remains two. Keep Blueprint and live
  service configuration aligned; no secrets or other variables are changed.
- Keep holder diagnostics to identify any recurrence instead of assuming a
  larger pool resolves every possible cause.

## Local validation

29 tests pass: the actual authentication body with twenty parallel requests on
a real bounded four-connection pool; one authentication read; connection return;
inactive, unverified, orphan, unknown and expired tokens; expired-token cleanup;
no identity reuse across requests; pool exhaustion diagnostics and hard limits;
academic readiness/profile regressions. Local database tests use SQLite, not
PostgreSQL load tests. Production validation must follow deployment.

The fourth failed academic index build is a separate outstanding problem. A
successful status request or absence of connection timeouts does not mean that
file has been indexed successfully.
