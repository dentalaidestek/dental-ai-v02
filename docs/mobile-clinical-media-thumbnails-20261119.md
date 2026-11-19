# Native clinical-media thumbnails — 2026-11-19

## Web flow inspected first

- `app/templates/patient_detail.html` renders the first three profile images and gallery cards from the original `/patients/{patient_id}/media/{media_id}/file` endpoint.
- `app/templates/analysis_viewer.html` passes authenticated analysis asset URLs into the embedded viewer; it is a full-resolution analysis workflow, not a gallery-thumbnail source.
- The web behavior is intentionally unchanged: the native gallery is optimized without changing the clinical viewer or original image semantics.

## Native flow and issue found

`NativePatientMedia` used `item.url` for the profile strip, FlatList cards, the analysis-compose strip, and the full-screen preview. Consequently a paged gallery could download original radiographs for every visible card and then download them again for the preview.

The mobile media list also returned the original URL only. The original-file handler performed R2 materialization while the SQLAlchemy session remained open, holding a pooled DB connection across remote storage latency.

## Implementation

- Added `app/clinical_media_thumbnail.py`: deterministic sibling key (`.thumb.jpg`), EXIF orientation correction, bounded 480px longest edge, JPEG quality 78, and a process-local bounded single-flight lock cache.
- Added authenticated `GET /api/mobile/v1/patients/{patient_id}/media/{media_id}/thumbnail`. It checks patient ownership and media ownership before storage access, closes the DB session before R2 I/O, and returns `private, no-store`, `Pragma: no-cache`, `Vary: Authorization`, `nosniff`, and inline JPEG.
- Original-file route now copies the authorized storage reference and closes the DB session before R2 materialization.
- Native media list responses include a thumbnail URL. Native profile strip, FlatList cards and compose strip use it; the full-screen preview continues to use the original URL.
- Native page size explicitly requests 40, matching the client validator and avoiding a 60-item response being rejected.
- Web single-delete, web delete-all and native DELETE queue the deterministic thumbnail key with the original. If queue admission fails, synchronous fallback attempts both objects. No schema migration is required.
- R2 missing-object responses remain 404; storage timeout/provider failures become retryable 503 responses. A corrupt/unsupported source image returns 415 without changing the original.

## Tests added

`tests/test_clinical_media_thumbnail.py` covers deterministic keys, image size/format and original immutability, concurrent single-flight generation, R2 write failure propagation, owner-scoped route/cache headers, full-resolution preview retention, and derivative cleanup on web/native delete paths.

These tests were committed but **not executed** in this GitHub-only environment. No pytest, Android typecheck, Expo export, Gradle build, or device test is claimed.

## Remaining risks / acceptance gates

- The process-local lock prevents duplicate generation inside one worker. Two independent workers can race to create the same deterministic derivative; writes are idempotent and produce the same bounded JPEG, but cross-worker generation is not globally serialized.
- R2 timeout/retry and deletion queue behavior still require integration tests against the configured object store.
- Verify native image requests include the bearer header on Android and iOS.
- Verify existing R2 objects, local-development storage, deleted originals, malformed images, and concurrent delete-vs-thumbnail requests in a deployed test environment.
- No production deploy, migration, main merge, or clinical record mutation was performed.
