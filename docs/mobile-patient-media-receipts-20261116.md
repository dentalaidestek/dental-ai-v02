# Native clinical media upload receipts — 2026-11-16

## Web flow inspected first

The web patient profile uses one multipart form for up to 12 selected JPG/PNG/WEBP files, a PHOTO/RADIOGRAPH choice, and a 12 MB per-file limit. The web gallery then supports preview, selection, analysis of up to four saved images, and deletion. The native profile already had the gallery/analysis actions, but its upload path allowed 15 MB, only reported a file count, kept the queue in React state, and treated a lost response as a manual gallery-check dead end.

## Changes on the mobile parity branch

- The mobile upload limit now matches the web limit: 12 files per batch and 12 MB per file. The general analysis-upload limit is unchanged.
- Every native file receives a UUID request key before transfer. The per-user/per-patient queue is written to SecureStore (through the existing chunked draft store) before the network call.
- The mobile API now reports multipart byte progress through React Native XMLHttpRequest and keeps the multipart boundary owned by the transport.
- The API checks a receipt before sending a file. After an app restart or an uncertain response, it uses the same request key to reconcile the server receipt before attempting any missing upload.
- The server hashes the sanitized file and normalized metadata, stores only the digest and media ID in a WorkJob receipt, rejects a key reused for different content, and does not resurrect a media record after it has been deleted.
- Receipt status is scoped to the authenticated owner and patient. Live patient receipts are retained while the patient exists, preventing delayed retries from creating duplicate clinical images.
- No image bytes, file paths, bearer tokens, or clinical notes are copied into receipt payload JSON. The request key itself is hashed before storage.

## Verification status and limits

Regression tests were added for exact replay, mismatched payloads, deleted-media tombstones, owner isolation, receipt retention, SecureStore-before-network ordering, process-death reconciliation, stable-key retry, and upload progress. The repository checkout is not available in this runtime because GitHub HTTPS DNS resolution failed; therefore the full Android typecheck and pytest/Node suites could not be executed locally. GitHub Actions must provide the authoritative run result. A restored picker URI can still be unavailable if Android evicts its temporary cache file; in that case the server receipt is checked first, but the user may need to select the original image again if no receipt exists.

No merge to main and no live deployment were performed.
