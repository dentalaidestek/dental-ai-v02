# Claude PDF workspace

`STUDY_REMOTE_PDF_ENABLED=1` enables Anthropic Files API, server code execution
and the built-in `pdf` skill for academic PDFs. The default is off. It requires
the existing `ANTHROPIC_API_KEY` and `STUDY_ACADEMIC_PROVIDER=anthropic` settings.
The configured generation model is checked with Models API before any upload;
the required capability is `capabilities.server_tools.code_execution.supported`.
No SDK, new database table, worker service or dependency is required.

The existing interpretation call chooses opaque keys from an owned chronological
PDF catalog, including the first original PDF and uploaded course PDFs. It sends
the original request and contextual edit instruction to Claude's isolated file
workspace. Legacy text-only PDFs are uploaded as their full authoritative text;
they are not rendered on the web service. Existing binary PDFs are uploaded as
files. Legacy page-edit recipes are reconstructed in Claude's workspace from
their owned sources and a server-built document plan, without local rendering.
Text-only legacy documents preserve their content; their original pagination
must be checked in the live visual evaluation. Plain generation and quiz generation retain their current source grounding
and validation, then export the completed answer in a separate Claude file call.
This extra formatting call consumes tokens; it is not a free local conversion.
`pause_turn` may resume at most twice, with a 240-second message-execution budget.
There is no provider fallback and model-written code is never executed locally.

Final PDFs are downloaded once, validated and stored through existing private
object storage. Downloads authenticate the owner/course, recheck source
dependencies and serve the stored bytes without another AI call or PDF render.
Quiz PDF exports verify unchanged stems and option order before retaining a key.
Editing question wording requires a new validated question set rather than silently
reusing the old key. Existing course-index readiness requirements still apply.

Uploaded provider files have one-hour expiration and are deleted after the job.
Acquired provider file IDs are registered as delayed durable `StudyDeletionJob`
records before use. The existing deletion worker must be consuming these jobs
before enabling the feature. Failed deletion retries through that worker;
raw provider IDs never go to clients, model instructions or conversation history.
Each request starts a fresh container; no container ID is persisted or shared
between users. Chat clearing, course deletion and account erasure queue stored
output deletion. Uncommitted files are removed or queued for cleanup.

Limits: 8 source files, 32 MiB per source and 64 MiB total source bytes, 8 final PDFs, 8 MiB per output,
32 MiB total output bytes, 500 output pages, two concurrent file jobs per process.
These are process bounds, not a distributed capacity or 60,000-user guarantee.

Files API operations are free. Token usage remains billable. Code execution has
standard execution-time pricing and an organization-level free allowance. No web
search/fetch tool is enabled solely to change billing; note-only grounding is kept.
Check the account's actual allowance before estimating production costs.

References verified 2026-10-18:

- https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- https://platform.claude.com/docs/en/build-with-claude/skills-guide
- https://platform.claude.com/docs/en/build-with-claude/files
- https://platform.claude.com/docs/en/about-claude/pricing

Rollout: run local regressions, review the isolated PR, then merge/deploy with
scoped approval and enable the flag. Verify a paid live request to restyle the
first original PDF, inspect its downloaded pages and measure actual usage. Unit
tests simulate Anthropic HTTP/file responses and are not a live skill evaluation.


Existing-PDF follow-ups also support `output_format=text`: the planner supplies the
owned generated file and relevant uploaded source PDFs to the same isolated skill.
The skill must actually inspect the files before returning a text answer; no new
PDF is created for a normal short inspection. Source references are revalidated
after processing. Requests to expand/update a summary remain PDF jobs, with the
original summary and required full source documents supplied together. This avoids
asking users to paste the text of a PDF the application already owns. Coverage
claims must distinguish supplied readable sources from missing/unreadable material.
