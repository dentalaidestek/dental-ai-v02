# Clinical image metadata sanitization — 2026-11-16

## Web/native flow comparison

Re-read the web patient gallery in `app/templates/patient_detail.html`, the web gallery upload handler in `app/main.py:upload_patient_media`, and the web patient/guest analysis handlers. Compared those paths with the native patient-media endpoint in `app/mobile_api.py`, the legacy v3 adapter, and direct/selected-media analysis copies in `app/mobile_analysis_api.py`.

The native gallery upload already had a Pillow re-encode path that applied EXIF orientation and dropped EXIF. The web patient-gallery route only checked the first file-signature bytes before persisting the original. More importantly, the web guest-analysis and patient-analysis routes used bounded byte copies or `shutil.copy2` without metadata removal. The native direct-analysis upload and legacy-gallery-to-analysis copy checked the image but did not strip EXIF. A previously archived web image could therefore retain location/device metadata in the analysis copy.

## Change

Added `app/clinical_media.py` as the shared image intake boundary. It:

- verifies that the decoded image format matches the filename extension;
- rejects malformed files, unsupported formats, animated containers and images above the configured pixel limit;
- applies EXIF orientation before storage/inference;
- re-encodes pixel data without carrying EXIF or ancillary text metadata, preserves PNG palette transparency, and removes rejected staged files so invalid PHI-bearing temporary uploads are not left behind;
- retains only a bounded ICC profile because it affects color interpretation;
- uses JPEG quality 95 with no chroma subsampling, lossless WebP and PNG re-encoding;
- writes to a temporary sibling and atomically replaces the staged file.

The helper is now used by:

- web patient-gallery uploads;
- web guest-analysis image uploads;
- web patient-analysis new-image uploads;
- web patient-analysis copies of selected archived media;
- native patient-gallery uploads (including the v3 adapter that reuses the native helper);
- native direct-analysis new-image uploads;
- native copies of selected archived media before classification/provider work.

The archived source object is not rewritten when it is selected for analysis; only the analysis copy is sanitized. No bulk migration of existing patient media was performed.

## Regression coverage

Added `tests/test_clinical_media_sanitizer.py` with nine test cases covering JPEG orientation/EXIF removal, PNG text-metadata removal, palette transparency, lossless WebP pixel preservation, extension mismatch, corrupt files, pixel bounds, animated WebP rejection, rejected-file cleanup, route wiring, native direct-analysis upload and legacy archive-copy behavior.

An isolated local execution of the sanitizer logic passed eight checks: JPEG orientation/EXIF removal, PNG metadata removal, PNG palette transparency, WebP pixel preservation, format mismatch rejection, pixel-limit rejection, animated-image rejection and staged-file cleanup. The complete repository pytest file, Android typecheck and device tests have not been executed in this connector-only run; the committed tests are not represented as green.

## Remaining acceptance

- Existing archived patient-gallery originals may still contain metadata until re-uploaded or handled by a separately reviewed migration. Analysis copies are sanitized before classification/provider work.
- Durable gallery-upload receipts, process-death recovery and true byte-level progress remain open.
- Verify image fidelity and orientation on real Android/iOS devices with representative radiographs, color profiles and large images.
- Run the full Python security/regression suite and Android typecheck/build when GitHub Actions can allocate a runner.
- No production deploy, main merge, patient-record mutation or provider/model/prompt change was made.
