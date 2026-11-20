# Native clinical media pagination and refresh recovery — 2026-11-20

## Web-first contract reviewed

Before changing native code, re-read:

- `app/templates/patient_detail.html`: the patient profile's clinical archive, first-page cards, gallery modal, selected-image cap, original-file preview, and `patientMediaLoadMore` interaction.
- `app/main.py`: cookie-authenticated `/patients/{patient_id}/media/page`, descending `PatientMedia.id` keyset query, bounded `PAGE_SIZE + 1`, private/no-store response, original-file and thumbnail handlers.
- `app/clinical_media_gallery.py`: cursor normalization and page serialization.
- `app/clinical_media_thumbnail.py`: deterministic private JPEG derivatives without mutating originals.
- `app/mobile_api.py`: bearer-authenticated native list route and owner-scoped keyset query.
- `app/mobile_modern_api_v3.py` and `app/main.py`: unique native thumbnail route and router de-duplication order.

The web gallery rejects malformed ordering/cursors before appending cards. The native API previously checked duplicate/positive IDs and that the cursor appeared somewhere in the page, but did not require strict descending order, require the cursor to equal the last item, or distinguish a missing `next_before` property from an explicit terminal `null`.

## Changes

### Native API contract

`mobile/src/modernApi.ts` now:

- requires an explicit `next_before` property;
- accepts only an explicit `null` terminal cursor or a positive safe integer;
- requires unique, positive, strictly descending media IDs;
- requires every returned ID to be below the requested `before` cursor;
- requires a nonterminal cursor to equal the last visible row ID;
- accepts only `PHOTO` and `RADIOGRAPH` types;
- bounds note, filename, tooth metadata and validates their runtime types;
- continues to construct same-origin mobile API file/thumbnail paths rather than trusting arbitrary server URLs.

### Native lifecycle and retry behavior

`mobile/src/NativePatientMedia.tsx` now coalesces a first-page refresh requested by app resume or a realtime media event while a cursor page is in flight. The pending refresh runs once after the active page releases the load lock. It is cleared on account/patient scope reset and component cleanup. Existing account/token/patient guards, mutation locks, encrypted drafts and no-polling behavior remain in place.

### Regression coverage

- Added `mobile/tests/patientMediaPagination.cjs` for valid terminal/nonterminal pages, missing cursor, cursor-not-last, ascending/duplicate rows, invalid type/metadata, before-boundary violations, and invalid IDs.
- Extended `mobile/tests/patientMediaAccountSwitch.cjs` with two realtime events arriving during one older-page request; they must coalesce into one first-page refresh after the page completes.
- Extended `mobile/tests/patientMediaRoute.cjs` to lock down owner-scoped keyset pagination, private response headers, and the native thumbnail's post-generation ownership recheck.
- Added the new API contract test to `mobile/package.json` `test:beta`.

## Commits in this pass

- `354dc056` — native page ordering and cursor validation
- `a150d66f` — pagination contract regressions
- `48a52b88` — include regressions in beta suite
- `f930455b` — coalesce refresh during cursor paging
- `49cbe217` — realtime in-flight refresh test
- `f26d6f98` — owner-scoped list/thumbnail security tests
- `7dccb8da` — align thumbnail test with fail-closed ownership check
- `76ba7091` — explicit TypeScript cursor narrowing
- `3af51e96` — reset queued refresh on scope cleanup
- `3299da90` — correct regression-test formatting

## Validation and limits

The changed files were read back from the target branch after the writes. The tests are committed and wired into `npm run test:beta`, but were **not executed** in this run: the available environment has no GitHub network access/local checkout, and GitHub reports no workflow runs or combined status checks for the starting PR head `cb68dbec7966214bd0c45b76fe102dfeef8e5411`. Therefore no new TypeScript, Jest/Node, Expo export, Android APK, PostgreSQL or device pass is claimed.

The prior Android typecheck error recorded in PR #257 was traced to the obsolete duplicate `ModernScreens.MediaGallery` calling `uploadPatientMedia` with an outdated argument list; that duplicate screen was removed earlier and the canonical route now delegates to `NativePatientMedia`. This pass does not claim a fresh typecheck because the current head has no executable CI evidence.

No patient data was read or changed. No schema migration, main merge, production deploy, store publication or APK release was performed.
