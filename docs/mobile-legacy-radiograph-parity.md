# Mobile legacy radiograph parity

## Web-first finding

The web analysis viewer is driven by `ImageAsset` rows. Older `Analysis` records can still carry a legacy `radiograph_path` without an `ImageAsset`. The mobile analysis detail API already exposed `legacy_radiograph_available` and a private `GET /api/mobile/v1/analyses/{analysis_id}/legacy-radiograph` route, but the native clinical review did not consume either contract. Such a record therefore appeared to have no image in the native clinical review even though the server could still serve its radiograph.

## Change

- Pass the server-validated availability flag from `NativeDentalAI` into `NativeClinicalReview`.
- When there are no modern assets and the flag is true, show a legacy-radiograph thumbnail and an accessible full-screen preview.
- Keep modern `ImageAsset` records authoritative; do not show the legacy fallback alongside modern assets.
- Use the existing authenticated mobile route, bearer header, `cache: reload`, and opaque per-session render keys.
- Retry a failed image fetch by remounting the image source; do not persist a clinical image to a public or shared cache.

## Safety and limits

The route authorizes the analysis through the patient owner before hydrating the stored object and applies the mobile private/no-store response policy. The native client never receives or constructs a storage path. The fallback is an image-only legacy preview: it does not fabricate a vision snapshot, finding list, overlay, or AI result for a record that has no modern `ImageAsset` evidence. No database schema, patient record, original image, worker, inference provider, or production deployment was changed.

## Regression coverage

`mobile/tests/clinicalWorkflow.cjs` covers endpoint construction, bearer authorization, private cache behavior, image visibility, full-screen open/close, precedence of modern assets, and retry after an image load failure.
