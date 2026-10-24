# Voice examination summary design QA

Source visual truth: `generated_images/exec-946b8261-cf0b-4d96-8284-f19ccdfdec90.png` (853 × 1844 pixels; approximately 390 × 843 CSS pixels when normalized).

Implementation: production voice panel template, session template, `voice-exam.js` renderer and `voice-exam.css`. The local `design-preview` builder uses those actual files with clearly synthetic clinical content and fixed library icons. No patient data or provider calls are used for that preview.

Target state: one clinical accordion open, remaining sections closed, narrow mobile content width 390px. Production defaults to all sections closed and requires the existing explicit physician confirmation before saving.

## Evidence and comparison history

- The generated source was opened and inspected. It uses a navy/ice-gray palette, thin bordered cards, small amber clinical tag, clear evidence/recommendation labels, a source disclosure, a separate save-fields disclosure and a full-width primary action.
- First browser capture showed an empty preview frame. Rejected as implementation evidence; it cannot support visual comparison.
- The preview builder and asset paths were corrected. Browser subsequently rejected reload under its URL security policy. No alternate browser or indirect rendering path was attempted after this rejection.
- Implementation screenshot: unavailable. Full-view and focused-region comparisons are blocked. No side-by-side or pixel-fidelity claim is made.

## Required fidelity surfaces

- Typography: 24px title, 15px card headings, 14px body and 1.5 line-height implemented; browser wrapping verification pending.
- Spacing/layout: 16px content gutters, 52px minimum rows, 8px card gaps, 10px corners implemented; mobile overflow/keyboard verification pending.
- Colors/tokens: navy foreground, ice-gray canvas, white cards and amber clinical label implemented; visual comparison pending.
- Assets: local Tabler outline icons with upstream MIT license; no screenshot rasterization, decorative generated imagery, or handwritten icon replacements.
- Copy/content: real model output fills the cards. Optional short titles use the existing final-review call; grounded patient/source evidence and uncertainty notices remain available. Distinct evidence and communication advice are preserved when removing exact duplicates.

## Checks and remaining work

- Local renderer, save lifecycle, privacy cleanup and template tests are available and exercised separately; they do not establish visual fidelity.
- Primary browser interactions and console-error checks remain unverified after the blank-frame capture and security rejection.
- Authenticated production verification and deployment remain separate: production has not received this branch while Render build minutes are exhausted.

final result: blocked
