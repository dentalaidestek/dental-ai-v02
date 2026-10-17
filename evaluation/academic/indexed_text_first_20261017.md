# Use indexed OCR text without automatic original-page re-reading

## Cause

The semantic retrieval path treated every selected OCR/IMAGE checkpoint as requiring original visual evidence, regardless of the request. It replaced the indexed text with instructions to read the original. Source batching also counted OCR pages against the visual-page limit. This added original-file materialization on Render, image/PDF input tokens, and potentially extraction and synthesis model calls even for plain-text tasks.

This was introduced to preserve answer marks, corrections and other information OCR can miss. Those requests still need visual evidence, but ordinary indexed-text questions should not inherit that cost.

## Change

- Only a planner request requiring visual inspection selects original pages. OCR extraction method alone no longer does so.
- Indexed OCR text stays in the generation context for normal explanations, summaries, question generation, source-question transcription and grading.
- Text-only batch planning performs no PDF-byte metadata lookup and splits by the existing text budget rather than the number of scanned pages. Complete source order and continuation rules remain.
- Planner instructions distinguish creating a table from inspecting source pixels; ordinary table output and indexed table text do not require original-page inspection.
- Explicit diagrams, marked answers and handwriting retain the owned, active-version original-page path, materializer and byte limits.
- No Modal jobs, indexing schema, storage policy, credentials or production settings changed. No migration or reindex required.

## Verification

- 222 focused planner/retrieval/batch/static/generation/PDF-download tests passed in 2.76 seconds (six dependency deprecation warnings).
- Three additional PostgreSQL-compatible PGlite tests passed in 0.59 seconds: ordinary OCR text with foreign/stale exclusion and zero original-page materialization; explicit visuals for topic and course scopes.
- A 128-chunk / 21-page synthetic case fits the text budget, avoids visual metadata reads and uses one generation call instead of source extraction/synthesis. This excludes the separate planner call and is not a live latency measurement.
- Existing test expectations that all OCR pages require visual input were updated to request explicit inspection. The PostgreSQL fixture gained the native-text/status columns used by the existing retrieval implementation.
- `git diff --check` passed.

The broader test run was interrupted after stalling; it is not reported as passing. A separate all-PostgreSQL attempt encountered an existing uploaded-note heading expectation mismatch and a PGlite connection termination. The targeted tests above completed successfully.

No paid API call or production deployment was performed for this change. Live latency and token savings are unmeasured. Sixty thousand registered users do not establish concurrent capacity; this change removes avoidable per-request work but does not constitute a load test.

## Tradeoff

Normal answers now depend on the stored OCR/chunk text. Missing labels, crossed-out answers and handwritten corrections must be fixed during indexing or requested through explicit visual inspection; they are no longer silently re-read on every question. Text exceeding the existing budget still uses bounded source batches. This does not promise exactly two calls for every possible request.
