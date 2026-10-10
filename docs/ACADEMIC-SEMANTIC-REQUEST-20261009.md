# Gemini-only Academic chat — implemented on work branch, not deployed


## Decision

Use one bounded pretrained language-model interpretation before retrieval for opt-in Academic V2. A morphological toolkit such as Zemberek can analyze suffixes/lemmas but does not supply a conversational study-task planner. A small local multilingual LLM is a candidate for later distillation, not a proven free/fast replacement on the present web host. No new GPU/service/model weights or training job were introduced.

A dedicated Gemini 2.5 Flash-Lite instance returns a strict request contract: complete resolved question, operation, topic/course scope, count, difficulty and clarification. Input includes the original question and at most eight intact conversation messages; no PDF/chunk payloads, identifiers or credentials. The prompt requires clause ownership, exclusions, negation, order, brands, output constraints and grounded references. This is pretrained-model interpretation, not another regex sentence catalogue. Local evidence matching still exists and is not assumed flawless.

## Integration and limits

- Both normal and streamed V2 handlers invoke the interpreter after ownership, dental scope, READY-index checks and after closing their initial DB transaction.
- The resolved question reaches the existing owned FTS retrieval. Explicit semantic course scope reaches coverage sampling; an explicit topic suppresses accidental course expansion. Requested count informs the existing bounded coverage budget.
- Reference heuristics receive no old history after semantic resolution, preventing an earlier topic from overwriting the resolved topic. Original conversation remains available to final generation.
- No authorization identifiers, source/chunk IDs or executable actions are accepted in the JSON contract. Existing server ownership, source version and factual evidence gates remain in force.
- One planner transport attempt, 5-second timeout, 512 output token ceiling. The instance-local JSON schema never changes the shared answer provider. A semantic attempt suppresses the old second paid recovery-planning call, including on invalid output/timeouts.
- Provider account reservations, request budgets, rate/health tracking are reused. This is a per-execution call bound, not a new cross-HTTP idempotency guarantee or monthly spend cap.
- Oversized context is not silently truncated: interpretation is skipped and existing behavior retained. Invalid output/errors also retain the old retrieval behavior. Logs contain timing/error type, not transcripts/model output.
- Default-off flag: `STUDY_ACADEMIC_SEMANTIC_PLANNER=1` enables it. Model override: `STUDY_ACADEMIC_PLANNER_MODEL`, default `gemini-2.5-flash-lite`. No env changes were made. Final answer model unchanged.
- This is NOT a claim of perfect/general Turkish understanding. Model schema validity is not semantic accuracy. Existing lexical sufficiency and compound-constraint coverage require real evidence tests. Ambiguous/non-study requests request clarification rather than supplying invented note facts.

## Cost assumptions, not measured usage

Official Gemini pricing retrieved 9 October 2026: 2.5 Flash-Lite standard text input $0.10/M tokens and output $0.40/M tokens:
https://ai.google.dev/gemini-api/docs/pricing

1,000 input + 200 output tokens per interpretation gives $0.00018/request, $0.18/1,000 or $18/100,000. This excludes answer generation, OCR, R2, hosting, retries in other components and taxes. Actual history length and usage tokens change the amount; it is neither a measured average nor a guaranteed spend ceiling. Existing final generation can still be a second model call. Cheapest self-hosted versus API route cannot be concluded without throughput/quality measurements.

Primary references:
https://github.com/ahmetaa/zemberek-nlp/blob/master/morphology/README.md
https://huggingface.co/Qwen/Qwen3-0.6B
https://ai.google.dev/gemini-api/docs/structured-output

## Validation and remaining gate

20 targeted contract/provider/routing tests pass, plus 10 existing recovery tests (five subtests included). Tests check invalid schema/limits, prompt preservation, one attempt, no secret logging, default-off, large context, second-planner suppression, ambiguity without DB lookup, owned topic lookup and count-aware course routing. Python compilation and diff whitespace checks pass.

A separate 20-case real-model smoke evaluator covers varied study operations and references. Its operation/term assertions are an initial signal, not a definitive semantic gold standard. Human review must check modifier ownership, exclusions/negation and complete requests, then actual note chunks and final answers. It defaults to estimation only. Run explicitly with an already configured secret in an approved shell:

`python scripts/evaluate_academic_understanding.py --run`

No live Gemini evaluation was run: local GEMINI_API_KEY is absent. No fabricated accuracy/latency/cost result. Production enablement/deploy is blocked on this real-model check and end-to-end evidence regression. Synthetic contract stubs do not prove model competence.

Earlier prepared chat reply/read fixes remain on parent commits; production remains a58ed18. OCR configuration and Modal resources were not changed.


## Direct planned source searches

The planner contract now requires `retrieval_queries`: at most four source phrases,
with topic tasks requiring nonempty phrases and course/clarification using none.
The original resolved request still preserves exclusions, relations, ordering and
output instructions. Independent comparison subjects become separate alternatives
in one primary FTS lookup; quoted Unicode tokens prevent FTS operator injection.
The topic primary query bypasses the old request-word/subject parser and its
canonical-subject additions. Authenticated owner/course filters and evidence
sufficiency/reranking remain enforced. No additional provider call or per-chunk
LLM call is added, and the feature remains disabled pending actual-model evaluation.

This does not turn lexical FTS into vector search. Existing semantic ranking and
requirement gates still need end-to-end evaluation for recall, comparisons and
exclusions; no claim of production accuracy or complete Turkish understanding is
made. No chunks are deleted or reindexed, no migration is required, and no
production settings are changed.

## 10 October continuation: balanced candidates and actual note replay

Independent planner searches now receive separate bounded candidate shares in
one PostgreSQL LATERAL statement. Each subject is ranked inside its own pool;
duplicate chunks retain their best rank before fusion. This prevents a frequent
comparison subject from consuming all 20 returned candidates. Single-phrase and
legacy retrieval retain their existing SQL, title bonus and evidence gates.
Every group keeps the authenticated owner/course and active READY source filters.
No provider call, new model, migration or reindex is added.

`scripts/evaluate_academic_note_flow.py` inspects the actual Ali Kiki source PDF
and can run the interpreter -> owned FTS -> reranking -> sufficiency -> final
answer flow against temporary tables in a dedicated PostgreSQL test database.
`--run` requires preconfigured GEMINI_API_KEY and ACADEMIC_TEST_DATABASE_URL;
`--answers` explicitly includes final generation. At most eight cases run.
Temporary tables are rolled back; production enablement is never changed.
Generated answers still require semantic review; schema/page recall cannot
prove factual correctness. Live mode reproduces chunking/enrichment, not the
worker's OCR or batched repeated-margin cleanup, and is not a production index
health check.

Actual source replay: downloaded `01-Ali Kiki toplu 2023.pdf` has 505 physical
pages (the extracted Library text reports 502). Text-only extraction gives
477 chunks and 43 empty-text pages; OCR was NOT run and completeness is NOT
claimed. Eight hand-authored planner-contract replays passed expected page
recall through production reranking/sufficiency and prompt construction:
hipofiz p64, tiroid p66, comparison p64+p66, prenatal p101, organogenez p105+p107,
five-question request, resolved follow-up and ambiguous clarification. Replay
uses an explicitly labelled token matcher, NOT real PostgreSQL/model accuracy,
and generated no answers or paid calls.

The new Academic semantic flow CI uses real PostgreSQL temporary-table tests
to reproduce common/rare-subject starvation and verify owner/course/version,
READY/deletion filters and duplicate removal. Local focused checks: 140 passed,
5 subtests passed, 3 PostgreSQL tests skipped because no local server is present.
No real Gemini evaluation: this environment has no configured key. The planner
therefore remains default-off; the completion gate is real-model + PostgreSQL
note-flow evaluation and semantic answer review. No deploy performed.

Two existing source-location assertions still searched for the pre-planner
literal `precise_query = _fts_query`; they failed on parent 720f361's conditional
assignment before this continuation. Their anchors now use `precise_query =`.
The same exhaustive/primary/rescue invariants and exact call-count assertions
remain in place; no scorer, threshold or behavior gate was relaxed.


## 10 October: Gemini owns interpretation and final response

The chosen flow is original question plus the last eight intact messages -> one
Gemini interpretation -> owned note retrieval -> one Gemini final response. No
local model training or per-chunk model calls are introduced. The final response
retains the original message, dialogue and complete interpreted request. Legacy
output/task heuristics no longer add competing instructions on this path.

Both normal and streaming endpoints use the same interpretation gateway. When
the enabled interpreter is unavailable, fails schema validation, or exceeds the
input budget, the request gets a truthful retry/context message instead of
silently returning to the old language rules. Disabled mode and simple
acknowledgements retain their behavior. Successful interpretations bypass legacy
reference rewriting. The interpreter has one attempt, a 15-second timeout and
1536 output tokens to avoid squeezing complete compound requests into 512 tokens.

Preserved pending work adds partial lexical candidate recall for model phrases
and real PostgreSQL tests against the actual text-only Ali Kiki snapshot.
Qualifiers remain mandatory at evidence sufficiency checks; partial lexical
matches cannot authorize missing comparison subjects.

Local focused verification: 145 tests and five subtests pass; seven PostgreSQL
tests require CI. The CI live step is explicitly triggered by [real-gemini] in
the commit message or manual run_live input and uses only the repository
GEMINI_API_KEY secret. A missing key writes a blocked artifact and fails that
step, rather than reporting a green real-model validation. At most eight
interpretations and eight final responses can be requested. The source fixture
contains no OCR text and cannot establish full source coverage. No production
settings are changed and the feature stays disabled pending real-model semantic
review.

Ali Kiki empty-text-page audit: the production local OCR reader ran on all 43
pages with no final errors. Five pages yielded more than 20 characters (36,37,
47,158,305); 37 remain visual-only and page 361 yielded one character. OCR text
has not been semantically validated or incorporated into the production index.
The saved OCR audit records text/confidence per page; blank OCR output does not
prove a source page is empty. Visual attachments are still required for diagrams.


## 10 October: remove legacy language routing from active chat

This section supersedes the earlier default-off/legacy-fallback descriptions.
The user chose Gemini interpretation as the sole Academic chat architecture.
The interpretation disable flag is retired. Gemini now also selects source kind
(notes, source questions, or past-question patterns), depth and whether actual
visual attachments are needed. Normal and streaming chat require a Gemini plan;
missing access, invalid output and oversized dialogue return a truthful error
message without falling back to local language heuristics. The normal endpoint
always requires the published V2 index, matching the streaming endpoint.

The new academic_semantic_retrieval module uses Gemini search phrases directly,
PostgreSQL ranking, bounded lexical pool balancing and owned READY source
filters. It does not call the old query resolver, study-task classifier, dental
requirement parser, semantic reranker or rule-based evidence sufficiency gate.
A candidate-presence flag only allows the final Gemini request; it explicitly
does not certify that the sources answer the question. The final prompt requires
Gemini to distinguish supported and unsupported parts, preserve every compound
request and avoid filling missing facts from general knowledge. It no longer
calls the old output/dialogue rules. There is no recovery-planner call.

Source question pagination and visual materialization still use server-owned
source IDs and published versions. Legacy helpers/modules remain available for
shared indexing, stored-data cleanup and historical regression tests; they are
not reachable as an alternative language engine from either chat endpoint.
Neither production configuration nor deployment is changed. Real-model semantic
quality remains unverified until secure Gemini access is configured.

Focused local verification for this cutover: 151 tests and five subtests pass;
eight PostgreSQL cases are reserved for real CI. Ali Kiki 8/8 hand-authored
contract replay also passes on the new retrieval path. The legacy static
output-rule assertions were replaced with the new no-legacy-import/grounded
compound-request contract; no scorer, benchmark threshold or access gate changed.
