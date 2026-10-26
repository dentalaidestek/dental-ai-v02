# Finish-only voice examination

User-approved direction: collect transient transcription while listening; run clinical extraction only after the Finish button, then retrieve evidence and run the existing final review. No production merge/deploy.

Keep FastAPI, browser JS, existing ownership/consent/fingerprint/atomic apply and provider budget. No new provider. First extraction chooses only verified closed taxonomy topics with verbatim evidence; no generated search queries. Extend the existing taxonomy with the five endodontic pilot topics while retaining all existing areas. Unsupported situations must not be represented as covered.

Approaches: per-segment extraction is rejected by the user; finish-only extraction reuses existing endpoints and review safety checks; a wholly new server job pipeline would add storage and migration scope. Use finish-only extraction with memory-only browser checkpoints.

Builder choices: maximum 72,000 characters and 216,000 UTF-8 bytes for a transient transcript, extraction chunks of at most 12,000 characters/36,000 bytes. The 24 KB structured context limit remains separate. Split at sentence/whitespace boundaries without dropping text. Retain full transcript and successful chunk cursor on failures in the open page; page close/discard/save clears private state, with navigation warning for unsaved work. No durable transcript storage. Long transcripts can require more than two LLM calls. Button only; no voice command.

Reuse useful first-document proposals: bounded parallel fixed-document requests, bounded queue and duplicate suppression, positive/negative cache, evidence text budget and timing logs without clinical data. Preserve selection fallback and GDC communication triggering, existing clinical prompt safeguards, and response contracts. Refusal analysis is already covered by decision_barriers; preserve it without unverified status assertions.

Local literature index is optional behind an explicit mode and missing-index reporting; legacy remote sources remain the default until the index is populated. Offline corpus build accepts no patient input. No claim of fully offline sources or validated clinical coverage.

Verification: no extraction until finish; end flush; extraction/final failures preserve drafts and do not replay completed extraction; over-limit input never truncated; invalid/unanchored topics rejected; all existing voice tests and Node harnesses; local index no network; source concurrency/queue/cache/budget tests. Full repo verification may require remote CI because this workspace is an authenticated API snapshot of the relevant subsystem.
