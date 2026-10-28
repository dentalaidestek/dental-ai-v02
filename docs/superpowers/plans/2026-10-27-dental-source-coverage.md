# Dental source coverage Implementation Plan

> Execute inline with superpowers:executing-plans. Source registry research is delegated independently; final review uses a fresh reviewer.

**Goal:** Route dental encounters across all specialty branches to fixed professional and scientific sources, exposing specific gaps.
**Architecture:** Closed semantic taxonomy, explicit source mappings, bounded existing retrieval groups and per-topic coverage returned through final review. Same model provider/call count.
**Tech Stack:** Python, plain JS, pytest, existing Node/Jinja/jsdom harness.
**Spec:** docs/superpowers/specs/2026-10-27-dental-source-coverage-design.md

## Global Constraints
- No main merge/deploy, no provider change or free-form model query.
- Keep existing limits except topic count becomes 24 with explicit overflow rejection; preserve all accepted topics.
- Preserve quote grounding, clinician approval, existing recovery and legacy IDs.

## Review Focus
- Broad references must not imply specific procedure/complication clearance.
- Unfamiliar situations use a branch fallback and preserve uncertainty.
- One available drug source must not hide uncovered prosthodontic/other topics.
- Accepted topics must survive incremental merge and final source reports.
- External queries/URLs must remain fixed and never contain clinical quotes.

### Task 1: Closed semantic branch taxonomy
- [x] RED: tests for branch coverage, topic enum/quote validation, fixed queries, semantic prompt descriptors and >6 topic retention.
- [x] Implement app/voice_exam_taxonomy.py; extend literature exports and core prompt/contracts to 24 topics without changing review_provider.
- [x] Verify full Python suite; keep legacy behavior with no explicit topics. Explicit validated topics remain authoritative over keyword fallback.

### Task 2: Professional routing and topic coverage
- [x] RED: tests for fixed professional source mappings, irrelevant drug-only coverage, source failure and final report forwarding.
- [x] Integrate app/voice_exam_professional.py with source retrieval; attach topic mappings and coverage status; forward to final model/result and render gaps in UI.
- [x] Real bounded source probes for new documents and a non-drug prosthodontic encounter. No real model call unless configured.
- [x] Full Python/Node suites and independent review. Fix important findings with RED→GREEN tests. Document actual limits, commit and publish only changed paths with expected SHA to existing draft PR.


## Execution record
- Existing isolated task branch feature/voice-finish-review reused as explicitly directed; no main worktree changes.
- 15 branches / 65 closed topic IDs, all mapped to documents; legacy IDs retained. 24 topic limit with explicit overflow, unchanged context/source budgets.
- Independent source-registry work: 26/26 real HTML probes and three offline contract tests. No PDF parsing or full guideline ingestion claim.
- RED→GREEN: schema/quotes, authoritative selection, fixed queries, >6 context and incremental retention; professional routing/irrelevant-drug coverage/final forwarding; jsdom visible gap display.
- Review fixes: explicit systemic-risk routes and legacy fixed safety supplement; empty-topic caller forwarding; clinical discovery terms instead of generic ID tokens; transcript-anchored topic retention with explicit grounded withdrawal. All reproduced before correction.
- Task 1/2 verification: 219 Python tests, two existing warnings; 11 Node harness files on26.12.1 passed. Real prosthodontic probe returned three professional documents with scientific gaps explicit. No actual model configured, no real microphone/browser, no remote CI success claim.
- Ruling: authoritative semantic topics control clinical routing; pre-existing deterministic systemic-risk document safeguards remain supplementary. They do not count as another branch's coverage. Removing them would regress previous risk handling.
- Ruling: general branch documents are only related material; exact diagnosis/procedure correctness remains unverified. Full source corpus/clinical validation is outside the bounded software implementation.
- No merge/deployment. Publish changed files atop the existing PR branch using an expected-SHA update.
