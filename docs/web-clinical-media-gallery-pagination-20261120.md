# Web clinical media gallery pagination — 2026-11-20

## Web-first finding

The patient profile previously selected every `PatientMedia` row for the patient, rendered every gallery card into the HTML response, and pointed both gallery thumbnails and the top-three profile preview at the original full-resolution file route. The native archive already used a 40-row descending-ID cursor and a private thumbnail derivative.

This meant a patient with a large archive incurred unbounded ORM/template work on the web profile and downloaded original radiographs for small gallery cards.

## Changes

- Added `app/clinical_media_gallery.py` with a fixed 40-item page contract, strict positive integer cursor parsing, stable descending-ID cursors, and a display-only serializer. Storage paths, owner IDs and original filenames are not returned.
- The web patient-detail route now loads at most 41 media rows (40 visible plus one look-ahead row) and separately obtains the total count. It preserves the first three profile previews and reports the real total.
- Added cookie-session-authenticated `GET /patients/{patient_id}/media/page?before={id}`. It verifies patient ownership, scopes media to the patient's owner, returns only bounded display metadata, and sets `private, no-store`, `Vary: Cookie`, `Pragma: no-cache` and `nosniff`.
- Added the web-session `GET /patients/{patient_id}/media/{media_id}/thumbnail` route. It uses the existing deterministic private JPEG derivative, releases the first DB session before storage hydration, then rechecks patient ownership, media ownership and the unchanged storage reference before serving. If the row disappeared during generation, the orphan derivative is deleted.
- Web profile and gallery cards now use thumbnails; opening a card still loads the original full-size image.
- The gallery fetches additional 40-item pages on demand. Selection is held in a Set across pages, remains capped at the existing four-image analysis limit, and uses DOM APIs/textContent with exact same-origin route validation for dynamically added cards.
- The existing upload, original-image preview, single-delete, delete-all and analysis submission routes remain in place.

## Security and compatibility

- The web endpoints use the existing cookie session, not the native bearer endpoint.
- Every page query is scoped by patient ID and the patient owner's media ID; non-admin cross-account access is rejected.
- No original file path, storage key, owner ID or filename is serialized.
- Thumbnail responses are JPEG, private/no-store, vary on Cookie and use nosniff/CSP headers.
- The original file route remains the full-resolution source for preview and downstream analysis.
- No database schema or migration, AI provider call, clinical record mutation, main merge or production deploy was added.

## Regression coverage

- `tests/test_clinical_media_gallery_pagination.py`: cursor validation, stable page boundaries, fixed page size, bounded metadata serialization and same-origin URL contract.
- `tests/test_clinical_media_thumbnail.py`: web thumbnail owner recheck, private response headers, bounded first page and template route wiring.
- `mobile/tests/patientMediaWebGallery.cjs`: same-origin session fetch, cursor continuation, cross-page selection, four-image cap, exact path validation, DOM-only rendering and thumbnail/original separation. Registered in `npm run test:beta`.

## Validation boundary

The GitHub connector can read and write repository files but this run has no checked-out worktree or dependency environment. The new Python and Node suites were committed but not executed here. Full pytest, mobile typecheck, Android build, browser interaction tests, PostgreSQL query-plan inspection, and multi-instance R2 race/load tests remain required before acceptance.
