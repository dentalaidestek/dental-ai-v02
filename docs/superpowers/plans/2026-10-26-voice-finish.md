# Finish-only voice implementation plan

> Execute inline with superpowers:executing-plans; test each behavior before implementing it.

**Goal:** Defer clinical work to Finish and improve evidence retrieval without changing patient persistence.
**Architecture:** Browser memory draft and extraction checkpoints reuse current text/final endpoints. Closed taxonomy and optional local literature adapter feed the existing source-grounding layer.
**Tech Stack:** Python, FastAPI, SQLite FTS5, plain JS, pytest and Node.
**Spec:** docs/superpowers/specs/2026-10-26-voice-finish-design.md

## Global constraints
- No main/production writes. No new model provider or stored raw transcript.
- 72,000 chars / 216,000 bytes total; 12,000 chars / 36,000 bytes per extraction; 24 KB structured context unchanged.
- Keep all existing clinical safeguards and source-selection fallbacks.

## Review focus
- Last audio flush and interrupted connections must not lose the retained text.
- Editing a transcript invalidates extraction checkpoints; retrying identical text preserves them.
- Source timeout must not allow an unbounded queue or duplicate outstanding fetches.
- Missing local index and unknown topic IDs must report lack of coverage.
- Existing apply endpoint remains consent/ownership/fingerprint protected.

### Task 1: Finish draft and UI
- [ ] Write Node tests for transcript limits, lossless splitting, resume and extraction deferral; observe failure.
- [ ] Add voice-finish-draft.js, wire live events to append only, finish/retry to sequential checkpoint extraction then final review; update truthful UI copy.
- [ ] Run Node draft and UI harnesses.

### Task 2: Taxonomy and local evidence
- [ ] Write tests for closed topics, negated/invalid anchors, SQLite adapter, missing index and catalogue refresh.
- [ ] Add endodontic topics and local index/build tool; preserve existing areas and opt-in rollout.
- [ ] Run Python source/core regression tests.

### Task 3: Bounded source optimization
- [ ] Write cache, duplicate in-flight request, budget and queue-limit tests and observe failure.
- [ ] Add bounded fixed-document parallel retrieval, cache and safe budget plus timing instrumentation, retaining existing prompt and output contracts.
- [ ] Run complete available voice suite, Node harnesses and review diff; publish isolated branch and reviewable PR only.
