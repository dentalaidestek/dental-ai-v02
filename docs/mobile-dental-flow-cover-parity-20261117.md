# Dental Akış native link-cover parity — 2026-11-17

## Web-first reference

Reviewed the current branch's real web flow before native changes:
- `app/templates/expert_following.html`
- `app/templates/_expert_social.html`
- `app/static/expert-social.js`
- `app/static/dental-flow.css`
- `app/expert_social_api.py` (`PostBody.cover_media_id`, `POST /posts`, media ownership checks)

The web composer supports a distinct uploaded-image link cover. Its cover is shown on the link card and excluded from the ordinary gallery. If exactly four uploaded images exist and no explicit cover was selected, the first image is used as the cover.

## Native gap and fix

Native previously supported four uploaded images, ordering/removal and server-generated link previews, but did not persist or send a custom cover ID. It also hid the link card entirely when metadata preview was unavailable, while web continues to show the URL card.

Implemented:
- Encrypted draft persistence and bounded restore validation for `cover_media_id`.
- Per-image accessible cover selection, with selected-state semantics.
- Cover clearing when its image or the link is removed; ordering retains the chosen ID.
- Link card shown for any non-empty link, with optional preview metadata.
- Explicit cover image preferred over server-generated preview cover.
- Web-compatible first-image fallback when all four media slots are occupied and no explicit cover is selected.
- Client preflight requires the selected cover ID to belong to the draft's uploaded media before any POST.

The existing backend already accepts `cover_media_id`, checks the preview receipt's owner/URL, locks the media rows, verifies every media item belongs to the current expert and is unattached, and persists the cover relation. No backend route or schema change was needed.

## Regression tests added

- `mobile/tests/social.cjs`: valid cover restore, invalid/non-member cover drop, client API rejection before fetch.
- `mobile/tests/socialScreens.cjs`: custom cover selection/submission, four-image fallback, selected-image removal, and link card visibility when preview metadata is absent.

These test files are included in `npm run test:beta`.

## Privacy, cost and acceptance

No patient or clinical media is involved. No new network request is needed to select a cover; it reuses an already uploaded first-party media ID. No polling, parallel upload fan-out, database migration, storage policy change or AI call was introduced.

The tests are committed but not claimed as executed. Full Android typecheck, Node beta suite, Expo export, backend pytest, and physical Android/iOS acceptance are still blocked by the current GitHub Actions runner failure and remain open acceptance gates.
