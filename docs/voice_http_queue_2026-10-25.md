# Voice HTTP admission repair — 25 October 2026

## Cause and observed failure

The extraction/final-review guard allows two operations per process and rejects
all new calls immediately while occupied. This protected provider capacity but
turned ordinary short bursts into manual retry errors. An actual local ASGI
HTTP test with eight distinct synthetic accounts reproduced two successes and
six HTTP 422 failures before the repair.

## Implementation choice

Use bounded asynchronous admission above the existing core/provider guards:

- Two running HTTP operations and at most eight FIFO waiters per process.
- Thirty seconds maximum queue waiting, then an explicit HTTP 429 with
  `VOICE_QUEUE_BUSY`, `Retry-After: 2`, and a message that the draft is preserved.
- One outstanding operation per account across upload, waiting and processing.
  This prevents multiple tabs from submitting overlapping voice work.
- Text, audio, final review and optional clinical review use the same processing
  queue. Authentication and consent remain before admission. Authentication and
  provider work run in threads, not on the event loop. No database transaction
  remains open while waiting for admission.
- Audio has a separate two-holder, zero-wait upload budget, held through its
  processing phase so at most two complete audio bodies are retained. Existing
  body byte limits remain. Body reads have a 30-second deadline; incomplete
  uploads return HTTP 408 `VOICE_UPLOAD_TIMEOUT` without calling a provider.
- A cancelled queued request returns its place, including a cancellation/grant
  race. A disconnected request does not start provider work after admission.
  If a worker is already running, repeated request cancellation does not free
  its processing permit early; it remains bounded until the worker finishes.
- No automatic billable retry, new model call, stored transcript, database
  migration, external queue resource or paid cloud service was introduced.
  UI status messages mention that processing may wait briefly during demand.

Alternatives considered: raising the core semaphore would transfer contention
to the global provider budget/database. A durable job queue would require a
separate privacy, temporary-content and recovery design because existing job
payloads deliberately contain identifiers rather than voice text or audio.
Bounded in-memory admission is the chosen short-burst repair. It does not survive
a process restart, and is not a replacement for durable background work or
capacity planning at high sustained traffic.

## Regression evidence

The eight-account HTTP test now completes eight requests successfully, with
exactly eight simulated provider calls and peak provider concurrency no greater
than two. Fifteen queue tests additionally cover FIFO, queue overflow, duplicate
account, timeout, provider failure, queued cancellation, cancellation just after
a grant, repeated in-flight cancellation, disconnected requests and all four
HTTP overload responses.

Independent review found two additional cases, both reproduced and fixed:

1. Two stalled audio uploads initially consumed both processing slots. Separating
   upload admission now allows an unrelated text request to complete while both
   uploads are stalled. Upload timeouts also release upload/account resources.
2. Separate upload admission initially allowed a second operation by the same
   account. A request-level account claim now covers the entire lifecycle. The
   corresponding concurrent-upload/text test rejects the second operation before
   any provider work.

Final independent review passed all fifteen queue tests and reported no remaining
important findings in this change.

## Offline HTTP burst measurements

Run from the project root:

```sh
PYTHONPATH=. python scripts/benchmark_voice_http_queue.py --output docs/voice_http_queue_capacity_2026-10-25.json
```

The benchmark executes actual ASGI routing, admission, extraction and validation,
with synthetic authentication, fixed model output and a 20 ms artificial provider
delay. It sends no real provider or production requests. Raw timings are in the
JSON report; no latency value should be treated as production performance.

At submitted concurrency ten, all 100 requests completed without manual retries,
while provider concurrency stayed at two. At concurrency fifty, the bounded queue
rejects requests beyond its two running/eight waiting envelope rather than holding
unbounded work. Rejected requests do not generate provider calls.

The earlier raw-core benchmark in `voice_local_capacity_2026-10-25.json` remains a
valid fail-fast baseline; it bypasses HTTP admission and is not evidence that the
new HTTP queue is absent.

## Remaining limits

This is per-process admission. Shared provider leases still enforce cross-process
budgets and may reject work when other features occupy provider capacity. Adding
processes multiplies local queue/pool resources and needs a shared capacity plan.
The queue does not raise actual AI throughput, certify 60,000 simultaneous users,
verify PostgreSQL under load, or resolve exhausted deployment/CI build quotas.
No production merge or deployment was performed. Actual mobile visual and real
microphone verification remain pending.

## Final local validation

- `python -m pytest -q`: 233 passed, with 40 pre-existing dependency deprecation
  warnings (Starlette/httpx, AnyIO alias and SQLite datetime adapter).
- All ten Node `.cjs` test files passed; `node --check app/static/voice-exam.js`
  passed.
- Offline ASGI benchmark completed: concurrency 1 and 10 each completed 100/100;
  concurrency 50 completed 10/100 and returned bounded queue-busy responses for
  90/100, with exactly one simulated provider call per completed request.
- These are all tests available in the local partial repository mirror, not a
  passing GitHub CI claim or real production capacity/audio/visual verification.
