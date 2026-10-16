# Academic AI Haiku migration

## Scope

Academic request interpretation, source-section extraction, per-file inventories,
source synthesis, practice-question generation/repair, and the legacy bounded
recovery planner use the explicitly selected Academic provider. No silent vendor
fallback or second paid provider call is added. Existing owner/course filters,
source validators, question checks, PDF export, and Modal indexing are retained.

## Activation

Set these together on the existing Render web service after adding a valid key:

```text
ANTHROPIC_API_KEY=<configure privately in Render; never commit>
STUDY_ACADEMIC_PROVIDER=anthropic
STUDY_ACADEMIC_PLANNER_MODEL=claude-haiku-5-5
STUDY_ACADEMIC_GENERATION_MODEL=claude-haiku-5-5
STUDY_ANTHROPIC_EFFORT=medium
```

Until activation, the default remains the existing Gemini configuration. The
provider/model pair is validated; stale Gemini model names cannot be sent to
Claude. Missing credentials fail before a network request. The request-local
planner schema cannot leak into a final prose response. Streaming generation
retains selected original page images/PDFs as well as text chunks.

The medium effort setting is the documented Haiku default. Published highest
effort benchmark scores do not describe this faster setting. Thinking consumes
the existing max-token budget. No guarantee of zero upstream capacity failures
is made. HTTP 529 has the same bounded capacity recovery as HTTP 503; never replay
an already emitted answer. Source sections retain their shared recovery budget.

## Embeddings and indexing

Haiku has no embedding API. Existing Gemini vectors and optional compatible
query embeddings remain intact; most newer FTS-only courses make no embedding
request. This migration does not delete/rebuild indexes, move original R2 files,
change Modal workers, or alter the radiograph-analysis provider. Those are not
Academic language-generation stages.

## Verification

The relevant local regression suite passed: 790 tests, 32 skipped, 576 subtests.
Coverage includes Claude Messages headers and payload/schema transformation,
selected image attachments/history, text-only SSE output, usage accounting,
partial-stream/EOF errors, max-token termination, HTTP auth/quota/overload errors,
one identical pre-output retry, missing credentials, invalid settings, and both
planner/final routing without constructing Gemini.

Live Claude verification is blocked pending `ANTHROPIC_API_KEY`. On 2026-10-17,
the authenticated Render Environment table contained neither that key nor
`CLAUDE_API_KEY`; no linked environment groups were configured. Do not describe
the migration as active until the key, model access, and a complete live answer
have been verified. No secret values were read or committed.

## Primary protocol references

- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/build-with-claude/streaming
- https://platform.claude.com/docs/en/build-with-claude/effort
- https://platform.claude.com/docs/en/build-with-claude/embeddings
