# Expert profile and voice review visual QA — 7 November 2026

Source visual truth: app/static/expert-profile-reference.png (1404×1536 supplied two-panel reference). Implementation evidence: docs/postlaunch-review/profile-member-390.png, expert-management-empty-390.png, voice-preparation-390.png, voice-compact-review.png. Full comparison boards: profile-comparison.png and manager-comparison.png in that directory.

Chromium viewport390×844, deviceScaleFactor1; additional social flows360/430/1280. Source panels690×1536 normalized to390×868, displayed next to same-width implementation crops. Fixed existing bottom navigation/consultation CTA appears within full-page screenshots; source omits those existing controls. Source has illustrative verified titles/publication counts; implementation uses test-account data and actual API counts, so text/count identity cannot be judged as pixel-equivalent. Management comparison uses empty composer with ORCID area, rather than the posted-feed state. Counts0 and absent academic-title badges are real synthetic-fixture state, not visual failures.

## Comparison history and fixes

- P2 legacy main inset: original rules targeted main.container but actual template is plain main. Fixed scoped main selector and legacy backlink margin. Postfix profile capture moves cover/back link nearer source without changing global shell.
- P2 management region order: published own feed displaced the reference ORCID card. Composer, ORCID/publications, rules and own feed now have explicit order; empty-composer screenshot confirms that structure.
- P2 empty media grid reserved a blank row. Empty attachment container now has no margin/display; tools reduced to an accessible52px height, input remains80px and auto grows. Recaptured manager screenshot after fix.
- P1 cluttered voice preparation: several ready labels/headings and duplicate capabilities request. Now one heading, one microphone action, on-demand privacy/history details; microphone disabled before consent. Browser preparation/recovery/logout test passes.
- P1 voice result fields used nested card frames and repeated quotations. Current result uses a single surface, dividers, compact growing textareas and collapsed nonduplicate evidence; only one confirmation action.

## Required fidelity surfaces

Typography: navy bold headings and neutral body text; source is raster/AI mock with no font metadata, current app uses existing system font stack. Some label wrapping/weight differs; it is not a pixel-font reconstruction. No unrelated font download or framework was added.

Spacing/layout: clinic cover, overlapping portrait, badges/stats/tabs and white feed cards preserved. Manager four tabs and inline composer match source hierarchy. Touch targets stay at least44px rather than reducing to the reference’s smaller normalized controls. No horizontal overflow at tested widths. Keyboard/physical Safari coverage remains open.

Colors/tokens: existing navy/blue, pale surfaces, green verification and ORCID label; existing global upper/lower navigation and consultation action preserved. No fake followers or badge ownership introduced.

Images/icons: exact supplied clinic/teeth artwork reused as existing source asset; real profile photos override fallback. Existing MIT Phosphor icons remain. Clinical image auto publication is not simulated to fill the screenshot. Source video/file/poll controls and automatic ORCID switch have no implemented scope and are intentionally not shown as dead buttons.

Copy/content: short labels and one main action; privacy/source caveats kept available in details. ORCID labels do not claim verified ownership. Cosmetic image contents are not copied into production as fabricated data.

## Verification

Real Chromium tested composer/publication creation, cancellation/tab state, photo ordering, offline retry, comments/replies/likes, consultation link, voice final save and draft recovery/logout. No application pageerror in these browser flows. Live shared Chrome also verified the approved deployed manager/publications and voice preparation pages. The new code itself was tested locally and remains on a separate branch.

No remaining blocking visual/usability defects in the supported composition/interaction scope. Literal pixel equality, physical device keyboard, and unsupported source controls are not claimed as completed. Those are explicit boundaries, not hidden seeded content.

final result: passed
