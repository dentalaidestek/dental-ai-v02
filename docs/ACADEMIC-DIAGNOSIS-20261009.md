# Academic screenshot diagnosis — 9 October 2026

Read-only diagnosis against local application code after chat commit 29c96de. No paid model/OCR jobs, uploads, configuration changes or deploys started.

## Reproduced request understanding failures

- `Notlardan 15 çok zor soru üret`: operation is generate_questions, but course_source_request is false and requirement subjects contains `15 çok zor`. The source-operation modifier grammar accepts zor but misses çok, leaving output constraints as topical search text.
- `Kral bana her bir konudan ders oluştursana`: no study operation is recognized; subject is the remaining request clause. Lesson creation/course scope needs a shared grammar rule, not a hardcoded response for this screenshot.
- `Nedir bu yüz tipleri`, with prior user Downs analysis request and assistant explicitly mentioning three face types: resolve_followup_query returns the unchanged query. The referent loses its owning Downs topic.
- Provider identity question becomes a dental retrieval subject. Such system questions need a deterministic, truthful metadata response outside note search.

The shown repetitive refusal is produced by evidence_followup when retrieval has insufficient evidence. This branch returns without calling final generation. It does not prove Gemini generated the faulty wording or that the note lacks the requested facts. Reduced-context absence must not be presented as exhaustive absence from all uploaded notes.

## Indexing code facts and unknowns

- Text extraction quality gate routes empty, short, corrupted/fragmented text to OCR. The short-text threshold can send legitimate title pages to OCR; actual counts were not measured.
- OCR is local Tesseract Turkish/English with PDFium rendering, layout handling and optional higher-resolution retry. Confidence is an internal heuristic, not proof of medical term accuracy.
- OCR slices reuse one PDF document but process bounded pages serially. Runtime depends on pages needing OCR, retry rates and compute allocation; 15 MB alone does not establish expected latency.
- New retrieval path uses local FTS and no query embedding request. Verification/publication do not require embeddings. Adding GPU/embeddings before fixing query understanding is not justified by these screenshots.
- The repository exposes an authenticated Modal wake dispatcher but no callable Modal deployment definition was found in the targeted source inventory. Actual Modal CPU/RAM allocation, idle lifetime, overlapping invocations, billed duration and deployed code version remain unverified.
- Render filtered logs for 15:15–15:40 UTC returned no matching records. This is not evidence that indexing did not run.

## Needed evidence before cost/quality conclusions

Original problematic PDF and its indexed page/chunk outputs; per-page extraction method, OCR time/retry/confidence; job stage durations; retrieved chunk IDs/pages for failed queries; Modal function usage breakdown and deployment source. No patient data or credentials are needed in screenshots.

Priorities: fix task/context routing with bounded regression tests; compare reference PDF text to OCR and retrieved chunks; attribute costs by stage and invocation; optimize duplicated work or idle compute only when proven, preserving completeness and user access. Earlier chat fixes remain prepared and undeployed.
