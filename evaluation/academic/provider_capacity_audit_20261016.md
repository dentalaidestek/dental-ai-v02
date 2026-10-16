# Academic provider capacity investigation — 2026-10-16

## Production changes

- PR 130: bounded, jittered, at most one pre-output retry per copied Gemini provider instance for HTTP 503. Does not retry quota/auth/embedding failures or replay partially emitted streams. Source extraction keeps its existing shared retry budget. Full relevant suite: 762 passed, 32 skipped, 576 subtests passed.
- PR 131: configurable single Academic generation model; planner already configurable. No provider chain, indexing, credentials, or account plan changes. Focused suite: 60 passed.
- PR 132: allowlisted upstream error categories; no raw provider message or question logged. Focused capacity and timing suite: 29 passed.

## Live results

| UTC | Model | Stage and result |
| --- | --- | --- |
| 14:43–14:44 | gemini-3.5-flash-lite | Planner succeeded; source retrieval returned three chunks. Final generation returned 503, bounded retry ran, retry also failed. Trace b0a8a387ccf14027b4265bccf040340a. |
| 14:51 | gemini-3.1-flash-lite | Planner returned 503 twice. Trace 3c4da3236c8d48709b1a760289e7e992. |
| 14:53 | gemini-3.1-flash-lite | Table request failed at planner with 503; cooldown prevented another request beyond the six-second recovery waiting budget. Trace fa940a8e223d410a8b8937511cbe8d21. |
| 15:00 | gemini-3.1-flash-lite | Both planner attempts classified `high_demand`, HTTP 503; request payload 20,725 bytes, no source retrieval started. Trace cd0f7a5a6d864e47893fe75acb2644af. |
| 15:03 | gemini-3.8-flash | Both planner attempts classified `high_demand`, HTTP 503; same 20,725-byte request. Trace a2302590a2434ddc90130bef04996146. |

The observed 503 category is provider high demand. It is not evidence of exhausted user credits, OCR failure, or excessive source retrieval. Failed messages return to the input and are not persisted as completed answers. Retry mitigation alone has not restored availability.

## Final disposition

The 3.8 test ran after deploy dep-db93o83rjlhs73e3tao0 became live at 15:02:54 UTC. It did not restore availability. Both planner and generation configuration were therefore restored to the original `gemini-3.5-flash-lite`; there is no evidence that either alternative model is more available for this account. No account upgrade or priority inference enabled. No successful end-to-end response was obtained during this capacity investigation.

The remaining blocker is upstream high demand under the existing Gemini project/key. The logs do not establish whether this is global, regional, project-specific, or transient. Current connectors cannot execute a standalone minimal authenticated provider probe on the Render instance or inspect the Gemini project. Further account/provider investigation is required; do not represent the problem as fixed or rerun the full student-question evaluation while all planner calls fail.
