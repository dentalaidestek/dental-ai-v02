# Academic AI capacity audit — 17 October 2026

## Verified production state

- Render service `dental-ai-v02`, one free instance. Metrics for 18:00–19:04 UTC report a CPU limit of 0.15 and a memory limit of 536,870,900 bytes (~512 MiB). The latest sample shows ~191 MB memory use. Low observed idle CPU is not capacity evidence.
- Deploy `dep-db9rr0qvcj2c739ktmn0`, commit `5b7760f`, became live at 18:27:01 UTC. PR #137 (long-answer PDF) remains unmerged and is not part of this audit's production baseline.
- Runtime settings differ from `render.yaml`: actual service is free, uses `pip install -r requirements.txt`, and has no configured HTTP health-check path. The Blueprint specifies a paid starter instance, a different lockfile, migrations and `/readyz`. The existence of that file does not establish the running configuration.
- HTTP count/latency series were empty for this resource/time window. No live p95 request-latency claim is made.
- Existing provider timing logs show two successful quick summaries at 12,064 and 15,835 ms, with 44,632 and 42,617 input tokens, respectively. Another request used a 10,301 ms planner, then 29,270 ms generation and stopped at MAX_TOKENS (56,613 input / 7,000 output tokens). These are historical provider-stage timings, not new test questions or end-to-end benchmarks.

## Changes in this branch

1. **Course listing:** replace per-course material-body queries with one owned grouped count. Fetch 51 courses for a 50-course page, with an owner-checked keyset cursor, stable update-time/id ordering and links to older courses. No cross-owner counts.
2. **Chat opening:** select the latest 40 messages in SQL, then reverse only those rows for chronological display. Count materials in SQL rather than materializing them solely to get their length.
3. **Course detail:** use SQL COUNT for the message count; do not fetch old answer bodies.
4. **AI admission:** cap active academic HTTP requests before planning/retrieval, including native mobile. Default two per process, additionally bounded by the general HTTP limit. Excess gets 503 and Retry-After; there is no hidden waiting queue or extra model call. Existing provider admission still applies.
5. **Upload independence:** a question's small multipart text form no longer takes a file-upload slot. Those routes have a separate 64 KiB body ceiling, including streamed/chunked bodies; real uploads retain their existing slots and byte limits. Numeric path aliases also enter the same admission lane.
6. **Browser rendering:** coalesce deltas at 100 ms intervals rather than repeatedly rebuilding the entire growing answer per fragment. Flush final text and cancel deferred paints on completion/error so a PDF card cannot be overwritten.

The admission cap is a protection boundary, **not** successful service for all incoming users. It is process-local; multiple replicas multiply its capacity. The existing provider reservation is shared through the database. A durable, fair academic queue is still needed for sustained traffic.

## Reproducible local evidence

Synthetic SQLite dataset: 60,000 distinct owner IDs, 60,200 courses, and 5,000 messages on the active course. Auth, readiness and template rendering are stubbed; the actual route bodies and SQLModel queries execute. This is neither a PostgreSQL load test nor 60,000 simultaneous clients.

| Route | Before | After | Median local elapsed, before → after |
| --- | --- | --- | --- |
| Course list, owner with 201 courses | 202 SQL queries, 201 cards | 2 SQL queries, 50 cards plus cursor | 43.942 → 1.053 ms |
| Chat opening, 5,000-message history | 5,000 message objects loaded, 40 displayed | 40 message objects loaded/displayed | 45.228 → 1.012 ms |
| Course detail message count | 5,000 message objects loaded | 0 message objects loaded | 62.579 → 3.201 ms |

Five iterations per route, warm local process. The row/query reductions are the primary evidence; these latencies must not be presented as production speedups.

- Seven targeted Python tests cover owned pagination, latest-message selection, body-free counting, a 1,000-request burst while two AI requests are held open, normal navigation and upload availability, shared web/mobile admission, cancellation cleanup and body limits.
- JavaScript harness executes the real rendering closure. A single burst of 1,000 deltas produces one final text paint/Markdown pass, or one PDF-progress paint with no Markdown pass. Real streaming may paint at most once per scheduled 100 ms interval, plus final completion.
- Both modified Jinja templates compile and the embedded browser script passes Node syntax checking.
- Python compilation passes. Existing full-application boundary tests could not collect in the available environment because `argon2` is missing; they are not claimed passing.

Commands:

```bash
python -m pytest -q tests/test_academic_capacity.py
node tests/browser/academic_stream_render.cjs
python scripts/benchmark_academic_capacity.py --baseline /path/to/pre-change-main.py
```

## Remaining bottlenecks and required next evidence

1. **Production hardware:** one free instance with the measured limits does not establish a 60k-user service. Determine peak active users, concurrent AI demand, request arrival rate, accepted error rate and latency objectives before sizing. No plan, replica, database or billing settings were changed.
2. **Durable academic execution:** question generation currently lives in the HTTP request/stream. The general durable clinical-job system does not automatically make academic work durable. Add idempotent jobs, owner isolation, fair scheduling, cancellation/deadlines, retry budgets and reconnect/replay before promising completion after disconnection or restart.
3. **Model throughput and cost:** course-wide calls read tens of thousands of tokens. Provider concurrency defaults to four; raising it without provider quota, memory and database measurements can worsen errors. Validate repeated presets with versioned, owner-isolated reusable source context rather than another paid summarization stage.
4. **Database contention:** configured default web pool is two connections with no overflow and a five-second timeout; actual production environment overrides were not read. These changes shorten reads, but do not prove absence of contention. Measure live connection use, slow queries and index plans on PostgreSQL.
5. **Sockets:** source default global socket bound is 2,000 per process and four per owner. This is separate from registered users. Capacity, proxy limits and memory per connection still need measurement.
6. **CPU/RAM overlap:** rendering PDFs, rasterizing originals, colocated indexing and large prompts can overlap on the web process. Separate durable worker execution from navigation and measure memory peaks under mixed loads. The existing shared two-thread source pool has no independent finite pending queue; the new HTTP gate bounds academic requests entering it in this process but is not a global worker queue.
7. **Legacy `/ai/ask`:** source still loads full patient/analysis/clinical-record collections for dashboard rendering after a model call. It needs its own scoped pagination/count and access review; it was not changed or exercised here. Do not assume the whole site is bounded by the academic fixes.

## Live question testing blocker

The user requested questions against the existing system. The signed-in browser reached the course list, but automatic approval review rejected selecting “Perio didem” because accessing private course notes was not authorized by naming/approving that course. No workaround or private-note query was attempted. Newly prepared live scenarios are marked NOT_RUN pending explicit approval for Perio didem and Orto. Historical logs and local synthetic tests are not substituted for those live responses.

No production merge, deploy, plan change or stress flood was performed.
