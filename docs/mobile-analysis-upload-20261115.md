# Native analysis upload parity and durable receipt — 2026-11-15

Continues the existing mobile branch/PR257/issue258. No merge/deploy/store publication. The canonical web upload accepts up to four images, tooth_number and clinical_notes; it classifies image modality itself. NativeDentalAI previously exposed one image and omitted the clinical fields. NativeAnalysisUpload now supplies multi-image camera/gallery selection, explicit previews/removal, primary/permanent FDI input and clinical context, real multipart byte progress/cancellation and stable recovery.

## Source adaptation

- Existing backend image classification and canonical VISION queue remain. There is no invented manual modality selector or new inference provider.
- The shared filename/MIME normalization remains strict, including PNG/WebP URI inference, unsupported/mixed format rejection and filename safety. Patient-scoped history isolation from concurrent branch5a1ddae is retained. Its validation is again synchronous for an invalid patient argument while network responses remain asynchronous; the existing synchronous error contract had regressed when the function was made async.
- Native uploads persist an encrypted user/patient/UUID/file/context intent before any mutation. Read-only receipt lookup occurs first. Known server record opens without sending bytes. Uncertain retry is explicit and reuses the exact same intent; navigation during receipt lookup cannot trigger a later upload. Missing/corrupt stored intent is not silently discarded.
- Native XHR uses actual React Native multipart files, Cookie empty/withCredentials false, bearer auth, aggregate byte progress and a finite deadline even if abort does not settle. 100% bytes is explicitly separate from confirmed storage. A failed result read retains an action to reopen the already-created analysis.
- Only UUID-named application copies are deleted; original selected files are never removed. Temporary native image copies are private application cache, not additionally encrypted. Process-death/unsent-draft cache retention still needs audit.

## Server receipt and concurrency

Optional request_key preserves old caller compatibility. The native composer requires receipt support before POST; it does not silently fall back to the old uncertain path. A streaming bounded hash binds each key to patient, clinical inputs, filename and exact bytes. A changed payload with the same key is409. Receipt, analysis, assets and canonical VISION job commit in one DB transaction. PostgreSQL uses a request-specific advisory lock before canonical queue admission; it avoids acquiring owner/global locks in reverse order. WorkJob DONE/UPLOAD_RECEIPT stores opaque digest and job identity, no raw images or duplicate clinical text.

The same committed record can be recovered if post-commit realtime publication fails. Ordinary30-day job-history pruning must retain a receipt while its analysis exists; otherwise an old native retry could create a second analysis. A red/green regression verifies that case. Receipts become normally prunable when their analysis is deleted. No claim of a PostgreSQL concurrent load test is made: SQLite integration tests establish sequential transaction/receipt behavior, not production lock performance.

## Tests and remaining scope

Regression tests cover real multipart backend upload, same-key reuse, changed content/clinical conflict, private receipt access, post-commit lost reply, invalid FDI/key/image atomic rejection, retention and deletion. Native tests cover multiple images/context, double-tap, restore-before-upload, explicit exact retry, corrupt intent, failed result open, FDI, actual XHR/progress/timeout, leave-before-write and cache ownership. Previous patient/history/session/clinical/security checks remain.

The old single-image native pick/send handlers are removed rather than left as a second live path. Existing hook-state test indices were adjusted for the removed image state; patient/result/account-isolation expectations stay unchanged. Image-analysis result and viewer entry remain the existing NativeClinicalReview.

Remaining: full web radiograph/intraoral geometry viewer, selected existing-media + new-image mixed upload UI, EXIF/clinical image fidelity audit across all paths, OS cache retention/process death, signed Android/iOS/device/real network permission tests, production Modal/inference and CI, PostgreSQL simultaneous submissions/capacity. The default native15MB limit mirrors the default backend; runtime limit variation needs a configuration contract. No feature is certified release-ready by these source tests.

Final selected verification for this combined upload/viewer checkpoint: TypeScript clean, **320/320 Node tests** (18 session +46 realtime +256 beta) and **240/240 selected Python tests**, zero failures; Python warning count is recorded in the verification log. Includes eight new server upload-receipt tests and ten native upload tests. Android+iOS Hermes exports succeeded for the final source. Existing full-browser/PostgreSQL/device/remote-CI gaps are not declared passed.

A further red/green batch regression reproduced an unowned first-image file when the second image was corrupt. All images now validate in a temporary staging directory; canonical queue capacity is reserved before publishing files. Invalid batches leave no analysis, stored remote image or local staged file. Storage-outage cleanup and ambiguous commit behavior still require the broader retention audit; this does not claim full orphan cleanup under every remote storage failure.


## Shared image-count contract — 2026-11-16

The patient media archive and an individual AI analysis are separate operations and intentionally have different limits:

- **Archive upload batch:** up to 12 JPEG/PNG/WebP files per save operation. The web patient-profile uploader and native clinical-gallery picker both enforce this batch boundary. Each image remains subject to the existing per-file byte/pixel validation and ownership checks.
- **One AI analysis:** at most 4 images total, counting selected saved PatientMedia rows plus newly uploaded files. The web patient-profile analysis selection, web analysis GET/POST, native analysis composer and /api/mobile/v1/analyses all use this same admission boundary. Native gallery selection is also capped at four before opening the composer.
- The 12-file archive allowance never means that 12 images can be sent to one analysis. There is no silent truncation: over-limit requests are rejected before an Analysis/WorkJob is committed. Client-side guards are usability only; server-side validation remains authoritative.
- Saved-media IDs are revalidated against the requested patient and owner on both web and mobile routes. The existing idempotent upload receipt continues to bind retries to the exact patient, saved IDs, clinical context and file bytes.

Regression coverage now explicitly distinguishes the limits: archive 12 accepted / 13 rejected; web and mobile analysis 4 accepted / 5 rejected; saved-plus-new mixed totals are checked against four. Hosted GitHub Actions jobs on the inspected head still did not allocate a runner (empty step arrays and missing job-log blobs), so these new tests are committed but not represented as executed or green.
