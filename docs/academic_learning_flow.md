# Academic study flow

The web composer creates a private `StudyRun` and polls its owned status. Two
event-woken execution threads process the durable queue in source order. There
is no always-running model poll, new worker service or automatic paid retry.
Queue admission deduplicates request keys, permits one active request per course
and two per owner, and bounds waiting work at 64 globally. These are single-process
resource bounds, not evidence of capacity for 60,000 concurrent users.

The existing authenticated request pipeline remains the only generation path.
The worker loads its recorded owner from the database, never a saved session
cookie. It calls the internal owned function; callers cannot supply an owner to
the public HTTP route. Ownership, active account, current sources and chat epoch
are checked again before committing the final message. The message and run's
completion pointer commit atomically. Partial text is a bounded progress record,
not a completed chat answer. It is checkpointed at most once per two seconds.
Internal file manifests are never sent as partial progress.

Closing a browser does not cancel a run. Returning finds active work; completed
work is already in chat history. Failed or stale/interrupted runs never silently
restart a paid call. After a process crash, a run with no update for 15 minutes
becomes interrupted and needs an explicit new submission. Browser status polling
slows while hidden and stops on completion. Original synchronous/stream APIs stay
compatible; durable completion is provided by the new composer/run route.

`StudyLearningState` retains the active task and validated quiz reference outside
the eight-message window. The exact quiz is version/hash-validated against its
owned message before use, and is sent only once in the planner input. It is not
reinterpreted from an unrelated PDF or an old visible question list. Clearing a
chat resets this context and cancels outstanding work, preventing resurrection.

`StudyAttempt` deduplicates repeated submissions for the same saved set/answers.
`StudyReview` stores practiced facts, right/wrong counts, a streak and next review
time, scoped to owner/course/source versions. A wrong answer is due in ten
minutes; correct streaks schedule 1/3/7/14/30 days. This is a simple scheduling
heuristic, not a clinical or scientifically validated mastery score. Source
changes hide obsolete records from current progress. New questions about weak or
due facts still retrieve current source notes; learning history is not factual
evidence. Scoring and progress updates make no extra model call. Blank answers do
not pretend to be demonstrated knowledge. Course/account erasure purges all new
records; a new conversation keeps review history but resets the active task.

The Teach shortcut requests one short explanation, a source-backed example and
one understanding check, then waits. On a large course it starts with the first
lesson batch instead of synthesizing the entire course. Further teaching uses
the student's response and the persistent task context. An explicit request for
a detailed full lesson remains available through ordinary language.

New question sets carry source topic and statement-quality metadata. For
multi-statement questions the parser checks actual displayed Roman-numeral
options against their declared combinations and checks the answer letter against
the requested true/false statement set. Distinct-topic requests reject repeated
topic labels. These checks catch structural/key inconsistencies, not every
medical factual error or semantically disguised topic duplicate. The model must
check source truth and explanation consistency in the same generation; at most
one existing repair is allowed. Old saved question sets remain readable.

Migration: run `python -m app.migrate` before serving this release. The v12 fast
path creates only the four independent new tables under a transaction-scoped
advisory lock. The global baseline revision stays 12 so existing OCR/clinical
workers remain compatible. New web startup additionally checks for the study
tables. On the existing free Render service the authorized one-shot startup
migration flag can run this before readiness; no paid pre-deploy service is added.

Acceptance checks include request deduplication, client-close completion, no paid
failure retry, foreign access rejection, clear-during-flight cancellation, atomic
message/run completion, source-version invalidation, legacy PDF quiz continuity,
review scheduling and erasure, premise/key mismatch rejection, and idempotent
additive migration. Local provider mocks establish these contracts, not superiority
over ChatGPT. Live latency, token use and source accuracy must be measured on real
requests. A controlled ChatGPT learning-outcome comparison remains separate;
neither passing unit tests nor a successful PDF proves better learning.
