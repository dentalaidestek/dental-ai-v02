# DentalAI — platform review and hardening, 17 October 2026

## Scope and evidence boundary

Baseline: production/main `5b7760fa5bd2874e4de45765a8e6f97541135be5`, with the staged capacity changes in PR #138 preserved. Production/main was not merged, deployed or reconfigured. PDF PR #137 remains separate.

The source inventory covers 91 app Python files and finds 255 route declarations; the imported application has 214 mounted routes, including framework/static entries. Compatibility routers contain declarations that are not mounted. An inventory is not proof that every route, role and device was exhaustively tested.

Source review and selected HTTP/SQL/concurrency tests cover authentication and recovery, profile/document access, patients, clinical uploads and queued analysis, academic retrieval/generation/indexing, messaging/replay, program retention, storage, administration and account erasure. All test records, images, provider failures and storage adapters are synthetic. No patient record, private clinical file, email, payment, production deletion or live load flood was used.

## Confirmed issues repaired in this follow-up

| ID | Trigger and previous behavior | Result and evidence |
| --- | --- | --- |
| S01 | Three native async upload handlers ran synchronous SQL, image validation and R2 work on the ASGI loop; two also called the worker-to-loop publication bridge from that loop. | Public async contracts now offload synchronous intake to AnyIO workers. A held storage call does not block an independent request; publication runs back on the ASGI loop. Three real handler/HTTP variants tested. |
| S02 | Those native uploads held a scarce database connection during slow image/storage work. | Authorization reads finish before storage. User/patient authorization is rechecked before publication. Account disablement during storage rejects all three upload variants. |
| S03 | Native analysis creation committed an ANALYZING row before validating/uploading the images or admitting its work job. A bad image, storage outage or full queue could leave a stuck analysis. | Stage files first; insert analysis, assets, work job and durable realtime event in one transaction after final authorization. Invalid image, failed storage and full queue leave no analysis/asset rows in tests. Failed pre-commit staging gets best-effort file cleanup. An already committed job remains successful when immediate socket delivery fails; the durable event remains available for replay. |
| S04 | Five native read paths could hold a DB connection while materializing remote media or reading a stored analysis result. | Snapshot authorized rows and fetch latest-job metadata, then close the session before storage I/O. Five parameterized owner/outsider tests verify no checked-out DB connections and private download cache headers; consultation downloads also receive private/no-store cache headers. |
| S05 | Browser mutation routes had no general Origin/Fetch-Metadata guard. Session authentication and SameSite alone were the existing boundaries. | Reject unrelated/null/malformed browser origins and cross-site Fetch Metadata before route mutation. Same origin, configured trusted origins and no-Origin native/server contracts remain supported. Real course-create tests show rejected origins cannot create rows. This supplements auth; it is not a claim of complete token-based CSRF or XSS protection. |
| S06 | `/ai/ask` rebuilt the dashboard using all matching patients/analyses and all ClinicalRecord objects, even though the dashboard only displays a few cards. It also copied raw exception text into template context. | Reuse the bounded dashboard response builder; no Analysis/ClinicalRecord loads, three Patient loads in the regression. Bound question length to 8,000 and use an allowlisted generic failure message. The existing provider still performs its direct-identifier redaction. |
| S07 | The patient directory fetched every patient and only searched the loaded DOM. | SQL keyset pages of 50 plus a lookahead, owner filter, server search across older rows, accessible next/first-page links, and a bounded realtime list. A 112-owned-record test verifies all pages without duplicates, exclusion of another owner and an older-row search hit. |
| S08 | Concurrent web/native password hashing could each allocate the configured Argon2 memory. | Share four non-waiting password-operation slots per process by default; excess gets 503/Retry-After. Argon2 parameters remain time_cost=2, memory_cost=19,456 KiB, parallelism=1. Four active operations have a theoretical Argon2 allocation envelope of 76 MiB, not a measured whole-process RSS bound. Success and failure both release slots. |
| S09 | Text-only authentication and legacy AI requests inherited a general upload-sized request body limit. | Apply a 64 KiB declared/streamed body bound to those text routes as well. Legacy AI shares academic admission. Real file uploads retain their separate upload limits. Regressions verify rejection before route processing. |

The initial PR #138 query and render fixes remain: owned course pagination/grouped counts, SQL LIMIT 40 chat reads, SQL message counts, separate academic/upload lanes and coalesced browser paints. The original 60,000-owner synthetic SQLite benchmark is preserved in `evaluation/academic/capacity_benchmark_20261017.json`; it is not a production or simultaneous-user result.

## Checked existing protections

- Session tokens are stored hashed; browser cookies are secure/HttpOnly/SameSite=Lax; web/native/socket authentication checks active and verified accounts. Password recovery uses a configured public base URL rather than a caller-provided Host for email links. Existing recovery, redirect and shared rate tests passed.
- Authentication rate counters use atomic shared-store updates and bounded expiry cleanup. Storage metadata and materialization caches are bounded. Private materialization uses reader pins so active readers are not evicted. Outage and missing-object failures are distinguished in tested paths.
- Clinical WorkJob admission has per-owner/global backlog bounds, deduplication, expiring leases, source fingerprints and publication fencing. Old lease holders cannot publish or finish replacement work in the tested boundaries.
- Realtime replay is owner scoped and page bounded; socket writes serialize and time out. Program/consultation retention uses durable job state. Their targeted tests passed; these do not establish arbitrary burst capacity or multi-region delivery.
- Administration list queries are paginated and storage-summary helpers already release the DB connection before R2 size calls. A cache miss can still require many metadata requests for a large user's collection; a persistent usage ledger/aggregation is an open scaling improvement.
- Expert-document publication already rechecks live ownership/state after storage. Account erasure revokes sessions and uses material tombstones/deletion jobs, but backup/provider/R2 deletion completeness was not independently verified.

## Verification

Two disjoint focused groups passed:

1. **210 passed, 14 skipped** — web/native authentication and recovery, storage, real HTTP upload/download boundaries, shared rate limits, queue/publication fencing, mobile query efficiency, program/consultation retention, realtime messaging, profiles and capacity. The 14 skips require a PostgreSQL connection. Includes **31 new system-audit regressions**.
2. **260 passed** — exact quick actions, Anthropic transport, source batches, semantic request understanding, question/quiz validation, native evidence, bounded capacity recovery and index isolation/concurrency/supervision. These use local synthetic fixtures, not paid/live provider answers.

Total: **470 passed, 14 skipped** across the two invocations. This is not the entire repository test suite. No skipped test is counted as passing. The earlier local argon2 import blocker was resolved by using already installed environment dependencies; requirements were not changed. The tested package versions are recorded in `test_environment_20261017.json` (FastAPI 0.141.1, Starlette 1.6.0, SQLModel 0.0.44 and SQLAlchemy 2.0.54).

Three modified Jinja templates and their embedded JavaScript pass syntax checking. The stream-render harness passes; the affected Python modules compile. The surface scanner emits no direct Session/open/storage calls in remaining async function bodies, but indirect calls, external dependencies and runtime behavior still require review; this scanner is not a security guarantee.

## Open items before a 60,000-user capacity claim

| Priority | Remaining evidence/work | Why it is still open |
| --- | --- | --- |
| P1 | Define peak active users, AI arrival rate, expected latency and accepted overload behavior. Test against production-equivalent PostgreSQL and compute. | Registration count does not specify simultaneous demand. Earlier Render measurements were one free instance, 0.15 CPU / ~512 MiB; no real 60k concurrency run exists. |
| P1 | Wire AcademicGenerationJob to a durable, fair request/worker/reconnect flow, with idempotency and budgets. | The model/helper exists, but source search finds no production enqueue/claim caller outside its definitions; the current academic ask/stream path still owns generation. Metadata does not make disconnected work durable. |
| P1 | Run native PostgreSQL migration, multi-worker, lock/lease, pool saturation and query-plan tests. | Fourteen selected PG tests are skipped without a connection. SQLite is not a substitute for PostgreSQL concurrency. |
| P1 | Finish durable cleanup/reconciliation for uploads during process crashes and ambiguous commits. | Native analysis avoids deleting potentially committed objects after a commit transport failure. Staging cleanup is best effort; patient-media races/storage failures can still leave unreferenced private objects. No complete cross-DB/R2 transaction guarantee is made. |
| P1 | Measure mixed indexing/raster/PDF/model memory peaks and isolate expensive work from navigation at the intended scale. | Process-local admission protects this process but multiplies across replicas. A free container, provider concurrency and DB pools cannot be sized from idle metrics alone. No plan/replica/billing change was authorized or made. |
| P1 | Complete the negative ownership/role/device matrix for every mounted route and independent security review. | Targeted tests and a source inventory are not an exhaustive penetration test or a KVKK compliance certification. Browser requests without Origin retain native/server compatibility and still depend on their normal authentication. |
| P2 | Bound bulk account-erasure work and reconcile storage/provider/backup retention. | Some account cleanup loops materialize a user's full collection; actual external erasure and backup behavior were not exercised. No production account was deleted. |
| P2 | Measure realtime history retention, reconnect storms, socket memory and admin storage aggregation on large datasets. | Source defaults and replay bounds are not measured production throughput. General event-history growth is not covered by a universal retention proof. |
| P2 | Physical Android/iOS keyboard, lifecycle, media and reconnect testing. | Backend HTTP tests and source inspection do not replace a device test; no APK/emulator session ran here. |

## Live course test blocker

The previous response requested permission to use Perio didem and Orto notes. The user replied to continue the detailed review. Automatic approval review nevertheless rejected a fresh signed-in notes navigation, stating that no user-authored message explicitly names authorization for those private notes. No alternate endpoint, credential extraction or indirect request was used to bypass it. The prepared live question cases remain NOT_RUN; the 470 passing tests and historical provider logs must not be described as new live question results.

No merge/deploy, live destructive action or external message was performed.
