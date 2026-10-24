# Academic index stall investigation — 2026-10-24

Base: e19d48b1a2b99a194dcbeb44b1ae09a607a97b7e (includes the separate 150 MB upload-limit change).

Authenticated production GET `/notes/courses/7/ai/index-status` returned `ready=false`, `completed=3`, `total=4`, `state=preparing`. This is a server-side readiness result, not merely a stale browser counter. No source file was deleted, uploaded again or requeued manually.

Render logs between 09:18 and 09:29 UTC (12:18–12:29 Türkiye) show repeated `sqlalchemy.exc.TimeoutError: QueuePool limit of size 2 overflow 0 reached`, timeout 5 seconds. The index-status and quiz requests returned HTTP 500. These logs establish pool contention; they do not establish which connection holder caused it, or prove that the same contention caused the currently incomplete index. Pool size has not been increased to conceal the problem.

The code has two independent readiness/recovery defects:

- A terminal `studyindexjob` can leave its material PROCESSING or leave an upgrade generation reserved. The status endpoint checked only `studymaterial.index_status`, so a failed/cancelled current job (or an orphan reservation) could remain `preparing` forever.
- Polling did not request recovery of existing work, and page-open recovery only selected QUEUED jobs. A worker that exited with an expired RUNNING lease could therefore remain unwoken by the open page.

The change checks the owned current generation for terminal/missing jobs and reports failure using the existing UI contract. Recovery selects only due QUEUED jobs or expired RUNNING leases belonging to this owner, course and current generation. It preserves checkpoints, lease fencing, active published indexes, future retry delays and terminal jobs. Poll recovery is coalesced to at most once per minute per course in each process, with a bounded 2048-entry cache; upload dispatch remains immediate. Across multiple web processes this is not a distributed dispatch limit, while database claim fencing still prevents duplicate job ownership.

Modal's current private job status is not verified: the available browser reached the Modal login screen. Historical successful dispatch acknowledgements do not establish that a current worker completed a job. The deployed Modal source was not changed. The exact status/error of the remaining current production job and the current database connection holders still require authenticated operational inspection.

The production task has not been marked recovered. Reviewable code and focused regression tests are prepared separately from a production rollout.

Validation: 19 tests passed across the new readiness/recovery cases and existing profile-upgrade regressions. Includes the actual status endpoint body returning failed for a 3-ready/1-terminal-job fixture, owner/course/generation isolation, expired versus active leases, future retry deferral, concurrent wake coalescing and preservation of the queued job/checkpoint identity. These are local SQLite-backed regressions, not a production recovery observation or PostgreSQL load test.
