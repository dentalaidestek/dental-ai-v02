# Progress — 2026-10-26-voice-finish

Base: upstream 180170ddcc9963505712f6719293ea073727dfe0; local snapshot commit 50284ba. Direct git clone has no credentials; use authenticated GitHub API and publish only changed paths atop upstream tree.
User explicitly requested implementation after agreeing on this flow; proceed without a new approval round. No deployment.
Tasks 1–3: complete. Local verification: 187 Python tests; 10 Node harnesses; syntax checks and git diff --check passed.
Independent review: five Important findings fixed with RED→GREEN regressions: failure-cache recovery TTL, standard EFetch DOCTYPE acceptance, invalid/incomplete EFetch batch preservation, local closed-topic fallback, transcript soft-limit resume gate. No Critical findings.
Ruling: retain the explicit clip-upload extraction tool while changing the main live path, matching the user's live-flow scope.
Ruling: local catalogue is opt-in until a real populated snapshot is validated; other source groups retain network behavior.
Ruling: recovery stays in the open page only, avoiding durable full-transcript storage; navigation warns and clears private data.
Limitations: no real microphone/provider/catalogue or production load validation; complete repository CI runs on the draft PR.

## Continuation requested by user
- Unified current clip upload/recording with the Finish-only path using an opt-in transcription-only audio response; backward compatibility is retained for older clients. This supersedes the earlier clip-scope ruling.
- Added cached pending clip transcription so over-limit append correction does not retranscribe; prior speech survives STT errors and pending audio blocks clinical processing.
- Fixed premature live shutdown on first final fragment, preserved incomplete flush status across pause/error, and bounded a missing-end-response wait. Three-second drain remains a heuristic awaiting real-device/provider validation.
- Fixed all-source outage handling before model charge, partial-source retry eligibility including drug sources, and unchanged-evidence retry without another model call. Fingerprint also binds clinical context/prompt/model to prevent reuse after edits.
- Second independent review found drug failure classification and unchanged cached evidence charge issues; both repaired with regression tests.
- Verification: 194 Python tests + 10 Node harnesses passed; two dependency deprecation warnings. Direct PubMed ESearch timed out; hosted web fetch also could not access EUtils, so no real catalogue was populated.


## 2026-10-27 handoff completion
- Confirmed local branch `feature/voice-finish-review`, starting HEAD `4199a53`, and remote draft PR #216 head `44ef35231aeb15c8d2a13a4123bfad34fca505d0` on `work/voice-finish-review-20261026`. Preserved the existing uncommitted timeout, panel version and workflow work.
- RED→GREEN: added integrated DOM coverage for the manual `/clinical` request budget (observed 30000 vs expected 120000 before fix), then included `/clinical` with `/text` and `/audio` at 120 seconds. Finalize stays 150 seconds; other requests 30 seconds. Draft retention and timeout retry also pass.
- Reproduced 195 passed / 2 failed from shared-cache pollution; fixed only the concurrency test fixture with fresh OrderedDict/in-flight map/private BoundedPools. Shutdown waits for group and document tasks before monkeypatch restoration. Production source behavior was not altered to hide test contamination.
- Final local verification: 197 Python tests passed in 5.16 seconds (two existing upstream deprecation warnings); 11 Node harness files passed, zero failures. Runtime actually reports v24.22.1 in this session, despite the earlier Node 26 handoff claim. Workflow requests Node 26 as instructed; current Node 26 execution is unverified. `git diff --check` passed.
- CI changes: jsdom 30.1.3 installation/NODE_PATH, Node 26, voice CSS path trigger. Panel uses voice-exam.js?v=15.
- Integrated Jinja/jsdom coverage is synthetic; no real browser/microphone/provider test. The earlier Chromium archive was corrupt; PubMed retrieval timed out, so no real catalogue is validated. Source concurrency 1/5/20 tests do not establish production throughput. Remote Actions is not claimed green and its earlier pre-step failure cause remains unknown.
- Preserve `review_provider`, closed taxonomy lookup, explicit clinician save approval and open-page-only recovery. No main merge or deployment. Publish only the changed paths atop the current remote tree using an expected-SHA ref update; local snapshot history is intentionally separate.


## 2026-10-27 additional validation
- Closed the Node-version gap: installed official Node 26.12.1 outside the repo after SHA-256 manifest verification; 11/11 Node harness files passed with jsdom 30.1.3. Fresh Python run: 197 passed, two existing dependency warnings (4.81 seconds).
- Real fixed-topic PubMed pilot succeeded twice. Final check built an atomic temporary catalogue for `endodontic diagnosis`, two records, then retrieved both with the actual local read-only path and no unavailable markers: pubmed-37772327, pubmed-39206581. Temporary database deleted. Full catalogue, all-topic coverage and clinical accuracy remain unverified; do not enable local mode in production from this pilot.
- Remote voice run 40459475190 on 9d4d5a9 failed before steps, runner_id=0 and empty runner name; logs 404/BlobNotFound. Other workflows also failed before steps. Exact cause remains unavailable through the connector (check annotation endpoint unsupported). Do not guess quota/billing/code cause or claim CI green.
- Fresh Chromium download returned 195 bytes of HTML instead of ZIP; no browser binary is installed. No real microphone/browser test. Existing review-provider configuration has no API key/model in this runtime, so no paid real-model call was attempted. Provider wiring unchanged.
- Follow-up only updates validation records and the existing draft PR. No merge/deployment.


## 2026-10-27 all-source follow-through
- Audited all 12 fixed documents (9 ADA, SDCEP, NHS SPS, GDC): all yielded excerpts via the production fetcher. Acute pain page excerpts are mainly descriptions/links, not proof of full guideline coverage.
- Both selected DergiPark OAI catalogues parsed; Selcuk candidate 1903361 is background-only (`clinical_use=False`), ADO case-report candidate 1903339 excluded. Integrated retry later reported intermittent ADO unavailability; no false clinical-clearance claim.
- Live DailyMed amoxicillin/warfarin succeeded; third simultaneous lookup correctly hit two-slot admission capacity, and serial clarithromycin retry succeeded. All eight exact-ID bundled SPL documents were refetched. TİTCK inventory is zero; do not describe the existing corpus as Turkish KÜB coverage.
- Real grouped retrieval took 15.26 seconds, returned 11 references across professional documents/PubMed/live DailyMed/local fallback and preserved DergiPark access/no-clinical-evidence markers as retryable partial coverage. No final model call.
- Found/fixed excipient-as-drug alias bug with failing regressions first. Import now includes only product/explicit active names and active ingredient classes ACTIB/ACTIM/ACTIR with active moieties. Regenerated eight records; all original clinical sections and versions unchanged, six verified Turkish spellings retained. No excipient blacklist or patient-data workaround.
- Final suite: 201 Python tests passed, two dependency warnings; 11 Node files passed on Node 26.12.1; diff checks passed. Workflow watches drug importer/corpus paths. Publish on existing PR only; no main merge/deploy.


## 2026-10-27 multidisciplinary expansion
- User rejected narrow drug/PubMed/example-only coverage. Implemented branch-level semantic fallback plus specific scopes: 15 branches, 65 topics, 38 fixed professional documents; 26 new production fetch probes passed. Existing provider/call topology retained.
- Added per-topic related/background/uncovered status to final model and clinician UI (JS v16); unrelated medication sources cannot cover other branches. No claim of every clinical situation being understood or every procedure evidenced.
- Replaced six-topic truncation with 24-topic bounded retention and explicit overflow. Preserved transcript-only topic anchors; grounded removed_literature_topics supports corrections.
- Independent review findings fixed with RED→GREEN tests: systemic-risk route regression, empty semantic selection lost at callers, generic DergiPark matching, topic-anchor loss. Legacy fixed systemic document safeguards remain separate from semantic branch coverage.
- Latest verification: 219 Python tests / 11 Node26 harness files passed. Real prosthodontic source call returned ADA direct/indirect material and NIDCR TMD; PubMed timed out, DergiPark had no clinical evidence. Full medical/semantic accuracy and actual model/microphone remain untested.
- See specs/2026-10-27-dental-source-coverage-design.md, plans/2026-10-27-dental-source-coverage.md and docs/voice_source_coverage_checks.md. Existing draft PR only; no main merge/deploy.


## 2026-10-27 natural spoken language continuation
- Same extraction call now receives contextual speech guidance: ordinary vocabulary, speaker/subject, region/procedure/time/trigger, negation/family/hypothetical attribution, ambiguous/ASR references and clarification. Examples are not a classifier and cannot become patient quotes.
- Added five common scopes and four actually fetched AAE/ADA documents: registry 70 topics / 42 fixed documents. Queries/provider/call topology unchanged. Guidance adds ~6612 input characters; latency/cost not yet measured.
- Separate synthetic corpus: 44 short dialogues, 15 branches, 45 expected IDs, 49 groups and three clarification cases. Offline default makes zero model calls. Explicit same-provider live evaluator is ready; actual --live --limit1 stopped on missing config, zero calls. No model semantic accuracy claim.
- Reviewer caveat on generic uncertainty accidentally passing ambiguity checks was reproduced RED and fixed; now a grounded CLARIFY_NOW question is required. Topic selection of a hypothetical risk is not evidence of a current complication; fixture corrected accordingly.
- Fresh validation: 232 Python passed, two dependency warnings; 11 Node26.12.1 harness files passed; diff check clean. No main merge/deployment; publish existing PR only.


## 2026-10-28 Claude native web research

This section supersedes the pending native-code status in the 2026-10-27 checkpoint. The existing configured review provider now supplies native public research, followed by the existing patient-specific structured final review. Finish runs extraction, public research, then final review (normally three model stages; a native pause can add one research continuation HTTP request). Successful public research is cached/singleflight; unchanged evidence and clinical inputs skip another final review. Search usage and model tokens have costs; no unchanged-cost claim.

Default `VOICE_EXAM_SOURCE_MODE=claude_web`; `legacy` explicitly selects the previous source engine. No silent fallback or provider substitution. Extraction still interprets natural Turkish dialogue and selects validated closed taxonomy IDs (70 topics across 15 branches). The isolated public research prompt lets Claude choose searches and pages within 18 trusted domains, including ADA, AAE, AAPD, AAP, EFP, AAOMS, ACP, BOS, NHS, SPS, SDCEP, GDC, NIDCR, PubMed/PMC, DergiPark, DailyMed and TITCK. It instructs reading actual source text, prioritizing professional guidance, distinguishing publication types, citing literal passages, and ignoring instructions embedded in pages. This is broad dental routing, not drug-only or PubMed-only research; no exhaustive clinical coverage claim.

Only server-owned public topic scopes and bounded supported generic drug names reach native tools. Raw patient dialogue, quotations, identifiers and private clinical fields do not. Unknown drug names remain explicit gaps and are not forwarded. The separate final review receives private clinical context plus retrieved public text. Evidence must bind a successful native fetch result to an approved HTTPS URL and literal returned text. Model prose and search snippets are never clinical evidence. Topic relevance/clinical entailment still requires judgment: native coverage is explicitly unverified, not automatic confirmation. Unassessed journal text is background only; unsupported PDF/base64 documents are rejected.

Research requests allow at most two searches, three fetches and two HTTP messages; callers wait up to 45 seconds. This is not a hard worker execution or total token/cost cap: transport read timeouts are inactivity limits and provider PDF processing may occur before local rejection. Queue admission is bounded (2 workers/4 capacity), public cache has 64 entries, fetched excerpts are bounded, and native pause continuations preserve returned assistant blocks.

Reproduced the remaining P1 with failing tests: no-topic/completed-empty/unsupported-format gaps were mislabeled as transport failures and blocked Finish. Native permanent gaps now use `web-research-gap` / `web-fetch-gap`; actual configuration, provider, capacity and incomplete-research failures remain retryable. A routine no-topic encounter can reach final summary/clarification without a research call; invented source-free clinical items are rejected. Genuine all-source access failures still stop before paid final review. Existing physician approval for saving, draft retention, extraction checkpoints and final fingerprint remain.

Fresh verification: `PYTHONPATH=.:../testdeps python -m pytest -q` — **275 passed**, two existing dependency deprecation warnings, 14.64 seconds. Full `tests/voice*.cjs` run using Node 26.12.1 and jsdom 30.1.3 — **11 passed**, zero failures, 2.26 seconds. Includes mocked native transport, privacy, source provenance, pause/error handling, cache/singleflight, public-research-to-private-final integration, no-topic Finish, all-source failure guard and integrated DOM display. `git diff --check` passed. Earlier `/clinical` 120-second timeout, isolated source pools/cache, Node 26 workflow and CSS triggers remain in place.

Real same-provider evaluation `--live --limit 1` stopped with `missing_provider_configuration`, **model_calls=0**. Native web support and real model output have not been verified against an authenticated provider. No actual microphone/Chromium test; jsdom is a DOM harness. Previous limited real source/PubMed probes do not verify this new native path or a full catalogue. Remote CI remains unverified; no claim of green Actions or guessed failure cause. Publish only to draft PR #216, no main merge or production deployment.


## 2026-10-28 adversarial prompt/output verification

Added 11 adversarial final-review cases exercising the real finalization and grounding validators with synthetic provider replies: invented source/field, translated or unrelated source quotation, fabricated patient quotation, whitespace-only patient/source quotations, empty clinical explanation, ineligible journal and a valid grounded control. Three whitespace/empty-output cases failed before the fix. Both patient/source quotations must now contain non-whitespace text while remaining literal substrings; a blank consideration is rejected with diagnostics. No semantic entailment or clinical correctness guarantee follows from literal matching.

Strengthened public research and final-review prompts: procedure/population/clinical-scope applicability, direct support for the recommendation rather than vocabulary overlap, preserving uncertainty and association versus causation, not inferring procedural fault from general information, and distinguishing publication/update date from retrieval time. Missing version/date cannot justify a latest/current-guideline claim. Tool-budget gaps must remain explicit. Public research cache policy version advanced to v4 so the previous prompt's result is not reused under the revised instructions. These text changes have no measured real-model quality score.

Added 70 parameterized checks, one for every accepted topic ID, through actual public-input normalization/retrieval/parsing with a synthetic native reply. Every ID reaches the public boundary with a scope, patient quote/query fields are excluded, fetched excerpts retain literal provenance, and no automatic topic match is claimed. This tests plumbing/privacy across the topic vocabulary, not the model's selection/relevance for 70 clinical situations.

Fresh full verification: 356 Python tests passed, two existing dependency deprecation warnings, 14.33 seconds. Full Node 26.12.1/jsdom suite: 11 harness files passed, 2.40 seconds. Existing 44-dialogue/15-branch spoken fixture inventory validates offline; it is not a 44-case model accuracy pass. Explicit same-provider live evaluation with limit 5 stopped at missing_provider_configuration, model_calls=0. Real Claude prompt behavior/web access, clinical entailment, microphone/browser and remote CI remain unverified. Diff check clean; existing draft PR only, no main merge/deployment.


## 2026-10-28 deployment/configuration preflight

User now authorizes configuring the existing provider and attempting production deployment; the previous no-deploy restriction is superseded. No main merge was authorized or performed. Render workspace My Workspace (tea-daea8v0u01pc73dmtir0), production service dental-ai-v02 (srv-daeb9d740ujc73ei7gmg) confirmed via connector. It follows main with auto-deploy on commit. Observed live deployment dep-dbe9aljsp5es73bukj90 uses c6ab6f129eb23f9f7db328332f22bb87175300ba. Intended voice revision remains 7187866e01ab0a5cf31ee269a5c3816c2907921a on the existing PR branch, so an unqualified trigger_deploy would deploy the wrong branch/version.

Render events and build logs now establish the cause of the two 24 October failures: pipeline_minutes_exhausted events for dep-dbea47jbc2fs7380vsn0 and dep-dbea0p3bc2fs7380sc50; logs explicitly say the workspace ran out of build pipeline minutes in the billing period. This is a verified historical Render failure, not the cause of GitHub Actions failures; current remaining quota has not been checked. No billing/plan/spend-limit change made.

The available Render connector can merge selected environment variables and trigger the linked branch, but cannot read current environment keys/values or select an exact deployment commit. Browser fallback reached Render's sign-in page; the secure browser-auth request returned declined. Existing secrets/model settings and today's quota could therefore not be inspected, and the exact target commit could not be selected. No environment variable changed, no deployment triggered, no real provider test completed, and no main merge occurred. Existing 356 Python/11 Node validation applies to code; production remains on its observed older revision.
