# Everyday dental speech implementation plan

User requests continued implementation without another approval round. Extend the existing semantic extractor for ordinary dentist/patient language and broader dental scope; keep closed IDs, fixed queries, review_provider and Finish-only processing.

- [x] Add regressions for interpretation guidance arriving in the same extraction call, ordinary-speech examples staying separate from external queries, and specific new everyday concerns with real professional sources.
- [x] Add a compact semantic interpretation guide: speaker/subject, ellipsis, chronology, denial, proposals vs completed work, ambiguous lay terms and clarification. Illustrations guide generalization; they must not become a regex classifier or diagnosis rules.
- [x] Add missing scopes for cracked-tooth assessment, whitening/esthetic concerns, sleep-related breathing, tooth development and dietary risk, with fixed source mapping. Verify new public document access with the existing bounded fetcher.
- [x] Add held-out synthetic natural dialogue fixtures across all 15 branches and a same-provider opt-in evaluator. Default mode validates fixtures with zero network/model calls; never label fixture tests as measured model accuracy.
- [x] Run Python/Node regression suites, review, document limitations and publish to the existing draft PR with expected SHA. No main merge/deploy. No key collection/provider substitution.

Constraints: no extra production model call, no arbitrary model search text/URLs, no actual patient speech in test artifacts, keep quote grounding and explicit source gaps. Real-model evaluation depends on an available configured API key and must report its actual execution status.


Execution evidence: 232 Python tests and 11 Node26 harness files passed; four new sources fetched successfully. 44 synthetic dialogue inventory validated offline, zero model calls. Opt-in real-model attempt failed closed on absent configuration; real semantic success is unverified. Independent review caveat on ambiguity-scoring fixed RED→GREEN. No regex classifier, provider switch or extra production model call.
