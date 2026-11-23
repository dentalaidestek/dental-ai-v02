# Web AI analysis upload recovery — 2026-11-22

## Web-first trace

Re-read the canonical web flow before changing native parity work:

- `analysis_new.html` submits to `POST /analysis/new/{patient_id}`.
- `create_analysis` verifies the patient owner and selected PatientMedia IDs.
- It bounds the saved + new image count and byte total.
- The old implementation committed an `Analysis(status="ANALYZING")` row before copying/persisting each image, then committed `ImageAsset` rows and the canonical VISION/PRELIMINARY job.

The native receipt-first route already had a durable recovery path through `WorkGarbage`, but the web route did not.

## Defects found and corrected

1. If the first R2 image write succeeded and a later image write failed, the web route left the initial Analysis row in ANALYZING and the earlier object had no durable cleanup receipt.
2. A final metadata commit can be ambiguous to the request process. Recovery must not delete a file if the commit actually succeeded and an ImageAsset/WorkJob now references it.
3. Unsupported web image extensions were silently skipped after Analysis allocation instead of being rejected before clinical records or storage were created.
4. The media route registry regression built a path by concatenating APIRouter.prefix with a route suffix. FastAPI versions can materialize route paths differently. The test now resolves the canonical source endpoint and asserts that the same callable is mounted exactly once.

## Implementation

- Record every generated analysis object key before local copy or remote persistence.
- On ordinary failure or request cancellation, roll back/close the original session, then use a fresh session to enqueue strict `enqueue_analysis_asset_cleanup` receipts.
- Give the existing collector its 30-second grace window; no new worker, polling loop, or storage path was introduced.
- Re-read the Analysis under a PostgreSQL row lock. Delete the initial ANALYZING row only when there are no committed ImageAsset rows, no Analysis WorkJob, and no legacy image/radiograph pointer.
- If the final commit actually succeeded, retain the Analysis and live references. The existing collector checks ImageAsset and legacy Analysis pointers before deleting an object and removes a stale cleanup receipt instead.
- Reject missing filenames and non-JPEG/PNG/WebP files before allocating Analysis or writing any clinical bytes.

## Regression coverage added

`tests/test_web_analysis_upload_recovery.py` covers:

- Two-image web submission where the second R2 write fails after the first succeeds: 503 response, no stuck Analysis/ImageAsset/WorkJob rows, and durable cleanup receipts for both generated paths.
- Ambiguous final-commit recovery: committed Analysis/ImageAsset/WorkJob rows survive; the garbage collector removes the stale cleanup receipt without deleting the live object.
- Unsupported extension rejection before Analysis allocation or storage persistence.

`tests/test_mobile_route_registry.py` now verifies active route ownership using the exact endpoint callable mounted on `main.app`, rather than assuming a prefix concatenation.

## CI and acceptance boundary

Starting HEAD: `92efd9a851ff80cfcdab3e7b04be9f34669487e0`.

- Security Recovery run `44975455898` executed the Python security/identity suite: **613 passed, 1 failed**. The failure was the route-registry test expecting a prefixed path that did not match the mounted route representation. The PostgreSQL migration/concurrency and web duplicate-submission steps were skipped because the Python step failed.
- Six native security jobs passed on that run.
- Android validation for the starting head `92ab6cb` was cancelled by the subsequent documentation-only commit; no final-head typecheck is claimed from that run.
- The five source/test commits in this pass triggered Android run `44978542511` and Security Recovery run `44978542518`; they were pending when this note was written. Do not treat the committed regressions as passed until the final-head jobs complete.

No production/staging database, patient record, R2 object, main branch, live deployment, or store artifact was changed. The web upload still publishes storage objects while the initial Analysis row has already been committed; the new recovery closes the orphan/stuck-record failure but does not yet move all object I/O outside database-session scope or establish 60,000-user capacity.
