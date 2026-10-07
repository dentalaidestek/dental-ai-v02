# Course retrieval and conversational study verification

Status: current improvements are draft; authenticated production verification
is pending. Render records show the earlier `08a53d9` recovery implementation
went live on 2026-10-06 at 21:13:43 UTC. The later dialogue/screenshot fixes are
not in that deployed commit. No successful authenticated browser stream,
indexing speedup, or model fine-tuning is claimed.

## Observed production failure

On 2026-10-06, Render service `srv-daeb9d740ujc73ei7gmg` logged HTTP 200 for
course 3 `/notes/courses/3/ai/ask-stream` requests at 17:13:18.927 and
17:13:26.927 UTC, followed by the empty-context generation guard. HTTP 200 alone
does not demonstrate a completed answer stream.

The existing authenticated endpoint checks ownership, course scope and V2 index
readiness, reads the last eight chat messages, resolves retrieval, releases its
database session, then streams NDJSON. Successful messages are persisted only
after generation and source-version revalidation. This endpoint contains no
usage-credit decrement. That does not establish the behavior of other endpoints.

## Implementation behavior

- Source-only study requests share course scope across summaries, explanations,
  new questions, study goals and note/slide/material wording. Named topics remain
  topic queries, including unknown medical terms.
- Course coverage reserves representative content from each material before
  allocating the rest of its budget. READY, ownership, course and active-index
  restrictions remain in SQL; retrieval relevance thresholds are unchanged.
- Source adjuncts, goals, output format, question counts and discourse prefixes
  no longer become medical search terms or replace the active topic.
- Selected questions support `Soru N`, numbered lists and ordinal inflections.
  Distractor options are excluded from retrieval subject ownership. Letter,
  grouped and short free-text answers bind to actual pending questions; an
  ordinary outline or rhetorical teaching question is not a pending quiz.
- Compound clinical subjects are distinguished from explicitly coordinated
  subjects. Ambiguous references ask for clarification; explicit new topic
  requests own their scope and clear stale output settings.
- Successful local retrieval and deterministic dialogue/clarification routes
  never invoke the recovery planner. Failed evidence may spend one Gemini
  planning call and one bounded retrieval retry before final generation.
  Recovery phrases only expand candidate discovery: original request, course
  scope, scorer and evidence requirements are unchanged. If recovery still
  fails, an actionable follow-up is streamed; no factual answer is fabricated.
- Generation retains its single final generation call and existing model.

## Difficult-query recovery and learning records

Both V2 ask endpoints release their retrieval Session before invoking the
recovery planner. A separate Gemini adapter uses one attempt, a four-second
transport timeout and 700 output tokens. This is a timeout setting, not a
measured end-to-end latency guarantee. There is no provider retry chain or
recursive recovery. Course catalogs are bounded to 32 READY sources and four
headings per source; metadata/persistence queries have a local 1.2s timeout and
the recovery retrieval uses a local 1.5s per-statement timeout.

The planner receives the current request, locally resolved intent/scope, missing
facets and bounded recent dialogue. Its strictly parsed JSON supplies up to
four alternate search phrases and an unverified failure diagnosis. It cannot
choose chunk IDs, grant access, rewrite requirements or lower thresholds.
Rescued evidence passes the original relevance and sufficiency gates. Recovery
does not solve every intent/resolver defect; diagnoses inform subsequent local
fixes rather than silently replacing the user's request.

The additive `AcademicRecoveryEvent` table is registered before existing
`create_all`. It stores private owner/course-scoped query, first plan, suggested
phrases, diagnosis, candidate IDs, outcome and elapsed time. Records start
UNREVIEWED, with cascading course/user foreign keys. Application logs contain
only outcomes and timings, not user questions or conversation text. Persistence
failure is logged and does not discard a recovered answer.

`scripts/review_academic_recovery.py` produces a private read-only pattern report
for an explicit owner/course. Repeated failure classes and missing facets can
be turned into shared resolver rules and regression scenarios after checking
the original messages and actual source evidence. The stored diagnosis is not
automatically trusted, deployed as a rule or used to fine-tune a model. Recovery
outcomes describe evidence recovery, not answer correctness or browser success.

## Local validation and its limits

58 focused source/dialogue tests, ten recovery tests and 59 existing continuity checks pass. Two
benchmark audit checks pass, and changed Python files compile. Focused tests
include source requests with spelled counts, unknown named topics inside notes,
free-text quiz answers, task rejection, clinical noun protection, compound
topics, and sole-topic versus previous-topic references.

Conversational control checks additionally cover learner-practice requests,
study-program requests, comprehension repair with/without prior topic, courtesy
messages that bypass candidate retrieval, and pending-question continuity across
a courtesy exchange. These routes do not classify every message as a new topic.

The 2026-10-07 natural-dialogue pass additionally covers 64 topic/wording pairs
(eight medical topics and eight omitted-subject requests), missing-context
clarifications without candidate SQL, successive facet changes, explicit known
and unknown topic switches, course exam preparation over stale topic history,
and follow-ups during a pending quiz. Example/procedure/dose/cause requests
retain the active user-owned subject. They cannot be graded as free-text quiz
answers. Request grammar is matched as full clauses; named new topics and
clinical nouns are not globally fuzzy-matched. Synthesized question-generation
controls are removed from subject search terms. Evidence thresholds are intact.

Study-artifact transformations such as "Notları çalışabileceğim hale getir"
also retain course scope while named topics remain named topics.
Known remaining limits include unrestricted indirect study transformations,
some quiz preference-only commands,
long-range references outside the eight-message window, and ambiguous pronouns.
These checks do not establish model-level understanding for arbitrary dialogue.

## Screenshot root-cause regressions (2026-10-07)

The exact Soru Hazırla request incorrectly matched `cevapla` inside
`cevaplarımı`, selecting `questions_exhaustive` instead of note-backed new
question generation. Complete predicate boundaries and explicit generation
precedence repair this shared routing defect; explicit source-question solving
and plain cursor continuation still work. A mocked candidate-access test runs
the real retrieval orchestration and asserts coverage hydration, sufficient
selected evidence, owner/course arguments, and no source-question-page query.

"Bu çok yüzeysel her başlığı açıkla" and "Diğer başlıklar nerede" were lexical
subjects. They now continue the existing user-owned course/topic scope; unknown
referents clarify rather than fabricate a medical topic. Source-backed outline
feedback instructs final generation to address each hydrated heading with
supported detail and to disclose incomplete scope, without claiming unseen
sections were covered. Final answer completeness still needs live verification.

`ACADEMIC_Q_CURSOR` was emitted into stored assistant history for pagination,
then HTML-escaped into visible text. The shared UI normalizer removes the
metadata before escaping on both initial history rendering and streaming while
leaving server continuation intact. Node execution of the actual template
renderer verifies marker hiding, question formatting and HTML escaping. The
browser verifier now rejects the screenshot's provider refusal text, includes
both outline feedback requests, and checks rendered assistant text for leaked
pagination markers. It has not been run authenticated against production.

## Depth versus basic sufficiency

Previously detail/outline feedback reused the normal eight-chunk topic limit
and 24-chunk course hydration budget. A provisional sufficient result skipped
neighbor retrieval even when the user explicitly requested more depth. Thus a
basic answer sufficiency decision did not imply evidence completeness for a
detailed explanation. This is a code-level cause, not proof of the actual chunk
payload used in any screenshot request.

Explicit depth/completeness requests now allocate a topic limit of at least 16
and course hydration budget of 48. Topic queries inspect up to four relevant
neighbors even when initial evidence passes basic sufficiency; resulting rows
still re-enter unchanged relevance, coverage and final sufficiency gates.
Ordinary short questions retain existing budgets, and negated detail requests
do not widen them. There is no extra provider call in this policy. Four tests
exercise budget selection, course hydration, neighbor behavior and failure on
empty expanded evidence. Candidate SQL/provider behavior and live answer depth
remain unverified; increased budgets are bounded settings, not latency or answer
quality guarantees. Routing logs include requested depth and topic budget.

## Three quick-study buttons

Tests extract the actual UI data-prompt values and run shared retrieval routing
for three prompts, two material counts (one/six), and three conversation histories
(empty, prior clinical topic, prior source-question cursor): 18 combinations.
Candidate hydration is mocked, not actual PostgreSQL/READY verification.

Two additional defects surfaced: "yüksek verimli şekilde özetle" incorrectly
required a source figure because of "şekilde", and "20 zorlayıcı çoktan seçmeli
soru" lost its count because the count modifier grammar omitted "zorlayıcı".
Bounded output-manner normalization now distinguishes figure references from
rendering style; actual "şekildeki"/table requests retain visual requirements.
Shared count/difficulty grammar preserves both Turkish and ASCII wording.

The teaching button now explicitly requests all course topics in detail, reaching
the shared deeper-evidence policy without a preset-specific route. The shared
study output contract applies equally to natural requests: summary headings and
key points, supported teaching rationale/details, and source-backed new question
generation with requested count and hidden answer key. It never claims unseen
sections were read. The browser verifier additionally requires exactly Soru
1..20 and rejects visible answer-key headings/per-question answer labels for
the question preset. Prompt contracts and local routing do not certify actual
generated count, teaching completeness, latency or authenticated streaming.

## Compositional Turkish language pass

Independent politeness, source, scope and operation slots are varied across
288 requests, with another 48 uppercase/ASCII variants. Additional checks cover
54 feedback/outline combinations, 12 known/unknown named-topic contrasts, and
written-count carry-over. These are synthetically composed grammar cases, not
an exhaustive natural-language benchmark or a production quality rate.

The shared language layer now strips polite request adjuncts, recognizes
source-wide manner constructions (from beginning to end, point by point, step
by step), and composes a complaint clause with an outline-follow-up clause.
It retains named medical nouns rather than globally repairing them. Cardinal
count grammar handles digit and supported Turkish compound forms such as
"yirmi üç", feeding the same study plan and conversation count axis. Inflected
question-generation predicates reach the shared study-plan parser. Explicit
depth remains a separate evidence-allocation axis.

No neural model training or automatic rule promotion took place. Transformer
language models infer meaning through learned contextual representations;
these changes improve deterministic request decomposition and bounded state,
not equivalent general language understanding. Image checkpoints still flow
through the existing extraction/OCR pipeline, and selected visual source pages are
materialized for visual generation after DB retrieval. No OCR, Modal or visual
indexing code changed; no new image-quality validation is claimed.

SQLModel and SQLAlchemy are unavailable in the local execution environment.
Language/resolver tests therefore use an AST harness that removes unavailable
database/storage imports while executing the real resolver functions. The
generation evidence branches are exercised without a provider. These checks do
not validate SQL execution, authenticated HTTP, generation factual accuracy or
production behavior.

Multiple 50,000-case synthetic resolver snapshots were run. Failures remain,
including noisy operators, reference ambiguity and inconsistent gold constraints
(for example, a gold case requires dropping `agresif` although the active user
topic explicitly says `agresif periodontitis`). Snapshot metrics are diagnostic,
not production quality estimates or a complete conversational certification.

The benchmark's literal `\\w` boundary bug, nominal-inflection checks and
normalized-query/context distinction were repaired separately from production
retrieval scoring. Real inherited stale format still fails its audit test.
Do not compare raw pass counts across different benchmark revisions as though
they measure only implementation improvements.

## Authenticated browser verification still required

`scripts/verify_authenticated_study_stream.py` sends requests through the actual
course UI, using an authorized Playwright storage-state file. It checks POST
`/ask-stream`, HTTP status, real deltas, terminal `done`, stream errors and known
clarification/failure responses. It records first-delta and completion timing.
It preserves existing history and appends real test messages.

Example in an environment with authorized session and browser/network access:

```sh
python scripts/verify_authenticated_study_stream.py \
  --course-id 3 \
  --storage-state /secure/path/dentalai-session.json \
  --report artifacts/browser-study-stream.json
```

A JSON scenario file can replace defaults with course-specific topics and
`answer_contains` assertions. Test the three presets, natural equivalents,
single-question answer/wait, free-text answers, grouped answers, follow-up
explanations, multiple requested facets and topic switches against actual notes.
Do not commit authentication state. A login in a separate personal browser does
not create a session in this execution environment.

The current environment has no usable authenticated DentalAI session or shared
interactive browser. Previous browser execution attempts were blocked. The
verifier has been syntax/CLI checked, but has not been run against production.

## Indexing duration

The observed `Academic Modal wake ... elapsed_ms=4020` is dispatch duration only.
It is not upload-to-READY indexing time. Later status requests do not expose
their READY timestamp in service logs.

Worker instrumentation records per-slice stage/result, work and lifecycle
duration, first-start delay, total age and page count without reopening a worker
session during cleanup. OCR, Modal scheduling and indexing logic are unchanged.
Measure upload, dispatch, worker start, extraction/OCR, persistence/publication
and READY separately before selecting a performance change. A 1.55 MB size alone
does not establish page count or OCR workload, and a 4–5 second total is unproven.
