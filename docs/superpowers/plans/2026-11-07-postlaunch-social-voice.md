# Postlaunch social and voice reliability implementation plan

User authorizes finding and fixing the launched expert-social and voice flows, preserving consulting, minimizing cost, private data exposure and interface clutter. Reference is the supplied two-panel profile image. No new paid infrastructure. Implement on feature/postlaunch-social-voice-20261107; prepare a reviewable PR for new code. Existing approved PR250 deployment repair is separate.

Baseline: main565df06a7b7775d2ec2466656ee92b497d2cdf58, tree0d97c4ba0e36a956356ed1dffb17a88a7df4057f. Actual Render failed18:21UTC with missing dental_social_revision; live service still802c28. Actual Render free-plan service is not synchronized with starter/preDeploy settings in render.yaml.

## Deliverables

1. Repair approved release deployment with existing bounded serialized startup-migration compatibility flag; verify missing-table upgrade on isolated PostgreSQL first. Preserve other envvars and plan/cost. Verify deploy state and /readyz. Document config drift and startup overhead; new code must not be silently deployed.
2. Backend social audit: reproduce/fix actual authorization, DB-pool pressure, bounded ingestion/external I/O defects. Own API/models/schema/safety/maintenance and focused tests. Verify schema readiness and no access to pending/clinical media.
3. Voice final audit: Claude receives the transient bounded/redacted full conversation and structured context, never raw full transcript in patient persistence or source queries. Preserve closed topic IDs, evidence anchoring, clinician confirmation and two-stage review. Reproduce missing-context and retry/cost behavior with synthetic fixtures; no production patient content or paid tests.
4. UI: wire conversation_text, avoid repeated prompts/actions, align supplied profile reference, keep mobile CTA and existing navigation/consulting, avoid background hidden-tab loading and repeated large draft serialization. Real browser tests at360/390/430/1280; no fake counts/dead features.
5. Capacity: local PostgreSQL experiment with60000 synthetic social rows, bounded concurrency and pool4. Count queries and p50/p95 for representative reads/interactions. No production stress tests. Distinguish60000 registered accounts from60000 concurrent sessions; publish hardware/test limits honestly.
6. Regression/independent review, screenshots, exact test counts and deployment evidence. Commit/push only intended files, create PR from current main with expected-SHA lease. Do not claim all-site or60000-concurrent readiness from a small benchmark.

## Verification checkpoint

Approved main deployment repaired and live, without paid plan changes. New code stays separate. 868 targeted tests pass;5 opt-in skips. Real metadata/API+browser:5pass. Synthetic60000rowcapacity:1pass. Whole repository2202pass/72fail/53skip; failing IDs are a subset of previously recordedbaseline failures. Source corpus restored from exactmainfile after reconstructed checkout gap, not fabricated/changed. Independent review found crosspatient dedupe and logout persistence risks; both corrected and tested. Additive indexes retain social revision2 for rollback compatibility. Newcode requires normal migration to install indexes before readiness. See acceptance report and project-root design-qa.md.
