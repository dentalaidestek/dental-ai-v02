# Render optimization branch

## Release status

This branch improves execution boundaries and resource use without changing dental prompts, model thresholds, retrieval scoring, or source cards. It is a **staging candidate**, not a certification of production capacity or clinical accuracy. Run synthetic cases on an isolated Render service/database before switching production traffic.

## What changed

| File | Change |
| --- | --- |
| `app/execution.py`, `app/main.py` | Execute synchronous HTTP handler work in AnyIO worker threads; return async request/broadcast operations to the owning event loop. Startup and maintenance queries also run off the event loop. Wakeups tolerate lifespan restarts and cross-thread signals. |
| `app/database.py`, `app/study_router_state.py` | PostgreSQL pools default to two connections per engine, no overflow, five-second pool acquisition timeout. Separate web/router settings. |
| `app/main.py` | Fetch only eight recent history rows; release the academic request's DB connection before query embedding and answer generation. Recheck course ownership/existence before saving the answer. Add `/healthz` and `/readyz`. |
| `dental_rag/rag.py` | Cache the prepared lexical corpus once per process, preserving existing ranking and tie order. Restart after changing source cards. |
| `app/http_transport.py`, provider adapters | Reuse up to four connections per provider host, bounded pool wait/connect timeouts, existing read timeouts and retry policies. No added transport retries. Streaming errors retain urllib error handling. Provider endpoints must be canonical; redirects are rejected. |
| `app/vision_llm_context.py` | Cache successful inference only; return independent copies; include inference revision in the process cache key. |
| `vision_service/app.py` | Synchronous inference endpoints run in FastAPI's thread pool. Admit one local inference at a time, return 503/Retry-After on overload, limit each saved image to 25 MiB, clean temporary files after success/error. Diagnostics require explicit enablement. |
| `app/study_index_worker_main.py` | Alternate NORMAL and OCR_HEAVY work in MIXED mode so OCR is serviced under sustained normal backlog. |
| `app/study_v2_service.py` | Stop V1 indexing on new uploads when V2 reads are enabled unless explicit shadow indexing is requested. Reject V2 reads without V2 indexing at startup. |

## Web service

Use Python **3.12.14** (`.python-version`). Build:

```sh
pip install -r requirements.txt
```

Start:

```sh
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
```

Use `/readyz` for Render's health check; `/healthz` is lightweight process liveness. Supply Render's internal PostgreSQL `DATABASE_URL`. Do not use SQLite on an ephemeral web filesystem. Keep one Uvicorn worker initially: each additional process multiplies pools, caches and embedded schedulers.

Settings introduced by this patch:

```dotenv
DENTAL_WEB_DB_POOL_SIZE=2
DENTAL_ROUTER_DB_POOL_SIZE=2
STUDY_V1_SHADOW_INDEXING=0
DENTAL_INFERENCE_REVISION=1
VISION_MAX_IMAGE_BYTES=26214400
DENTAL_RUNTIME_DIAGNOSTICS=0
```

Pools are per process/engine, not a global database limit. Size against PostgreSQL's connection allowance, accounting for the indexer, event listener, and other services. Pool timeout failures require observing held transactions; increasing the pool alone is not a throughput fix.

## Replace tmux indexing with a managed process

A tmux session on another machine is not a Render process supervisor. Choose **one** of these topologies:

1. Separate Render background worker (preferred for isolation): use the same branch, Python version and build command, and start `python -m app.study_index_worker_main`. Configure the same PostgreSQL, object storage and academic provider settings. No HTTP port is required. On the web service set `STUDY_ACADEMIC_V2_COLOCATED_WORKER=0`.
2. Single-container option: set `STUDY_ACADEMIC_V2_COLOCATED_WORKER=1` on the web service. The existing lifecycle supervisor starts the indexer subprocess. It shares web memory/CPU and stops when the web service stops; this does not provide independent worker availability.

For either topology:

```dotenv
STUDY_ACADEMIC_V2_INDEXING=1
STUDY_V2_RESOURCE_CLASS=MIXED
STUDY_V2_DB_POOL_SIZE=1
STUDY_V2_OCR_BATCH_PAGES=1
STUDY_V2_EMBED_BATCH_CHUNKS=4
```

Keep `STUDY_ACADEMIC_V2_READS=0` during migration. Once existing materials have READY active generations and sample answers pass review, set reads to `1` to stop the duplicate V1 upload indexing path. V2 reads also require indexing enabled. Streaming remains separately controlled by `STUDY_ACADEMIC_V2_STREAMING`. This patch does not automatically migrate or switch production data.

The existing consultation deadline executor can run as another background worker via `python -m app.deadline_worker`; only then set web `DENTALAI_DEADLINE_EXECUTION=external`. Otherwise retain the embedded executor. Program reminders remain embedded.

## Shared storage and provider routing

For separate services, enable the existing R2 integration and set `R2_ENABLED=1`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` on both services using Render secret settings. Existing local uploads must be migrated before moving workers; a path in the web filesystem is not visible to a separate worker. This patch does not delete existing uploads or introduce unsafe cache eviction.

Keep the current Modal inference base in `DENTAL_VISION_MODAL_URL` and its read timeout in `DENTAL_VISION_MODAL_TIMEOUT_SECONDS`. The caller appends `/infer`. The standalone vision app exposes `/analyze*`, **not** that protocol; do not substitute its URL for Modal's base URL.

If deploying standalone vision for compatible clients, install `vision_service/requirements.txt` from the repository root and start `uvicorn vision_service.app:app --host 0.0.0.0 --port "$PORT" --workers 1`. Set `DENTAL_VISION_API_KEY` and send `X-Vision-Key`. Model dependencies and weights belong on this service, not the web service. Each service needs its own capacity measurement.

## Verification and remaining limits

The branch includes synthetic ASGI, connection reuse, vision admission/cleanup, transient-failure cache, RAG cache, configuration, and academic DB-release/deletion tests. Existing clinical and OCR tests remain in the full suite. See the commit handoff for actual pass/failure results.

Remaining architectural work is explicit:

- Clinical preliminary/final analysis and legacy V1 indexing still use request execution or FastAPI BackgroundTasks. They are not durable across restarts. The existing durable V2 queue covers academic indexing only; no unfinished general-purpose queue is shipped.
- Thread offloading prevents event-loop blocking; it does not remove every held database transaction or bound every request backlog. Websocket SQL and portions of the PostgreSQL listener still use synchronous driver calls.
- Provider quotas and vision cache are process-local; simultaneous identical requests can still duplicate inference. Increasing replica count requires coordinated quota/admission design.
- The 25 MiB vision limit applies while copying an already parsed multipart upload. An ingress request-body limit is also needed to bound multipart spooling.
- Persisted vision snapshots retain their existing lifecycle; changing `DENTAL_INFERENCE_REVISION` invalidates the process cache, not stored snapshots.
- Live multi-user latency, real provider behavior, restart recovery, model accuracy and Render memory limits have not been certified by synthetic tests.

For staging, observe p95 request time, 429/503 rates, DB checkout waits, worker lease/retry counts, and RSS using synthetic dental cases. Do not log uploaded images, patient data, prompts or secrets. Compare retrieved sources and model output against the current deployment before increasing traffic. Roll back by selecting the previous branch/commit and restoring its feature flags; the patch adds no database tables or schema migration.

### Verification at publication

- Twelve optimization regression cases pass, including actual ASGI responsiveness and DB connection release during a simulated slow provider call.
- Forty clinical search outputs and ten specialty contexts exactly match the base commit. Local median search time: 24.566 ms before / 0.265 ms with the warm cache; this is a local microbenchmark, not Render end-to-end latency.
- PostgreSQL 16 pool check passes: two connections, no overflow, successful reuse after saturation.
- Application/test/training Python compilation and Git whitespace checks pass.
- All three CI remote checkpoint checks pass (pinned Liodon hash/classes, repository metadata, bone-loss/periapical ONNX inspection).
- The full suite still has ten pre-existing failures: two 3D viewer contracts, baseline notebook content contract, chat navigation cleanup contract, two consultation UI contracts, expert-support UI contract, and three realtime messaging/reminder contracts. These are not waived as production gates. The previously failing OCR fixture now uses the installed Amazon Linux font and passes.
- CodeRabbit review was attempted but is disabled for this task. No completed CodeRabbit review or production load test is claimed.

Reproduce the new checks with `python -m pytest -q tests/test_production_optimization.py` after installing root requirements plus pytest, httpx, NumPy and opencv-python-headless in a development environment. The remote checkpoint scripts additionally require onnx and huggingface_hub. Keep these test dependencies out of the web service's production build.
