# Source matching and minimum useful model calls

## Scope and measurement

The 20 cases in `source_matching_20261017.json` use the existing 109-chunk snapshot of the uploaded cephalometric note and PostgreSQL SQL executed by PGlite. Expected physical pages and excluded terms were checked against that snapshot. Plans are supplied explicitly; this is a retrieval test, not a live Claude interpretation or answer-quality benchmark. No paid model calls were made.

All 20 source-matching cases passed after the fixes. Cases cover individual definitions, two-subject comparisons, table output, complete skin/bone single-point sections, paired-point exclusion, a precise page selection and an unsupported subject. The unsupported subject returns no evidence. No ordinary case requests original pages. Some definition cases retain other pages mentioning the same requested term; this is not a claim of perfect precision.

## Additional findings and fixes

1. The small complete-context path still rejected courses with more than four scanned pages. Removed that obsolete scan-count query/gate: indexed OCR follows the same 128-row and 48,000-character limits as native text. Ownership, active version, deletion and changed-generation checks remain.
2. Optional embedding preflight used the same obsolete scan gate. It now skips embedding for a complete bounded text context without querying scan counts. It still uses existing compatible vectors for larger eligible courses; no vector index is rebuilt.
3. Literal nested section paths could be lost during recovery from old chunks. A stored path explicitly present as a full text line now updates section continuity even after a previous literal heading. The existing uploaded-note SQL regression, previously failing its `Deri Noktaları > Tek Noktalar` expectation, passed after this correction.
4. Native-page recovery selected a second page sharing only a partial search token even when the full subject existed. The Labiale superior/inferior comparison initially also received page 38 (Molare superior); it now receives pages 4 and 5. Prefer full-phrase factual pages per subject, retaining partial recovery when there is no full factual match. Exam-option pages cannot suppress factual fallback.
5. The SQL evaluation fixture now stores page text/status, matching the columns used by the current native-page path. The new matrix and focused regressions are included in the semantic CI workflow.

## Claude call budget

Counts assume one successful planner, no transient recovery or question repair. They exclude optional Gemini embeddings and Modal indexing.

| Request path | Planner | Source calls | Final answer | Total Claude calls |
|---|---:|---:|---:|---:|
| Normal text/summary/comparison/new questions fitting one context | 1 | 0 | 1 | 2 |
| No source evidence or clarification | 1 | 0 | 0 | 1 |
| Export previous answer to PDF | 1 | 0 | 0 | 1 |
| Oversized notes requiring B source batches | 1 | B | 1 | B + 2 |
| Source-question transcription or exam-topic inventory requiring B batches | 1 | B | 0 | B + 1 |

The earlier 128-chunk / 21-page synthetic test proves that a fitting text request takes one generation call, avoiding source extraction/synthesis. It does not measure the exact production Perio request or establish a fixed token/latency saving. Existing malformed-question repair and bounded transient recovery are retained; removing them only to advertise a lower call count would sacrifice validation/recovery.

The planner stays in place for free-form questions: it controls conversation references, file/page/section boundaries, source versus generated questions and requested output. No keyword intent engine or guessing shortcut was enabled. Prompt caching would affect token billing, not the number of calls, and was not added here.

## Verification and limits

- Broad local suite: **784 passed, 34 skipped, 30 deselected, 576 subtests passed**, in 12.17 seconds. The 30 deselected cases are benchmark/holdout/combined cases; PostgreSQL-only cases are skipped without their dedicated URL.
- The new 20-case SQL matrix passed as one test in 1.11 seconds. The existing uploaded-note SQL regression and two explicit-visual regressions also passed in a separate run. That combined PGlite session subsequently lost its connection on another fixture; it is not reported as a full PostgreSQL suite pass.
- Focused native-page, dense-preflight and small-context tests: 37 passed in 0.63 seconds.
- `git diff --check` passed.

This preserves tested source coverage and exclusions; it does not prove every future answer is factually correct. No live latency/cost comparison, simultaneous-user load test, production merge or deployment was performed. OCR quality still limits ordinary text answers. Original diagrams, handwriting and marked-answer inspection remain available through the explicit visual path.
