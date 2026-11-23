# Dental AI mobile — web parity implementation ledger (2026-11-10)

Source branch: feature/mobile-beta-20261110 (PR #256). This branch is isolated; do not merge or deploy without review.

## Product contract
- Preserve dentalai.tr's information architecture, feature locations, content, and permissions. Native styling may use Instagram-like feed interactions but cannot relocate clinical actions arbitrarily.
- Reuse original web images, brand assets, icons, FDI/tooth visuals, and API data. Do not invent replacements before inventorying assets and licensing.
- Never simplify clinical functionality into a tooth-number checklist. Adult/primary arches, tooth surfaces, statuses, treatment history, anamnesis, and patient media must be accessible.
- Use shared backend and authenticated access; no production patient data in development fixtures.
- Maintain secure, account-scoped drafts and recoverable jobs. Do not send clinical data to analytics.

## Observed physical-device beta defects (user screenshots)
1. Patient detail: excessive whitespace; complaint, tooth/surface/treatment/media cards detached from clinical workflow; chart only behind button.
2. Tooth chart: FDI numbers wrap into 7-column grids, splitting upper/lower arch rows; checkmarks do not visually communicate surfaces or clinical status; primary teeth partially obscured by bottom tabs.
3. Profile: quick-access menu instead of complete expert profile, feed/publications, follow, edit, and media.
4. Expert directory: search input and empty area without actionable empty/loading/error states.
5. Program: raw ISO date string input and duplicate heading; needs native date/time selection.
6. Global: light status bar icons on pale background, oversized vertical spacing, placeholder square glyphs, and bottom tab consuming space on nested screens.

## Work packages and acceptance criteria
### P1 — shell/assets/navigation
Inventory actual web static assets and map to native use. Fix status bar contrast and bottom safe-area; nested detail routes should not permanently cover content. Replace placeholder glyphs with actual icon components/assets. Keep five top-level tabs and match web section placement. Compare screenshots at 360/390/430px.

### P2 — patient/clinical
Replicate web patient detail sections and action ordering; full FDI adult/primary chart with clinical surface selection and persistence; anamnesis and treatment history. Test chart orientation, mixed dentition, selected-tooth state, save/restore, permissions and offline/error behavior.

### P3 — social/expert
Native feed and profile with original image assets, multi-photo gallery, follow/like/comment/reply/bookmark, publications and ORCID, moderation and correct navigation. Explicit empty/loading/error states.

### P4 — AI
Full analysis image/results/history, academic upload/index/quiz/export, native voice capture/transcript/review and save; preserve provider routing and clinical safety checks.

### P5 — workflow
Consultations, messaging, notifications, schedule calendar/date picker, settings, privacy and account deletion parity.

### P6 — release
TypeScript, unit/integration, disposable PostgreSQL concurrency, device Android/iOS E2E, accessibility, performance, privacy/store compliance, signed distribution. 60k accounts != 60k concurrent users.

## Delivery discipline
Small PRs; each change documents screenshots before/after, routes, API contract, tests, regressions, and rollback. No claims of completed implementation until code/test evidence exists.
