# Clinical image admission contract — 2026-11-16

## One limit, two different operations

- **Patient archive upload:** up to 12 images in one gallery-upload batch. This stores clinical media on the patient record; it does not start AI analysis.
- **One AI analysis:** up to 4 images total, counting both previously saved patient-media IDs and newly uploaded image files. The server is authoritative. Web and native clients must never silently truncate an over-limit selection.

This preserves the existing inference and queue admission budget. It also resolves the previous mismatch where the patient profile let users select 12 saved images, while the web POST and native API rejected any analysis containing more than 4 combined images.

## Client behavior

- The web patient gallery lets users select at most `MAX_ANALYSIS_IMAGES` (currently 4) for one analysis. Its select action explicitly selects the first four visible records, not every archived image.
- The web analysis form explains that saved and newly uploaded images share the same total limit.
- The native patient gallery, native image normalizer, durable upload-intent parser and composer all use the exported `ANALYSIS_MAX_IMAGES` constant (currently 4).
- The 12-image archive-upload batch limit remains separate and unchanged.

## Server enforcement and privacy

- Web GET selection rejects more than the shared analysis limit; web POST rechecks the combined saved + new count before creating an Analysis.
- Native API parsing rejects too many saved IDs and then rechecks the combined saved + new count before patient lookup, analysis allocation, asset publication or queue admission.
- Existing same-patient checks and owner checks remain mandatory for each saved media ID. Cross-patient or other-owner media are not made visible by this limit change.
- Existing file signature/extension validation, image sanitization, per-file byte/pixel bounds, durable queue admission and upload receipt/idempotency behavior are unchanged.
- The limit is not increased to 12: archived media volume is independent from a single inference request's admission budget.

## Expected rejection behavior

- Web form: HTTP 400 with a Turkish message stating the 4-image total.
- Native API: HTTP 422 with a Turkish message stating the 4-image total.
- No Analysis row, ImageAsset, VISION job or upload receipt is allocated for an over-limit native request. The web route rejects before Analysis allocation.

## Regression coverage

- Web GET accepts exactly four selected saved images and rejects five.
- Web POST rejects four saved images plus one new image and leaves no Analysis.
- Native intent parsing accepts four saved IDs, rejects five, and rejects four saved plus one new.
- Native server rejects five saved IDs and four saved plus one new before Analysis or VISION allocation.
- Existing upload receipt replay, owner isolation, mixed saved/new ordering and durable upload semantics remain covered by their existing tests.
