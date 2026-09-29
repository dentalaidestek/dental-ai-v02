# Dental AI: deployment and blueprint verification

## Scope and capacity

This patch preserves the dental corpus, prompts, OCR/chunking rules, inference models, thresholds and evidence scoring. It changes execution, storage and publication boundaries. Existing public routes remain available; three authenticated job-control routes are added.

**60,000 registered users is a planning target, not a verified concurrency or latency claim.** Capacity depends on simultaneous sessions, requests per second, PDF size/page count, inference latency, provider quotas and the monthly budget. The limits below deliberately reject excess work or queue it. One small Render instance cannot promise 60,000 simultaneous OCR/inference requests.

The earlier **1.115 ms** lexical result was a local reference benchmark. The implemented cache subsequently measured **0.265 ms median versus 24.566 ms** on the same synthetic search workload, with 40 exact search-output comparisons and ten specialty-context comparisons. These numbers exclude network, embeddings, generation and inference. They are not response-time guarantees.

## Blueprint cross-reference

“Covered” means implemented with the listed checks, not certified under production load. Mechanical model/router extraction was explicitly marked “later” in the original blueprint; those declarations remain to preserve schema and route contracts.

| Blueprint component | Implementation | Evidence / practical boundary |
| --- | --- | --- |
| Async HTTP/auth/maintenance boundaries | `execution.py`, synchronous offloaded routes, `settings_cache.py` | ASGI tests; flags cached two seconds, identities not globally cached. |
| DB pools and role isolation | `database.py`, indexer engine, router engine | Pool saturation/recovery checked on PostgreSQL; no overflow; five-second acquisition timeout. Pools multiply per process. |
| Short academic transactions | `study_rag.py`, `study_retrieval_v2.py`, ask/stream handlers | Embedding, attachment download and generation outside SQL; source versions and owner checked before publication. |
| Clinical orchestration | `work_jobs.py`, `work_worker.py`, main clinical functions | Durable queue, immutable result blobs, guarded DB result pointer/status commit; no blob I/O transaction in regression test. |
| Realtime/WebSockets | `realtime_io.py`, thread-based LISTEN, socket helpers, case-room catchup | SQL/auth off-loop, serialized bounded writes, real PostgreSQL notification/shutdown test. Explicit event IDs cover reversed commit order. Reconnect/overflow requests durable resync. |
| Cross-instance chat | Existing event log plus case HTTP catchup | Global MESSAGE_CREATED now triggers room catchup even with an open room socket; 500-row pages and coalesced continuation. Process hubs are delivery caches only. |
| Durable application jobs | `work_jobs.py` | Dedupe, one running job per resource, bounded global/owner backlog, expiring leases, heartbeat, source/owner fencing, bounded retries, cancellation, 30-day history cleanup. PostgreSQL parallel claims tested. |
| Pending/error/retry UI | `/jobs/{id}`, POST retry/cancel; `work_pending.html`, viewers | Authorized endpoints, 202 stays pending, polling backs off; failed vision jobs expose an explicit retry form. Cancellation fences publication; it cannot undo a provider call already in flight. |
| Lexical RAG footprint | `dental_rag/rag.py` | Immutable process cache; all evidence cards retained; no generated corpus copies/index downloads. Restart after corpus changes. |
| Academic V1 indexing | Disabled after V2 cutover | `STUDY_ACADEMIC_V2_ONLY=1` prevents new V1 jobs and cancels previously queued V1 jobs. The dormant implementation remains for one-release rollback safety. |
| Academic V2 indexing | `study_index_jobs.py`, `study_index_worker.py` | Short checkpoints, heartbeat during external work, fenced post-call writes, bounded page/chunk slices and queue admission. Existing lease/publication regressions pass. |
| Fair background scheduling | `study_index_worker_main.py`, `work_worker.py` | MIXED alternates normal/OCR; erasure drains during continuous work; bounded legacy backfill continues periodically. |
| Colocated indexer | Existing `study_colocated_worker.py` | Explicit optional subprocess supervisor. Disable when an external indexer is configured. Shares web RAM/CPU. |
| Pooled provider transport | `http_transport.py`, clinical/academic/modality adapters | Four pooled connections per host, eight host pools, bounded waits, original read timeouts; no new automatic HTTP retry layer. |
| Shared API request budgets | `provider_budget.py` | PostgreSQL slots/counters, account-wide wildcard request budgets and expiring heartbeats. Cross-process concurrency test passes; legacy router observations are not authoritative global billing totals. |
| Provider batching | Existing adapter semantics preserved | No speculative batching: model/task-specific vector equivalence has not been established with live providers. Serial calls checkpoint individually. |
| Vision snapshot reuse | `vision_llm_context.py`, persisted asset snapshots | Successful-only cache, defensive copies, inference revision, batches of four; partial failures retry missing assets. Clinical routing reuses structured snapshots. |
| Vision service admission | `vision_service/app.py`, `request_limits.py` | One local model request at a time; bounded per-image/body sizes and temp cleanup; diagnostic endpoints disabled by default. |
| TVEM shared model residency | `tvem_client.py` | Load/detect/unload serialized through a shared PostgreSQL slot. All clients using that TVEM instance must share this coordinator. |
| R2 handlers/cache | `object_storage.py`, `object_cache.py` | Bounded streaming download, disk budget, reader pins across processes, immutable cache generations, response-lifetime cleanup. Failed remote delete propagates; failed HEAD is not “object missing”. |
| Erasure/recovery | `study_deletion_worker.py` | Atomic reclaimable claim, attempts fence, remote I/O outside transaction, retry on failure; successful academic deletion does not depend on web-process lifetime. |
| Result garbage collection | `WorkGarbage` | Allocate cleanup before result upload; delayed cleanup checks live result pointers, including ambiguous-commit recovery. Existing uploaded source keys remain authoritative. |
| Upload pressure | `request_limits.py`, `upload_io.py` | Two multipart requests/process, aggregate byte counting including chunked bodies, 25 MiB clinical image copy cap, no partial file on rejected copy. |
| Deadline/reminder workers | Existing queues plus offloaded scheduling/listener | Business transitions retained; startup migration removed from dedicated worker; existing lifecycle/transaction tests pass. |
| Observability | Existing study/xray traces plus job IDs and worker duration | Structured safe clinical timing/attempt/token fields on stdout. Diagnostic rings remain bounded and instance-local. No new public metrics endpoint exposing case data. |
| Controlled migrations | `python -m app.migrate` | Revision 2; serialized release lock, existing baseline DDL retained, immutable result pointer columns, queue/provider tables and cursor indexes. Fresh/upgrade/repeat checks on PostgreSQL. |
| Dependencies / CI | `requirements-web.lock`, `.github/workflows/vision48-ci.yml`, application/PostgreSQL tests | Verified Linux Python3.12 dependency closure pinned; the workflow runs the full application regression suite in addition to the existing vision/model inspections. Torch/model weights stay out of web install. |
| Later model/router extraction | Existing main declarations retained | Route inventory shows no removed contracts; avoids speculative schema/module churn. Queue, cache, transport, admission and listener logic are extracted. |
| Dental/vision/OCR logic | Existing AI engine, motors, source cards, specialty rules, chunking and OCR | Existing contracts and OCR tests pass. Live clinical accuracy and GPU inference still need representative authorized fixtures. |

## Render processes

`render.yaml` is the checked-in deployment contract for the existing free web
service only. It deliberately declares no Render background workers, so applying
it cannot add paid worker services. Automatic deploys and previews are disabled.
Run the application and Academic V2 consumers on the already available external
free worker host. Do not create a second `dental-ai-v02` web service accidentally:
link/adopt the existing service when applying the Blueprint, or copy the
verified commands and variables to the existing service manually. Supplying
secret values and applying the Blueprint are explicit release operations, not
part of repository verification.

Use the same commit and configuration on all consumers. Configure Python **3.12.14**.

Build web and application/index workers:

```sh
pip install -r requirements-web.lock
```

Before starting this revision, run once with the target database:

```sh
python -m app.migrate
```

Use a controlled release/pre-deploy step where available, or run the command in an operations shell before switching services. Migration retains existing idempotent baseline DDL, which can lock large tables; schedule the release accordingly. Production web/worker processes check the revision instead of independently performing schema upgrades. Do not enable `DENTAL_MIGRATE_ON_STARTUP` on every replica.

| Service | Start command | Port / notes |
| --- | --- | --- |
| Web | `uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1` | Render HTTP port; `/readyz` checks DB, `/healthz` checks process. |
| Application consumer | `python -m app.work_worker` | Existing external free host; vision, preliminary/final AI and erasure. V1 jobs are cancelled in V2-only mode. |
| Academic V2 consumer | `python -m app.study_index_worker_main` | Existing external free host; no HTTP port; `STUDY_V2_RESOURCE_CLASS=MIXED`. |
| Optional deadline consumer | `python -m app.deadline_worker` | Set `DENTALAI_DEADLINE_EXECUTION=external` on web only when this is running. Program reminders remain embedded. |
| Optional local inference | Existing GPU/model deployment, or `uvicorn vision_service.app:app --host 0.0.0.0 --port "$PORT" --workers 1` | Separate model environment; install `vision_service/requirements.txt` and existing weights. Do not install GPU stacks in the web image. |

Keep one web process initially. Add measured replicas rather than blindly multiplying Uvicorn workers. Inference services need their own measured memory/model capacity.

### Required shared configuration

Set secrets in Render's environment configuration; do not commit values:

- `DATABASE_URL`: same internal PostgreSQL database for web, workers and quota coordination. Production refuses missing database configuration.
- `R2_ENABLED=1`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`: same private bucket on each service. Keep stored `uploads/...` keys intact when migrating existing files.
- Existing `GEMINI_API_KEY`, clinical model and academic provider keys/model settings. Preserve the selected models and OCR languages.
- `DENTAL_VISION_MODAL_URL`: existing API base implementing `POST /infer?modality=...` with multipart field `image`. This is **not** interchangeable with the standalone vision service's `/analyze`, `/analyze-intraoral`, `/analyze-bitewing`, `/analyze-periapical` endpoints, which require `X-Vision-Key` / `DENTAL_VISION_API_KEY`. Keep the current contract or provide a compatible external adapter.
- Increment `DENTAL_INFERENCE_REVISION` when inference behavior/weights change, on every service. Restart consumers when changing corpus/model/provider configuration.

Conservative starting limits (tune from measurements):

```dotenv
DENTAL_WORK_EXECUTION=external
STUDY_ACADEMIC_V2_COLOCATED_WORKER=0
STUDY_ACADEMIC_V2_INDEXING=1
STUDY_ACADEMIC_V2_READS=1
STUDY_ACADEMIC_V2_STREAMING=1
STUDY_ACADEMIC_V2_ONLY=1
DENTAL_WEB_DB_POOL_SIZE=2
DENTAL_ROUTER_DB_POOL_SIZE=2
DENTAL_MAX_HTTP_REQUESTS=8
DENTAL_MAX_UPLOADS=1
DENTAL_MAX_REQUEST_BYTES=52428800
DENTAL_MAX_SOCKETS=2000
DENTAL_MAX_PENDING_JOBS=1000
STUDY_MAX_PENDING_INDEX_JOBS=1000
DENTAL_PROVIDER_MAX_INFLIGHT=4
R2_CACHE_DIR=/tmp/dental-r2-cache
R2_CACHE_MAX_BYTES=268435456
STUDY_V2_DB_POOL_SIZE=2
STUDY_V2_RESOURCE_CLASS=MIXED
STUDY_V2_OCR_BATCH_PAGES=1
STUDY_V2_EMBED_BATCH_CHUNKS=4
STUDY_V2_RECYCLE_RSS_MB=384
DENTAL_WORKER_RECYCLE_RSS_MB=420
STUDY_V1_SHADOW_INDEXING=0
DENTAL_INFERENCE_REVISION=1
DENTAL_RUNTIME_DIAGNOSTICS=0
```

The two RSS thresholds apply only at durable job/slice boundaries. A worker
first closes its active session, collects cyclic objects, asks glibc to release
unused arenas, and only then re-execs itself if resident memory is still over
the configured threshold. No worker is recycled while it owns uncheckpointed
work. Set either value to `0` to disable recycling on a larger measured plan.

`STUDY_ROUTER_REQUEST_BUDGETS_JSON` accepts verified account limits, for example `{"gemini:*":{"day":1000}}` **only if 1000 is your chosen actual budget**. Request counts are conservative reservations, not token/dollar accounting. Configure provider-side spending limits too. Concurrency is global only when services use the same database. Pool size is per engine/process; include the dedicated LISTEN connection, router engines and workers in the DB connection budget.

Cut over in two phases. First run the external free Academic consumer with
`STUDY_ACADEMIC_V2_INDEXING=1` while production reads remain unchanged. Wait
until every non-deleted material has `index_status='READY'` and a non-null
`active_index_version`. Then deploy the web configuration with reads, streaming
and `STUDY_ACADEMIC_V2_ONLY=1`. The V2-only flag requires indexing and reads,
prevents new V1 indexing, and makes the application consumer cancel old queued
`LEGACY_INDEX` work. Do not enable the V2-only web configuration before this
readiness query returns zero:

```sql
SELECT count(*) AS pending_v2_materials
FROM studymaterial
WHERE deleted_at IS NULL
  AND (index_status <> 'READY' OR active_index_version IS NULL);
```

For a single-container test, `DENTAL_WORK_EXECUTION=embedded` runs one application consumer in a thread; `STUDY_ACADEMIC_V2_COLOCATED_WORKER=1` starts the existing indexer subprocess. This saves a service but shares RAM/CPU and availability with web. Durable jobs survive process restarts; running provider requests can be repeated after a crash, while stale result publication is fenced.

## Replacing tmux and tracing traffic

1. Identify the current tmux commands, machine, bound interfaces/ports and endpoint contracts. Supply those commands with secret values redacted, plus Render service names/regions/instance sizes and any reverse proxy routing.
2. Move consumers to the managed worker commands above. Verify DB/R2/provider connectivity, stop the corresponding tmux consumers, then enable traffic. Avoid two independently configured supervisors for the same intended allocation.
3. If GPU inference stays on the other machine, expose its existing authenticated HTTPS endpoint through your chosen reverse proxy/private network. Render cannot reach that machine's `localhost`, and a tmux session does not bridge networks. Do not point the Modal `/infer` client directly at a different `/analyze` contract.
4. Verify `/readyz`, upload a synthetic image/PDF, inspect the returned job ID, and follow `work.finished`, `xray.event` and `[STUDY_TRACE]` logs across services. No customer data or production traffic was inspected for this patch.
5. To monitor live traffic, provide authorized read-only Render logs/metrics, database connection limits and aggregate queue timings; provider quota/latency/error metrics; R2 operation counts; p95/p99 HTTP latency, event-loop lag, worker RSS, oldest queued job and 429/503 rates. Do not paste keys, tokens or patient content.

Useful aggregate PostgreSQL checks:

```sql
SELECT kind, status, count(*) AS jobs,
       max(now() - created_at) AS oldest_age
FROM workjob GROUP BY kind, status;
SELECT stage, status, count(*) FROM studyindexjob GROUP BY stage, status;
SELECT status, count(*) FROM studydeletionjob GROUP BY status;
SELECT application_name, state, wait_event_type, count(*)
FROM pg_stat_activity WHERE datname=current_database()
GROUP BY application_name, state, wait_event_type;
```

## Verification and release boundaries

The full local suite passed. Tests cover leases, queue admission, stale publication, upload/provider session release, cache pressure, storage failure, realtime replay and existing dental contracts. The CI workflow runs the same application suite alongside the existing vision/model inspections. PostgreSQL-specific tests still require their configured integration database and skip safely when it is absent.

The bundled S3 emulator verified SDK upload/head/download/delete, upload cleanup and pinned readers for a small object. Its `CreateMultipartUpload` endpoint is unsupported; **real R2 multipart remains a required deployment smoke check**. The emulator catalog does not include Gemini/Modal, so provider inference quality, cancellation behavior and rate limits were not simulated as verified live behavior.

Before sending production traffic, use an isolated Render database/bucket and representative authorized cases. Verify a worker restart during inference, stale/deleted-source rejection, large PDF/OCR memory, R2 multipart upload, multi-instance chat, and provider quality parity. Measure the intended concurrency and budget. Schema rollback should retain the additive columns/tables and drain/stop consumers before rolling application code back; immutable result pointers are a new read contract, so older code will not display newly generated result files.
