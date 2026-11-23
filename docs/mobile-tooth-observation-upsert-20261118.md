# Tooth-chart current-state upsert and web/native parity — 18 November 2026

## Web flow inspected first

The canonical reference was read from `app/templates/tooth_chart.html` and its `update_tooth_status` handler in `app/main.py`. The web chart selects an FDI tooth, edits one optional surface, and stores the tooth observation plus surface observation. The native chart calls the mobile whole-tooth endpoint and the independent surface endpoint.

## New defect found

Both `ToothStatus` and `ToothSurfaceStatus` were current-state tables without a unique key. Web and mobile handlers performed SELECT-then-INSERT. Two workers could both observe a missing row and insert duplicates for the same patient/tooth (or patient/tooth/surface). Native builds its display map from the returned rows; duplicate current-state rows can therefore make the displayed status depend on result ordering and appear to revert after refresh.

## Changes

- Added unique indexes for one `ToothStatus` row per patient/FDI tooth and one `ToothSurfaceStatus` row per patient/FDI tooth/surface.
- Added shared PostgreSQL/SQLite `INSERT ... ON CONFLICT DO UPDATE` helpers.
- Updated both the web form handler and both native mobile tooth endpoints to use the same atomic upsert contract.
- Added schema revision 18. It keeps the newest legacy current-state row by `updated_at`, then highest id as a deterministic tie-breaker, before adding the two unique indexes.
- PostgreSQL migration takes a transaction advisory lock and a short `SHARE ROW EXCLUSIVE` table lock while deduplicating/building the indexes. Reads remain available; writes pause during the bounded migration.
- Tooth status remains a clinical observation, not proof that a procedure was performed. No taxonomy, AI provider, prompt, or media behavior changed.

## Regression coverage

- Cross-channel web/mobile updates converge on one tooth row and one row per surface.
- A different account cannot update another owner's tooth observation.
- Revision 18 removes only duplicate current-state rows, preserves the latest observation, creates both unique indexes, and rejects a subsequent duplicate insert.

## Verification boundary

The tests are committed and wired into Android/security CI. They are not reported as passed until GitHub actually executes them. PostgreSQL staging migration, production data volume, and a 60,000-user load test remain separate acceptance gates.

No production migration, main merge, live deploy, APK/IPA publication, or real patient-data mutation was performed.
