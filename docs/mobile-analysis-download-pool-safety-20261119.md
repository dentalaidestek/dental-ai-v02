# Native analysis image download resource isolation — 2026-11-19

## Web-first finding

The web analysis viewer authorizes the analysis and asset, then closes its SQLAlchemy session before calling `storage_ensure_local`. The native patient-media file route already follows the same pattern and offloads R2 hydration through Starlette's threadpool.

The native analysis asset and legacy-radiograph routes were the exception: both performed `storage_ensure_local` inside a synchronous `Session` block. On an R2 cache miss this could hold a database connection for the entire object hydration. The sync FastAPI handler also consumed a worker thread for the blocking storage call. Under concurrent image viewing this unnecessarily couples database-pool occupancy to remote object-storage latency.

## Changes

- Both native analysis image routes are now async.
- The authorized analysis/asset lookup copies only the storage path and safe filename while the short database session is open.
- The session closes before remote/local hydration.
- `storage_ensure_local` runs through `run_in_threadpool`, matching the existing patient-media route.
- Both responses use the shared `_mobile_private_no_store` policy: `Cache-Control: private, no-store`, `Pragma: no-cache`, and `Vary: Authorization`.
- Ownership and analysis-to-asset association checks remain before any storage access; an unauthorized request cannot trigger R2 hydration.

## Regression coverage

Added three integration regressions to `tests/test_production_optimization.py`:
1. Analysis asset R2 hydration occurs off the event loop after the database pool has returned to zero checked-out connections.
2. Legacy radiograph fallback has the same connection-release/threadpool behavior.
3. A different account receives the existing not-found response before storage hydration is attempted.

Updated `tests/test_security_hardening.py` to guard the cache policy and prevent a future synchronous hydration call from being reintroduced.

## Validation limits

The GitHub connector can read and commit repository files but this execution environment cannot resolve `github.com` for a checkout. Therefore pytest, Android typecheck, `npm run test:beta`, Expo export, Gradle and device tests were not executed in this pass. The committed integration tests are not reported as passing. GitHub Actions for the previous current head had no workflow runs/status records; earlier Android/security jobs failed before step 1 with `runner_id=0`, empty steps and unavailable log blobs. The platform-side runner/billing/provisioning cause remains unknown.

No schema, dependency, provider, inference, clinical record, production deployment or main-branch change.
