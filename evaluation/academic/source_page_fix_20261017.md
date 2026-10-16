# Source-page preparation and long-answer fix — 2026-10-17

Production fix: https://github.com/dentalaidestek/dental-ai-v02/pull/134
Merged main: `5367fef05a99daa2805371bbed06122e68a041ad`.
Render deployment `dep-db9aue7lk1mc73bpq170` became live at 2026-10-16 23:13:24 UTC (02:13:24 Istanbul).

## Reproduced failures

- Trace `34c6d6e9656849db97519b3033b26f4a`: a 20-question request selected 128 evidence chunks and 21 original pages, split between two workers. One worker finished; the other exhausted the old 7,000-token output budget (`MAX_TOKENS`). Adaptive thinking consumes that budget too.
- Trace `6b34efdab2184870a598d0d34547cce5`: page preparation reported missing original pages. The page cache holds 12 entries, while one worker needed 16 pages. Loading early misses evicted later hits before consumption; those hits had not been loaded from the database because they were initially cached.
- A regression test failed before the fix with pages 5–8 missing. The new tests cover eviction during preparation, eviction by another worker, and repeated preparation without duplicate attachments.

## Changes and automated verification

`materialize_visual_sources` now pins the request's initial cache hits under the existing lock, calculates database misses from that snapshot, and skips already prepared pages. Existing cache size, request attachment limits, ownership checks and version checks remain in force.

Claude source-batch extraction and question requests of at least 10 questions now receive a 16,000-token output budget. Ordinary short answers retain their prior budget. Question repair uses the same selected budget; this change adds no automatic model call.

Relevant full test run: **797 passed, 32 skipped, 576 subtests passed** (14.26 seconds). `git diff --check` passed.

## Post-deployment live check

Course: Perio didem, course 6. Sent a request for 20 challenging multiple-choice questions, A–E options, continuous numbering, and no answer key before the student replies.

Trace: `f11dd524215848e0b6353cad0a594355`.

| Stage | Result | Duration |
|---|---|---:|
| Planner | STOP | 9.735 s |
| Source worker, 16 attachments / 82 evidence chunks | STOP | 50.461 s |
| Source worker, 5 attachments / 46 evidence chunks | STOP | 28.574 s |
| Final synthesis | STOP | 47.423 s |

The two source workers ran concurrently. Four model calls total; no retry or repair call was logged. Final response completed at 23:15:39 UTC, about **114 seconds** after planner start.

DOM verification found exactly question numbers 1–20, and 20 instances of each A–E option label. The answer key was withheld and the send button was enabled again. No page-preparation error or output-limit failure occurred. The response explicitly excluded an IDEATHON promotion file as unrelated academic content; all four files were considered, not all four used to create questions.

Screenshot captured after completion: `dental-perio-20-complete-1792192690688.jpg`, showing questions 19 and 20 and the ready composer without the error.

This verifies the previously failing workflow and output structure. It is not an independent factual audit of all 20 questions. The approximately two-minute latency remains a limitation; this fix does not establish that broad requests are fast.
