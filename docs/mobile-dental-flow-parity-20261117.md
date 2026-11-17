# Native Dental Akış parity — 2026-11-17

## Web-first inspection

Reviewed the target branch's real Dental Akış path before changing native code:

- `app/templates/expert_following.html` and `app/templates/_expert_social.html`
- `app/static/expert-social.js` and `app/static/dental-flow.css`
- `app/expert_social_api.py`
- `app/expert_social_relationships.py`
- `app/expert_social_safety.py`
- `app/expert_social_models.py`
- `tests/expert_social/test_dental_flow.py`

The web composer supports up to four JPEG/PNG/WebP images (8 MiB each), multi-select, ordering/removal, safe HTTPS link previews, owner-bound preview receipts, and a separate link-card cover. In feed cards, the cover is excluded from the image gallery. For an owner's post in the aggregate Dental Akış, the web action is "Profilimde yönet"; editing and moderation actions remain on the expert profile.

## Gaps found in native

- The native composer selected and uploaded only one image per picker interaction.
- Uploaded media had no visible remove/reorder controls, despite the draft already storing ordered media IDs.
- The native composer accepted a link string but did not call the existing safe `POST /preview` endpoint or persist the owner-scoped `preview_id`.
- Feed cards showed the raw URL rather than the web's metadata/cover preview card.
- A link cover in `post.media` was also rendered in the native gallery, duplicating the web cover.
- Native aggregate-feed owner actions exposed edit/pin/comment-close/delete directly, while web routes the owner to profile management.

## Changes

- Native image picker now allows multiple selection up to the remaining four-image budget. It pre-checks the web's MIME allowlist and 8 MiB per-file limit, uploads sequentially, and persists each successful media ID before starting the next upload.
- Draft media can be reordered or removed. These operations update the encrypted draft's ordered ID list. As in the web composer, removed uploads remain unattached and are left to the existing orphan-media maintenance path; no broad cleanup scan was added.
- Added a typed native `getLinkPreview` call to the existing `POST /api/expert-social/preview` endpoint. The client rejects non-HTTPS URLs before network access and validates the server's HTTPS URL, preview ID, and first-party cover-media path.
- The preview ID and bounded metadata are persisted with the SecureStore draft. Draft recovery validates at most four unique positive media IDs and drops mismatched/unsafe preview receipts without discarding otherwise valid text/media.
- Post creation now includes the owner-scoped `preview_id`. Existing server validation still checks preview ownership and URL equality before attaching metadata or its cover.
- Native feed cards now render a metadata/cover link card and keep its cover out of the gallery, matching web ordering semantics.
- Aggregate-feed owner actions now route to the expert profile for management, matching the web action.
- Tab label now matches web: "Takip Ettiklerim".

## Privacy and scale constraints

- No patient identifier, clinical image, or patient record is sent to the social preview service.
- Preview fetching remains server-side through the existing SSRF-safe URL resolver, with its existing per-user throttle, bounded network slots, and timeout.
- Image uploads remain sequential and bounded to four files; no parallel upload fan-out or new background polling was added.
- No database schema, migration, production configuration, or storage policy changed.
- No merge, live deploy, store build, or patient-record mutation was performed.

## Regression coverage added

- `mobile/tests/social.cjs`: HTTPS-only preview request, bearer-token/credential policy, preview receipt in post payload, legacy draft compatibility, media-ID bounds/uniqueness, and cover-path validation.
- `mobile/tests/socialScreens.cjs`: multi-image selection, 8 MiB rejection, per-upload draft persistence, reorder/remove, preview rendering and receipt submission, cover/gallery separation, owner-management routing, and tab wording.

These tests are committed but are **not reported as executed** in this run. The current GitHub Actions evidence is still the gating factor.

## CI and acceptance status

The previous current-head Android typecheck and Security recovery runs had no runner assignment and no job steps; log artifacts returned 404. This is a GitHub Actions execution/runner problem, not a compiler or pytest diagnostic. The current commit's workflow runs must be inspected before claiming a green result.

Still required:
- Full `npm ci`, `npm run typecheck`, `npm run test:beta`, and Expo Android/iOS export on a real runner.
- Full backend `tests/expert_social/test_dental_flow.py` regression execution.
- Device acceptance on Android and iOS, including image-picker multi-select, authenticated cover loading, interrupted upload recovery, and deep-link opening.
- PostgreSQL query and concurrent upload/load tests before any 60k-user capacity claim.

## Commit range

This work starts from PR #257 head `54fb2e9474ad` and is committed only to `feature/mobile-web-parity-20261110`. The PR remains open and Draft. Main merge and live deploy are not authorized.


## Follow-up hardening

A review of the newly added preview/draft path found two additional edge cases:

- A restored SecureStore preview could have a non-HTTPS URL or a cover media ID that did not match its first-party media URL. Draft recovery now requires an HTTPS URL without credentials/nonstandard ports, and the cover URL must be exactly `/api/expert-social/media/{cover_id}`. The API response validator enforces the same ID/path binding. Opening a restored preview repeats the HTTPS/credential check.
- The first composer implementation blocked `post()` when `attempted=true`, even though the UI correctly showed "Tekrar dene". That would have prevented recovery after an ambiguous network response. The guard now permits retry of the frozen draft; edits/uploads/preview changes remain locked, and `submitDraft` reuses the same idempotency UUID and payload. A regression test covers this.

Additional tests cover non-HTTPS restored previews, mismatched cover IDs, and idempotent retry. These tests are committed but not executed locally or in CI.

## Latest observed CI at head d5c415a

The following current-head runs completed as failures before any step:

- Mobile Android CI: run `44030198756`; jobs `133860014317` (typecheck) and `133860014558` (beta APK).
- Security recovery: run `44030198821`; job `133860015124`.
- Expert social: run `44030198735`; job `133860014209`.
- Admin security: run `44030198867`; job `133860014845`.
- Voice regression: run `44030198773`; job `133860015148`.

All six direct job-step queries returned empty arrays; all six log downloads returned Azure `BlobNotFound 404`. No npm, TypeScript, Node beta, Gradle or pytest command ran. This does not establish a source-level test failure or a passing result. The exact hosted-runner/account cause is not exposed by the repository API.

The work from starting PR head `54fb2e9474ad` through this follow-up comprises 18 commits on the feature branch. The PR remains Open/Draft; no main merge, live deploy, APK/IPA publication or patient-record mutation.

## 2026-11-17 — Native custom link-cover parity

Re-opened the web composer source before changing native code: `app/templates/_expert_social.html`, `app/static/expert-social.js`, `app/static/dental-flow.css`, and the existing `POST /api/expert-social/posts` contract in `app/expert_social_api.py`.

A remaining web/native gap was confirmed: web lets an expert choose one of the uploaded images as a separate link-card cover, shows that cover in the preview, excludes it from the post gallery, and uses the first image as the cover when all four media slots are filled and no custom cover was chosen. Native previously sent only `preview_id`; it could not choose a custom cover, and it hid the URL card when metadata preview was unavailable.

Native changes:
- Persist optional `cover_media_id` inside the existing encrypted SecureStore draft; restore it only when it is a positive safe integer, belongs to the draft's uploaded `media_ids`, and the draft still has a link.
- Add an accessible per-image “Kapak yap / Bağlantı kapağı” control. Removing the selected image clears the cover; clearing the link clears the cover; reordering preserves the selected media ID.
- Render the URL card whenever a link exists, even when server metadata is unavailable. Prefer the explicitly selected uploaded cover, otherwise use the safe server preview cover.
- Send the selected cover ID in `POST /posts`. If exactly four images are present and no explicit cover is selected, match the web fallback by choosing the first image. With fewer than four images and no selection, the server's preview cover remains the fallback.
- Validate the cover ID client-side before network access. It must be one of the post's own media IDs; the existing backend still validates ownership and unattached state while locking media rows.

Regression coverage added:
- `mobile/tests/social.cjs`: cover draft restore, invalid/non-member cover rejection, and API preflight validation.
- `mobile/tests/socialScreens.cjs`: custom cover selection and submission, four-image first-cover fallback, removal of the selected cover, and URL-card visibility/opening when preview metadata is unavailable.

No patient identifiers, clinical images, or patient records are used by this feature. No new polling, upload fan-out, backend route, database migration, storage policy, or AI provider call was added.

The tests are committed but not reported as executed: current GitHub Actions jobs are failing before runner assignment, with `runner_id=0`, empty step arrays and unavailable log blobs. Full typecheck, `npm run test:beta`, Expo export, Android/iOS device acceptance and backend/PostgreSQL regressions remain required.
