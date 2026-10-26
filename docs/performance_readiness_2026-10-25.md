# Dental AI performance and capacity review — 2026-10-25

Follow-up: `voice_http_queue_2026-10-25.md` documents the subsequently added bounded HTTP admission queue. Raw-core burst results below record the earlier baseline and bypass that queue.

## Current assessment

60,000 registered users is a population target, not a verified concurrency level.
This change removes one demonstrated server event-loop stall. It does not make
production ready for 60,000 simultaneous users or certify end-to-end latency.

## Evidence from connected services

- Render service `srv-daeb9d740ujc73ei7gmg` is one free web instance, started with
  one `uvicorn app.main:app` process. No paid upgrade or scaling change was made.
- Latest live source remains `c6ab6f129eb23f9f7db328332f22bb87175300ba`.
  Later builds for academic partial readiness and AES PDF support are failed;
  earlier investigation identified exhausted build minutes. PR #215 is not live.
- A query explicitly scoped from 2026-10-24 11:28 UTC through 2026-10-25 14:00 UTC
  returned no error-level logs. This is an absence of matching logs, not proof
  that every request succeeded. Older two-connection pool errors precede this
  interval and are not treated as evidence that the pool fix failed.
- Render returned sparse memory samples (159,408,130–183,779,330 bytes) and no
  usable CPU, HTTP latency or request-count series in that query. Therefore no
  production p95 latency, error rate or requests-per-second is reported.
- PostHog project 318683 still reports `ingested_event: false` and incomplete
  snippet onboarding. Its preparation dashboard is not live site telemetry.
- Figma test board tracks QA status, not actual rendered production performance.

## Reproduced defect and repair

The async voice WebSocket handler entered and exited the synchronous provider
reservation directly. That reservation executes database transactions and can
wait for a lease-renewal thread to stop. Such work on the event loop delays
unrelated sockets and async HTTP work in the same server process.

Four regression scenarios first failed against the existing handler: delayed
lease acquisition/release SQL, each with normal completion or provider failure.
Tests use the real reservation manager and a local SQLite database; a 150 ms
artificial query delay deterministically checks whether another coroutine can
continue. No production load or real provider request is generated.

`_provider_slot` now offloads entry and exit to worker threads. Acquisition is
shielded so a cancelled socket waits for its worker to finish and registers
cleanup. Exit uses its own thread capacity limiter so saturated request workers
cannot prevent lease cleanup. Existing provider budget, four-slot admission,
origin, consent and per-user checks are unchanged.

Seven scenarios cover success, provider failure, cancellation while streaming,
and cancellation during acquisition. They verify event-loop progress, closed
socket, per-user cleanup and removal of the actual database lease.

Review caveat: repeated cancellation during the acquisition cleanup wait is not
covered. Independent review reproduced reliance on generator finalization for
that edge, but no current production lease leak was demonstrated. Do not claim
arbitrary repeated cancellation has been verified.

## Local burst benchmark

The existing benchmark still simulated Gemini's response after extraction moved
to Claude. It failed locally with missing Claude configuration. The harness now
simulates the current forced `clinical_extract` tool result and supplies only a
synthetic Claude key. An offline regression test exercises the real extraction
and normalizers. No model understanding is evaluated.

Raw results: `docs/voice_local_capacity_2026-10-25.json`.

| Submitted concurrency | Requests | Accepted | Busy response | Peak simulated provider calls |
| --- | ---: | ---: | ---: | ---: |
| 1 | 100 | 100 | 0 | 1 |
| 10 | 100 | 2 | 98 | 2 |
| 50 | 100 | 2 | 98 | 2 |

This is an immediate burst of tasks with an artificial 20 ms provider delay,
not sustained arrival-rate traffic. Rejected tasks finish quickly and allow
more submissions before the initial two calls complete. These acceptance ratios
must not be extrapolated to normal users, real Claude latency or Render capacity.
The result does demonstrate that the existing two-slot extraction guard rejects
bursts rather than queuing them. Raising it blindly would transfer contention to
the provider budget/database and is not a capacity solution.

## Remaining capacity gates

1. Define peak active users, requests per active user and simultaneous voice
   sessions separately from 60,000 total accounts. For illustration only, 600
   active users making one request every ten seconds produce 60 requests/second;
   this is not an observed usage model.
2. Add production latency/error and queue metrics without transcript, patient,
   medication, uploaded-document contents, or session replay capture. Verify
   ingestion before using a dashboard to make capacity claims.
3. Use durable bounded background jobs for longer AI work, with fair admission,
   visible waiting/processing/retry states, cancellation and duplicate-save
   protection. Preserve the existing provider budgets; do not silently add
   retries that multiply billable calls.
4. Run isolated staging tests against PostgreSQL and representative external
   provider latency at gradually increasing concurrency. Measure p50/p95/p99,
   event-loop lag, pool wait/timeouts, worker/queue depth, accepted/completed
   requests and resource use. Stop on saturation; do not flood the live free
   service with a 60,000-user test.
5. Budget web-instance and worker counts against total PostgreSQL connection
   limits and provider quotas before scaling. The current web pool has four
   connections per process and router pools two; multiplying instances also
   multiplies pool demand.
6. Exercise mobile keyboard, long evidence/source text, patient selection,
   microphone interruption/resume, final evaluation, approved tooth chart,
   appointment and record save in a real browser. The unreleased mobile summary
   remains visually unverified because preview access was rejected; the Figma
   board is not a substitute for app screenshots.
7. Resolve build/CI billing quotas before a single reviewed release. No repeated
   build retry, billing change, new cloud resource or production deploy was
   performed for this review.

## Validation

Full locally available Python and Node suites are run with this change. They
use the partial repository mirror, synthetic data and local databases. They
cannot establish production capacity, real audio transcription accuracy, mobile
visual fidelity, or a passing GitHub CI run. See the PR validation entry for the
final counts and commands.
