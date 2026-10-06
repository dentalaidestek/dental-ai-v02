# Course retrieval and conversational study verification

Status: draft implementation; production verification is pending. No deployment,
successful authenticated browser stream, indexing speedup, or model fine-tuning
is claimed.

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

31 focused source/dialogue tests, ten recovery tests and 59 existing continuity checks pass. Two
benchmark audit checks pass, and changed Python files compile. Focused tests
include source requests with spelled counts, unknown named topics inside notes,
free-text quiz answers, task rejection, clinical noun protection, compound
topics, and sole-topic versus previous-topic references.

Conversational control checks additionally cover learner-practice requests,
study-program requests, comprehension repair with/without prior topic, courtesy
messages that bypass candidate retrieval, and pending-question continuity across
a courtesy exchange. These routes do not classify every message as a new topic.

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
