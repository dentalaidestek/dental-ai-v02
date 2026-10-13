# Academic AI file-answer flow audit — 13 October 2026

Base production commit: `dba9b984c316bb372b7b7585c3c1857a44f4553e`.

The target is to understand the current Turkish request and real follow-ups,
retrieve the correct owned sources, and answer the whole requested task from
those sources. Source discovery, factual support, answer completeness and
provider availability are separate checks. Passing code tests is not evidence
that every possible student question will be answered correctly.

## What the published methods establish

OpenAI's documented file-search API combines keyword and semantic search; its
retrieval guide describes query rewriting, filtering and rank fusion. This is
public API documentation, not a claim about private ChatGPT implementation.
Anthropic's Contextual Retrieval publication explains loss of document context
at chunk boundaries, contextual embeddings, keyword search and reranking. It
also describes full-context input when a corpus fits the model's budget. That
publication does not disclose every implementation detail of the Claude app.

- https://developers.openai.com/api/docs/guides/tools-file-search
- https://developers.openai.com/api/docs/guides/retrieval
- https://www.anthropic.com/engineering/contextual-retrieval

## Audit findings and implemented changes

| Stage | Verified previous behavior | Updated behavior |
|---|---|---|
| Request understanding | Gemini receives the current request, last eight messages and owned heading outline. A fixed 15-second timeout aborted live planning. | Preserve Gemini interpretation; configurable 10–75 second timeout, 45-second default, exactly one attempt. Genuine clarification remains distinct from provider failure. |
| Candidate discovery | The caller requested up to 96 rows, but `_fts_rows` silently capped the result at 20. Question records could exhaust that pool before being filtered. | Honor a bounded pool up to 120. Apply notes/question candidate domains before ranking, retaining owner/course/published-version fences. Legacy question-looking TEXT records remain eligible for question requests. |
| Small sources | Literal query matching and a top-k list could miss information in a short corpus. | For ordinary topic requests without a selected or matched named subsection, use the entire factual index when it fits 128 rows, 48,000 input characters and at most four scanned pages. Keep topic/task/exclusions unchanged. Explicit named-subsection boundaries and visual requests stay query-specific. No extra embedding or generation call. |
| Large-source meaning search | The active path always passed `query_vector=None`, despite existing vector-search infrastructure. | Both endpoints prepare one Gemini query embedding outside a database transaction only when compatible complete published material vectors exist. Combine vector and lexical candidates while preserving literal subjects and complete named sections. On unavailable embeddings retain owned lexical search, never legacy language heuristics. |
| Vector preparation | New published indexes are FTS-only. Rebuilding their OCR to obtain vectors would add avoidable work. | Add an explicit dry-run/resumable enrichment command for published chunks. Use literal filename, parent heading and source body as embedding context; no contextualizer LLM. At most 32 calls by default, hard cap 256 per invocation. Snapshot/version/body/heading/name checks prevent writes to changed sources. No cron, automatic backfill, source-text change or new index publication. |
| Scan evidence | Ordinary candidates exceeding eight scan pages could retain their rows while omitting later original images. Multi-page rows supplied only their start page. | Partition every over-budget candidate set and supply every required page in each bounded batch, including multi-page ranges. Preserve OCR as search/reading assistance rather than verified facts. |
| Large comparisons | Independent batch answers were concatenated; neither model call necessarily saw both comparison sides. | Extract relevant, source-cited facts from each required batch, then make one final grounded comparison over all supported extractions. Do not emit an independent partial comparison as a final answer. Stop explicitly on synthesis-budget or provider failure. |
| Citations | Text evidence identified material IDs/pages but did not always show the source filename. | Include the literal filename alongside page and section metadata. A model's citation still requires factual review; this is not an automatic correctness certificate. |
| Delivery | #93/#94 retain visible partial stream output and prevent failed planning from being saved as a completed answer. | Preserve those behaviors. Release batch image bytes even on generation failure. Existing completed-answer print/PDF flow remains. |

## Call and cost boundaries

- An ordinary source-backed question uses the existing planner and final
  generation calls. Small-context routing adds no model call, but may increase
  input tokens compared with a smaller top-k prompt.
- A large topic request adds at most one embedding call when a compatible,
  fully enriched published material is available. Empty/partial/wrong-model
  vector indexes do not trigger query embedding or supply semantic candidates.
- An oversized comparison uses N bounded evidence-extraction calls and one
  final comparison call, plus planning. The final call is necessary for a
  comparison across sources that cannot fit together in one input. When the
  selected sources fit one request, it remains one final generation call.
- Enrichment is explicit and resumable. It does not redo OCR, change readiness,
  create background schedules, or automatically process all uploaded notes.
  Its dry run reports pending rows and selected source characters, not a guessed
  currency price. Preparing production vectors is a separate operation from
  implementing or testing the pipeline.

## Validation and limits

Local full Academic tests: **613 passed, 576 subtests passed, 30 skipped** before
PostgreSQL CI. The database skips are not counted as passing SQL tests.
New regressions cover whole small-context access without literal overlap,
candidate budgets above 20, pre-ranking domains, preserved scan tails and page
ranges, comparison synthesis/failure, query-embedding transaction release and
one-call behavior, partial/wrong-model vector rejection, enrichment dry run and
changed-source protection. Real PostgreSQL and bounded actual-Gemini evaluation
results must be recorded from the actual CI run. The first PostgreSQL CI run
caught unwanted sibling-section inclusion in a small full context; preserve
matched named-subsection boundaries rather than relaxing the original test.

Remaining limits: embeddings depend on source extraction quality; unvalidated
OCR pages cannot be declared complete. Grounded synthesis can still omit or
misinterpret facts, so real answers require inspection against original notes.
Streaming partial answers are not durable background/resumable jobs. Citations
are not yet checked automatically against every generated factual claim. No
claim of universal answer correctness or parity with ChatGPT/Claude is made.
