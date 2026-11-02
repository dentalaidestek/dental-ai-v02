# Finish-only live examination

The main live microphone path now retains completed transcription segments in the open browser page. It does not call clinical extraction during listening or pause. The Finish button waits for provider flush, then extracts clinical context and verified closed taxonomy topics in bounded chunks, retrieves sources and runs the existing final review. Alternative 90-second clips now also request transcription only and append to the same draft; clinical extraction is deferred to the explicit evaluation/Finish action. Legacy API clients without the new header keep the old response contract.

## Draft lifecycle

- Full transient transcript: at most 72,000 JavaScript characters / 216,000 UTF-8 bytes accepted for processing. New listening is blocked at 60,000 / 180,000 to leave space for buffered final speech.
- Extraction chunks: at most 12,000 characters / 36,000 bytes, split losslessly at whitespace where possible. The existing 24 KB structured-context cap remains separate. Over-limit context reports an error and retains the transcript; it is never silently truncated.
- Successful chunk cursor survives extraction failures in the open page. Final-review retry does not repeat extraction. Editing/replacing transcript invalidates extraction checkpoints. Editing extracted fields invalidates the final result and preserves clinician edits.
- No browser or server transcript persistence. Discard, save or navigation clears transient data; unsaved navigation warns. Closed/reloaded pages cannot recover the transcript. Failure recovery is only within the open page.
- A normal short examination uses one extraction plus one final review, excluding transcription. Longer examinations need additional extraction calls. Unchanged partial-source retries skip the final model using a fingerprint bound to clinical context, prompt, model and public evidence (excluding retrieval timestamps). Total source outages stop before the final model. Explicit retry of an ambiguous provider/network timeout may still incur another provider charge; this change does not provide server-side idempotency.
- After pause or connection failure, an incomplete flush remains incomplete; pressing Finish cannot certify it. The server drains finalized segments for a bounded three-second window instead of closing after the first segment. An eight-second client watchdog exits a hung stopping state. This is a bounded heuristic, not proof of complete real-provider speech capture.
- No speech-triggered Finish command. An unconfirmed final flush requires the clinician to inspect the text and explicitly run evaluation.

## Closed source topics

Existing sixteen areas remain available. Five explicit endodontic topic IDs were added: instrument separation, root perforation, missed canal, postoperative pain and irreversible pulpitis. IDs are in the extraction schema enum and validated by the existing normalization/context contracts; original speech quotes are required. Fixed search strings are server-owned. No model-authored free-form literature query is introduced. The drug lookup still uses its existing validated ingredient vocabulary.

Topic selection is not diagnosis. Absent, historical or uncertain findings must not become confirmed patient findings. Unsupported conditions remain outside this bounded taxonomy. Real clinical recall and source-query quality have not been established by the software tests.

## Source retrieval

Fixed documents use 6 workers and at most 12 admitted jobs. Source groups use 4 workers and at most 8 admitted jobs. Shared outstanding document requests prevent duplicate fetches. Waiting ends after 12 seconds for documents / 16 seconds for groups; running threads cannot be forcibly killed and retain admission slots until completion. These are wait budgets, not an end-to-end execution guarantee. Local drug fallback and model review are separate stages.

Successful documents cache for one hour; failures cache for ten minutes. Total source excerpt text is bounded to 40,000 characters and final prompt+data to 80,000 characters. Omitted source text is reported as unavailable; grounding uses the same included excerpts. Existing keyword fallback, GDC communication selection, clinical prompt safeguards and response fields remain intact. Timing logs contain counts/durations rather than clinical text.

## Optional local PubMed catalogue

Default remains `VOICE_LITERATURE_MODE=remote`. For a pilot, build an offline snapshot with:

```sh
python -m scripts.build_voice_literature --db /persistent/literature.sqlite
```

Set `VOICE_LITERATURE_MODE=local` and `VOICE_LITERATURE_DB` only after reviewing and validating a populated catalogue. Local retrieval uses verified topic memberships ranked by evidence level/date; it never sends patient text to PubMed or falls back to network on a missing/corrupt index. This setting changes only the PubMed layer: other existing source groups can still make network requests.

Build uses all 21 closed topics and at most 200 relevant PubMed records per topic, without an arbitrary publication-date lower bound. Full abstract sections are retained; existing eligibility metadata still restricts clinical use. A complete replacement drops stale records and topic memberships. Transport/error envelopes or incomplete fetched PMID batches abort publication, preserving the previous file. All source metadata is a selection aid, not a guarantee of scientific quality or clinical applicability. A genuinely successful empty search can remove a topic; inspect the build report before rollout. Weekly scheduling and durable storage placement are operator rollout steps, not installed by this PR.

## Verification

232 Python tests and 11 Node controller/worklet/DOM harness files passed locally, using pinned web dependency versions for the tested subsystem. Tests include closed topics, source grounding, ownership/consent/atomic apply, lossless splits, checkpoint recovery, no mid-speech extraction, source queue/cache bounds, normal PubMed XML headers and error-batch protection. Two upstream deprecation warnings remain. All 11 harnesses passed on both the bundled Node v24.22.1 and a separately downloaded, SHA-256-verified official Node v26.12.1 runtime with jsdom 30.1.3. CI requests Node 26. Independent code review findings were repaired with regression tests.

This workspace contains the voice-subsystem snapshot, not every repository test. A dedicated PR workflow runs all voice Python tests and browser harnesses against the complete checkout. A direct synthetic fixed-topic PubMed ESearch attempt timed out in this runtime, and the hosted web fetch could not access the endpoint. Real microphone, actual model calls, full catalogue ingestion, clinical accuracy and production load are not verified here. A two-record real PubMed catalogue pilot was subsequently verified below. No production merge or deployment is performed.


## 2026-10-27 continuation verification

- Added bounded client request timeouts: final review 150 seconds; text/audio extraction and manual clinical review 120 seconds; other controller requests 30 seconds. Timeout errors preserve the open-page draft and release controls for explicit retry. These browser wait limits do not cancel remote provider work or guarantee charge-free retries after ambiguous timeouts.
- RED: the integrated DOM regression observed `/clinical` receiving 30,000 ms instead of the required 120,000 ms. GREEN: adding that endpoint to the extended budget passed the regression.
- Reproduced the full Python failure before isolation: 195 passed, two failed (`test_official_sources_do_not_use_academic_or_transfer_patient_data`, `test_sources_fail_closed_without_claiming_safety`). Synthetic concurrency results had polluted the shared document cache. The concurrency fixture now monkeypatches a fresh OrderedDict, in-flight dictionary and private 6/12 document and 4/8 group pools for each case, drains groups then documents before restoring patches, and leaves production source code unchanged.
- The new integrated jsdom harness renders the actual Jinja panel and loads both controllers plus the draft helper. It covers listen/pause/finish, duplicate Finish, approved save, disconnected recovery, unchanged/failed partial-source retry, extraction timeout draft retention/retry and the manual clinical deadline. This is simulated DOM/media/provider validation, not a real browser or microphone test.
- Synthetic source saturation cases at 1, 5 and 20 concurrent reviews passed. They test bounded admission/shared work, not real provider capacity or production load.
- The dedicated workflow installs jsdom 30.1.3, requests Node 26 and triggers on voice CSS changes as well as JavaScript changes. Panel script version is v15.
- Commands: `PYTHONPATH=.:../testdeps python -m pytest -q` → 197 passed, two dependency deprecation warnings; `PYTHONPATH=.:../testdeps NODE_PATH=../domdeps/node_modules node --test tests/voice*.cjs` → 11 passed, zero failed (Node v24.22.1); `git diff --check` passed.
- Chromium installation previously failed because the downloaded archive was corrupt. Real microphone/model end-to-end behavior, real PubMed catalogue ingestion and clinical accuracy remain unverified. Prior Actions runs failed before test steps; the cause is not established and remote CI is not claimed green. No merge or production deployment.


## 2026-10-27 follow-up: Node 26, real PubMed pilot and remote CI

- Downloaded official Node v26.12.1 and verified its archive against the release SHA-256 manifest before extraction. Re-ran all 11 Node harness files on that executable with jsdom 30.1.3: 11 passed, zero failed. Re-ran Python: 197 passed, two existing dependency deprecation warnings (4.81 seconds).
- Real network pilot used the existing builder with one closed topic (`endodontic diagnosis`) and `per_topic=2`, without patient input or model-generated search terms. ESearch/EFetch returned two eligible records, atomic SQLite publication succeeded and the read-only local retriever returned both with no unavailable markers. Retrieved IDs: `pubmed-37772327` (guideline), `pubmed-39206581` (systematic review). Both carried clinical-use metadata; clinical applicability was not independently reviewed. The temporary pilot database was deleted after verification. This verifies this small ingestion/retrieval path, not all 21 topics or the full 200-record-per-topic build; local mode remains opt-in.
- For remote commit `9d4d5a9f69abe81b45f046c63e339f7d3bcddc3e`, voice run `40459475190` failed in two seconds before any steps: `steps=[]`, `runner_id=0`, empty runner name. Academic and vision workflows also failed before test steps. Voice job logs return 404/BlobNotFound. The connector does not expose the check annotation endpoint, so the specific pre-run cause remains unconfirmed. No billing, quota or workflow-code cause is inferred; remote CI is still not green.
- A fresh Chromium download probe returned HTTP 200 with only 195 bytes of HTML, not a ZIP. No local browser binary was found. Real browser/microphone validation remains blocked. The existing review provider's API key and explicit model configuration are absent from this runtime; no actual model call was made and the provider connection was not changed.
- No source behavior changes, merge, deployment or production catalogue activation in this follow-up.


## 2026-10-27 complete source-group audit

All probes used fixed public document URLs, closed topic IDs or generic drug names; no patient conversation and no paid model call was sent.

| Source group | Actual probe | Result / limit |
| --- | --- | --- |
| ADA | All nine configured documents | All returned five nonempty excerpts each. Page retrieval is not full guideline coverage; the acute pain landing page primarily provides guideline descriptions/links. |
| SDCEP | Configured prescribing interaction document | Five excerpts retrieved. |
| NHS SPS | Configured macrolide/statin document | Five excerpts retrieved, including actual interaction paragraphs. |
| GDC | Configured communication standard | Five excerpts retrieved. |
| DergiPark Selcuk Dental Journal | OAI catalogue and candidate 1903361 | Catalogue and article metadata parsed. Narrative review retained as background, `clinical_use=False`; no clinical evidence claim. |
| DergiPark ADO Klinik Bilimler | OAI catalogue and candidate 1903339 | Catalogue parsed; case-report candidate correctly excluded. A subsequent integrated cold request reported this journal unavailable; successful standalone access does not prove reliable latency. |
| Live DailyMed | amoxicillin, warfarin, clarithromycin | All returned versioned identities and ten excerpts. Three simultaneous probes hit the configured two-lookup admission limit for clarithromycin; explicit serial retry succeeded. |
| Local drug fallback | All eight exact-ID public SPL documents | Refetched from DailyMed and reparsed. Clinical section payloads and versions match prior records; inappropriate excipient aliases removed. |
| TİTCK | Current corpus inventory | Zero records. Loader allows this host, but no Turkish KÜB connector or populated TİTCK corpus is established by this PR. |

A real integrated `sources.retrieve` call exercised document, PubMed, DergiPark and requested-drug groups plus local fallback in 15.26 seconds. It returned 11 references: four professional documents, four PubMed abstracts, two live DailyMed labels and one distinct local label. DergiPark produced no clinical evidence for the selected endodontic/anticoagulant topics and one journal access failure; these remained explicit unavailable markers and enabled retry. Reference count is not evidence quality or completeness. No final model review ran.

The audit exposed an importer defect: inactive SPL ingredients (water, magnesium stearate, titanium dioxide and others) became drug aliases, causing unrelated labels to match. Added RED→GREEN regressions and restricted ingredient names to explicit active classes ACTIB/ACTIM/ACTIR plus their active moieties, product names and verified spelling aliases. Regenerated all eight bundled records from their exact official identities, preserved the six existing Turkish spellings and confirmed all clinical sections unchanged. Water/magnesium-stearate/titanium-dioxide searches now return no labels; amoxicillin/warfarin/ibuprofen/lidocaine/clindamycin matching remains available. The workflow now also triggers on importer/corpus changes.

Post-fix validation: 201 Python tests passed with two existing dependency warnings (4.84 seconds), 11 Node harness files passed on Node 26.12.1, and `git diff --check` passed. This remains bounded software/source-access validation, not comprehensive clinical recall, full DergiPark archive coverage, Turkish product approval validation or real microphone/model end-to-end validation. No merge/deployment.


## 2026-10-27 multidisciplinary scope expansion

The earlier 21-topic/12-document scope was inadequate for general dental encounters. The closed vocabulary now contains 65 topic IDs: 21 legacy IDs plus 44 new scopes across 15 branches, each with a general fallback. Prosthodontics, orthodontics, pediatric dentistry, periodontology, surgery, oral medicine, restorative care, implantology, endodontics, imaging, anesthesia/sedation, emergencies, special care, prevention and orofacial pain are represented. A finite taxonomy is not a promise that every diagnosis/procedure is understood or evidence-covered.

The same extraction model call receives Turkish labels, branch names and semantic scopes. It selects specific closed IDs where applicable, or the nearest branch fallback for unfamiliar manifestations while retaining specific uncertainty. No free search text or model URL and no additional paid model stage is added; review_provider is unchanged. Valid explicit topic selection, including empty selection, is forwarded to retrieval. Older callers without a topic field retain fallback behavior. A bounded deterministic safety supplement preserves the previous fixed systemic-risk document lookups (hypertension/prophylaxis/macrolide-statin/osteoporosis/anticoagulant/diabetes/pregnancy/prescribing); these documents cannot count as coverage for an unrelated topic.

All accepted topics, up to 24 and the unchanged 24KB context budget, survive context and incremental processing. The old six-topic truncation is removed. Overflow fails with a draft-preserving error. Prior transcript-anchored topics no longer disappear because their exact words differ from a summarized field quote. Grounded `removed_literature_topics` corrections explicitly withdraw topics; mere omission does not withdraw them. This still depends on real model selection/correction quality, which has not been measured here.

There are 38 fixed professional/public-health documents, including 26 additions across ADA, AAPD, BOS, NHS, AAP, EFP, AAE and NIDCR. All 26 additions passed the actual bounded HTML fetch/parser once. Pages may contain only abstracts, patient information or general background; they are not interchangeable with full specialty guidelines. ACP returned an error page to the production fetcher and was excluded. No bypass or arbitrary redirect was added. See `docs/voice_source_coverage_checks.md` for actual source probes.

Each topic now has a source coverage record: related material, background only, or uncovered. This record is sent to the final model and displayed to the clinician. `specific_claim_verified` remains false: locating a document does not verify the specific procedure, diagnose a complication or establish clinician fault. Drug labels cannot cover an unrelated prosthodontic topic. Source groups keep existing bounded workers/waits; topics beyond available evidence or wait budgets remain explicit gaps.

A real prosthodontic retrieval for fixed restorations/cementation/occlusion returned ADA indirect/direct restoration material and NIDCR TMD text in 16.01 seconds. PubMed exceeded its group wait and DergiPark produced no clinical evidence for these topics. The professional paths still returned three references; that is limited related material, not verification of a high restoration or all prosthodontic errors. No real model call ran.

Independent review found unreachable existing systemic-risk sources, empty-topic forwarding, generic-ID DergiPark matching and topic retention gaps. Each was reproduced with a failing regression and fixed. New DergiPark discovery terms come from server-owned clinical vocabulary, not opaque ID fragments such as `general`; a general-anesthesia paper no longer masquerades as prosthodontic/periodontal coverage. Validation: 219 Python tests passed (two existing dependency warnings) and all 11 Node 26.12.1 harness files passed, including visible uncovered-topic output. Real semantic recall, clinical accuracy, full guideline ingestion, full source archives, Turkish KÜB coverage and real microphone/model tests remain unverified. Remote CI is not claimed green. No main merge or deployment.


## 2026-10-27 everyday speech and broader common concerns

The existing extraction call now receives a compact everyday-speech interpretation guide in addition to semantic topic scopes. It asks the model to reconstruct speaker/subject, prior procedure, region, chronology, triggers, denial, proposed-versus-completed work and ambiguous references from the full available dialogue. Lay terms such as “vida”, “takılan şey”, “siniri alındı” and “o parça” are not deterministic diagnosis/keyword rules. Unresolved meaning requires clarification; examples are explicitly forbidden as patient evidence. Family history, hypothetical explanation and explicit negative findings must not become current patient disease. Source topic selection is still not a diagnosis, so a discussed hypothetical risk can legitimately select that topic for evidence retrieval.

Five missing everyday concern scopes were added: cracked-tooth assessment, whitening/esthetic concerns, sleep-related breathing, dental development and dietary risk. The registry now has 70 closed IDs and 42 fixed documents. Four new AAE/ADA pages passed actual bounded production fetch/parsing (cracked teeth, whitening, obstructive sleep apnea, nutrition); pediatric development reuses AAPD developing-dentition guidance. Queries remain fixed server concepts; no patient phrase is sent to external discovery as a query.

`app/voice_exam_speech.py` contains illustrative guidance, while `tests/fixtures/voice_spoken_cases.json` holds 44 separate synthetic 2–6-turn dialogues across all 15 branches. Their 49 expectation groups cover 45 topic IDs and three clarification cases. These are provisional routing expectations, not adjudicated clinical gold labels. Required topic-group recall, specified forbidden routes, unknown returned IDs and literal quote anchors are scored; extra topics are reported as unscored, not automatically deemed false positives. Raw unknown IDs discarded by normalization and clinical entailment are not measured. Clarification cases require a grounded CLARIFY_NOW question; a generic uncertainty/normalizer warning cannot pass them. Question semantic relevance itself still needs review.

Run offline inventory (zero model/network calls):

```sh
PYTHONPATH=.:../testdeps python scripts/evaluate_voice_spoken.py
```

An explicit configured same-provider evaluation uses:

```sh
PYTHONPATH=.:../testdeps python scripts/evaluate_voice_spoken.py --live --limit 5
```

Default live limit is five synthetic cases, with no automatic retry/provider fallback or arbitrary key lookup. Only case IDs, counts and fixed failure categories are printed. In this runtime `--live --limit 1` stopped with `missing_provider_configuration`, `model_calls=0`; no model semantic score is claimed. Production call count is unchanged, but guidance adds about 6,612 input characters, so actual provider latency/cost must be measured rather than assumed unchanged.

Validation after these changes: 232 Python tests passed (two existing dependency warnings, 15.40 seconds), 11 Node 26.12.1 harness files passed, and diff checks passed. Independent review found no important production regression; its uncertainty-scoring caveat was reproduced with a failing test and corrected. This verifies contracts/guidance delivery/evaluator behavior, not that all 44 conversations are understood by the real model. Existing microphone/browser, source-completeness and remote-CI limitations remain. No merge/deployment.


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


## 2026-10-29 external clinical review continuation (separate draft change)

Claude's feedback was checked against current code. The older interaction-test record is historical, not a reproduction on this native-web revision. Existing medication temporal labels, omission/daily-denial retention and clinician-plan review already exist; structured reconciliation and clinician-approved risk rules remain incomplete. No broad medication-class contraindication rules were added without validation.

Added clinician_statement to the same extraction call. Grounded statements become bounded transient CLINICAL_STATEMENT insights, never selectable patient-record fields. Final review receives separate clinician_ anchors and preserves all-source failure/grounding controls. Each attributed statement explicitly reports unverified or control_point_present (not correct/incorrect). Speaker attribution and clinical entailment remain unverified. Source-free claims do not silently become safety approval. JS v18 shows attribution/uncertainty, excludes it from confirmed save and rejects overflow while preserving transcript. No added production model call.

Repeated evaluator: --repeat 1..10, --max-calls default25/hard500, independent attempts, stop on provider error, failed attempts retained. Per-case routing recall, forbidden routes and topic-set consistency reported separately from pass status; stable incorrect routes cannot become passed cases. Missing/forbidden/ungrounded clinician attributions now fail scoring. Added six provisional synthetic cases: 50 total, 15 branches, 53 required topic groups, 46 expected topic IDs. These are not clinician-adjudicated gold labels or clinical alert sensitivity.

RED/GREEN regressions cover normalization, final coverage, repeated failure accounting/budget and attribution scoring. Integrated DOM RED/GREEN covers transport, explicit unverified UI, exclusion from saved patient fields and draft-preserving overflow. Fresh full local suite: 370 Python tests passed, two existing dependency warnings, 18.52s; 11 Node26.12.1/jsdom files passed, 3.20s; diff check passed. Explicit same-provider --live --limit5 --repeat5 --max-calls25 still stopped with missing_provider_configuration, model_calls=0.

Detailed remaining gold-set/clinical metrics/pilot requirements: docs/voice_clinical_validation_protocol.md. No actual native model/microphone/clinical accuracy measurement, feedback data lifecycle or Turkish guideline coverage verified in this continuation. Changes are proposed on a new draft PR, not merged/deployed; prior merged main revision remains 278d30c with known Render build-quota failure.

Independent follow-up review found contradiction enums omitting transient clinician anchors and forbidden-attribution scoring missing short quoted spans. Both were reproduced RED and fixed before publishing. Required positive clinician quotations are still exact/provisional and can undercount valid shorter extractions; this is not a semantic or clinical gold score.


## 2026-10-29 continued adversarial verification (PR #217)

Reproduced model-output boundary defects: planned/negated/uncertain/unrelated chart states and another tooth's state were accepted as existing candidates. Added affirmative state/tooth quotation checks, including spoken FDI subjects and punctuation-free questions, with explicit uncertainty instead of silently adding a chart finding. Existing positive controls remain candidates for physician approval. Conservative shorthand limitations documented; no diagnosis or drug contraindication rules added. Normalized-plan-to-apply and no-confirmation endpoint tests verify no record writes.

Added offline human-adjudicated clinical outcome scoring with explicit TP/FP/miss/critical-miss and negative-run denominators. Unapproved labels are rejected; provider failures count as end-to-end expected-alert misses; unreviewed/missing outcomes suppress whole-cohort sensitivity. This tool does not infer clinical correctness from model prose. Draft template intentionally produces no clinical score. Whitespace-only question/contradiction anchors also rejected.

Final full local checks: 416 Python passed (two dependency warnings, 25.43s), 11 Node26/jsdom files passed (9.91s), diff check passed. Independent review findings on the new chart helper were reproduced and fixed. Real keys/model config and local browser/microphone unavailable; explicit live run still model_calls=0. No claimed gold-set score, live semantic/clinical accuracy or real-browser pilot. See docs/voice_clinical_validation_protocol.md for input format, metric interpretation and remaining work. Update existing draft PR #217 only; no merge/deployment or secret/billing changes.


## 31 Ekim 2026 — yayımlanmış vakalardan gündelik üç konuşmacılı set

- `tests/fixtures/voice_published_case_dialogues.json`: 12 yayımlanmış vaka + 2 mesleki kılavuz başvurusu; 12 vaka esinli ve 12 kurgusal karşılaştırma, toplam 24 konuşma / 192 replik. Her diyalog Hasta, Hekim ve Asistan içerir. Okunabilir sürüm: `docs/voice_published_case_dialogues.md`.
- Her öğede kaynak kimliği, uyarlama açıklaması, korunacak bilgi, çıkarılmaması gereken sonuç ve insan inceleme listesi var. Tam metin CAPTCHA ile açılamayan kaynaklar yalnız indekslenmiş vaka/özet erişimi olarak işaretli. Kaynak olgudaki tedavi genel klinik kural sayılmadı.
- Önceki 50 konuşmalık fixture değişmedi. Değerlendirici `--fixture` ile yeni seti kabul eder; 2–12 replik ve Asistan desteklenir. Desteklenen eski ifade biçimindeki konu kimliklerinin yanlış `unknown_branch` hatası vermesi RED/GREEN testiyle düzeltildi; eski kimlik sayısı ayrı raporlanır.
- Yeni set: 10 noktalı taksonomi dalı, 27 beklenen konu kimliği (8 eski ifade kimliği dahil), 30 gerekli konu grubu, 1 zorunlu netleştirme vakası. Bu sayılar bütün diş hekimliği kapsamı veya klinik duyarlılık iddiası değildir.
- Yeni 32 otomatik test veri bütünlüğünü, puanlayıcının boş çıktıyı başarı saymamasını, asistana ait sözün hekime yanlış atfedilmesinin yakalanmasını ve beklenti/kaynak notlarının çıkarıcıya gönderilmemesini sınar. Sahte sağlayıcı çıktılarını kullanmak klinik/model başarısı sayılmadı.
- Güncel sesli snapshot koşusu: `PYTHONPATH=.:../testdeps python -m pytest -q` → **448 passed**, 2 bağımlılık kullanımdan kaldırma uyarısı, 15.44 s. İlk yeniden kurulum koşularındaki eksik `app.work_jobs`, `app.http_transport` ve ana şablon dosyaları uzak committen aynen geri yüklendikten sonra tekrar koşuldu; üretim mantığı bu eksiklikleri gizlemek için değiştirilmedi. Bu snapshot tüm sitenin test koleksiyonu değildir.
- Node 26.12.1, jsdom 30.1.3: `PYTHONPATH=.:../testdeps NODE_PATH=../domdeps/node_modules ../domdeps/node_modules/node/bin/node --test tests/voice*.cjs` → **11 passed**, 0 failed, 1.70 s. Gerçek mikrofon/tarayıcı testi değildir.
- `--fixture tests/fixtures/voice_published_case_dialogues.json --live --limit 24 --repeat 5 --max-calls 120` → **missing_provider_configuration**, **model_calls=0**, çıkış 2. Gerçek Claude çıkarımı, kaynak getirme ve final değerlendirme bu set üzerinde çalıştırılmadı; klinik başarı oranı yok.
- Tüm etiketler **draft**, `clinical_gold_standard=false`. Klinik kontrol listeleri otomatik final çıktı puanlaması değildir; hekim gerçek çıktıları ayrıca incelemeli. Canlı ses/ASR, gerçek üç konuşmacı ayrımı, insan onaylı altın set, klinik duyarlılık/yanlış alarm ve uzak CI yeşilliği doğrulanmadı. Bitişte çalışan mimari, acil senaryolarda gerçek zamanlı alarm sağlamış sayılmaz.
- PR #217 taslak kalır; main birleştirme veya Render dağıtımı yapılmadı.


## 1 Kasım 2026 — kullanıcı onaylı canlı yayın ve gerçek oturum testi

#217 tamamı kullanıcı talimatıyla main'e birleştirildi ve Render'da live doğrulandı. Gerçek güvenli girişten sonra iki kimliksiz sentetik metin vakası, mevcut Claude bağlantısı ve gerçek kaynak araçlarıyla çalıştırıldı. Bu çalışma gerçek mikrofon testi değildir.

Canlı denemeler çıkarım isteğindeki strict uyumsuzluğunu, yanlış aşama hata metnini ve reCAPTCHA sayfasının kaynak sayılması kusurunu yakaladı. #218–#222 ile düzeltmeler/tanılamalar yayımlandı. Uzun kaynakta geç gelen pasajın kaybı da RED/GREEN testiyle giderildi. Son canlı kod a06f4654, deploy dep-dbjhqtjm8hqs73fpnf6g, live14:09:20 İstanbul. İlk vakada gerçek ADA kaynağı ve3 alıntı dayanaklı kontrol noktası; ikinci vakada asistan/yakın öyküsünü hastaya atamayan sonuç ve ADA restorasyon kaynağı görüldü. Kayıt onayı olmadan kaydetme canlı ön yüzde engellendi; kaynak yeniden denemelerinde başarılı çıkarım tekrarlanmadı.

460 Python testi geçti; bu oturumdaki11 Node kontrolü de geçti. Araştırmanın çıktı sınırında kesilmesi nedeniyle kaynak kapsamı hâlâ kısmi gösteriliyor. Bu sonuçlar24 vakanın tamamı, gerçek mikrofon, pozitif hekim onaylı kayıt veya klinik doğruluk ölçümü değildir. Plan/bulgu alan sınıflaması ve soru tekrarları için küçük açık bulgular var. Ayrıntı: docs/voice_live_validation_2026-11-01.md. Önceki tarihli taslak/yayımlanmadı notları tarihsel durumu anlatır; bu bölüm yayın durumunu günceller.


### 1 Kasım ek gerçek canlı vakalar ve iletişim düzeltmesi

İki ek kimliksiz sentetik metin muayenesi gerçek Claude ve gerçek kaynaklarla tamamlandı: aktif hastane ilacı günlük hap yokluğuyla silinmedi; gelecekteki çekim/implant tamamlanmış işlem sayılmadı. AAE/NHS ve EFP kaynakları gösterildi; her iki sonuç kısmi kapsamlı. Canlıda hekimin belirsiz “adını koymayalım” ifadesinin ilaç adı diye paraphrase edilmesi yakalandı. RED/GREEN regresyonla clinician_response için doğrulanmamış yeniden anlatım kaldırılıp birebir yanıt korundu. 461 Python ve11 Node testi geçti; bağımsız74 odaklı testte engel yok. Yeni düzeltmenin canlı tekrarı ayrıca doğrulanmalı.

Açık kalan önemli bulgular: 47 dişindeki dolgunun “yanında” diye yeniden anlatılması; implant sonrası iyileşme kaynağının çekim sonrası planla hatalı ilişkilendirilmesi. Literal alıntı doğrulaması klinik uygulanabilirlik doğrulaması değildir. 24 vaka/5 tekrar, gerçek mikrofon, hekim onaylı altın set ve pozitif kayıt akışı tamamlanmış sayılmaz. Ayrıntılı tablo ve UTC log özeti: docs/voice_live_validation_2026-11-01.md.


### Seçilmiş özet görseli — düzen farkı ve dar arayüz iyileştirmesi

Önceki örnek resim gerçek canlı sentetik sonuçla karşılaştırıldı: açılır kart düzeni yoktu, özet/dayanak tekrarları ve üstte uzun kayıt formu vardı. Native açılır kartlar/sayılar, ayrı dayanak/eksik bilgi/öneri, kontrol başına kaynak alıntısı ve değerlendirme sonrası açılır kayıt bölümü eklendi. Kaynak eksikliği uyarısı ve açık hekim kayıt onayı korundu. RED/GREEN entegre panel testi ve11 Node dosyası geçti; gerçek yeni ekran dağıtım sonrası ayrıca doğrulanmalı. Ayrıntı docs/voice_live_validation_2026-11-01.md.

#224 iletişim düzeltmesi18:03:28 İstanbul'da live oldu. Aynı vaka tekrarında aktif ilaç korundu fakat yalnız arka plan yayını bulunabildi; final sources1/accepted0. Önceki AAE kaynaklı sonucun tutarlı biçimde tekrarlandığı söylenemez. Kaynak uygulanabilirliği ve klinik alan paraphrase kusurları hâlâ açık.


#225 fb041879, dep-dbjlcj3m8hqs73ftika0 ile18:11:54 İstanbul'da live oldu. Gerçek sentetik dolgu vakasında yeni kartlar,2öğeli özet,ADA kaynak grubunun açılması ve onaysız kayıt engeli gerçek tarayıcıda doğrulandı. Son final15:13:10Z sources1/accepted0; kaynaklı kontrol üretilmediği açıkça gösterildi. Önceki aynı vakadaki1kontrol bu kez tekrarlanmadı; kaynak/model tutarlılığı çözülmüş sayılmaz. Kanıt ekranları ve4adımlı kısa görsel inceleme ana canlı test raporunda. Fiziksel mobil/mikrofon ve klinik altın set doğrulanmadı.


### 1 Kasım — sade başlıklar ve uzatılmış gündelik konuşmalar

Başlıklar “Görüşmeden çıkan bilgiler”, “Kaynaklara göre kontrol edilecekler”, “Hastayla iletişim”, “Netleştirilecek sorular”, “Kaydedilecek bilgiler” olarak sadeleştirildi. Önceki vaka esinli setten3yeni uzun senaryo:74replik, toplam14:52Türkçe yapay ses,13adet90saniye altı bölüm. Gerçek mikrofon/insan sesi değildir. Sesli rol adları okunmaz; beklenen sonuçlar ayrı metadata alanındadır. Fixture doğrulayıcı48repliği destekler,49u reddeder; RED/GREEN sonrası462Python/11Node geçti. Canlı ses testleri henüz bu notla geçmiş sayılmaz; ayrı koşular ve bulgular docs/voice_extended_validation_2026-11-01.md içinde kaydedilir.


### Uzun seslerin gerçek üretim testi ve bulunan klinik veri hataları

#22718:39:53 İstanbul'da live oldu. Üç yapay Türkçe ses(5:14/4:43/4:55),13bölüm halinde gerçek Gemini aktarımı ve Claude çıkarım/kaynak/final akışında denendi; bir ASR bölümü ve bir final açık yeniden denemeyle tamamlandı. Aynı26replik özgün rol etiketli metin de karşılaştırıldı. ASR kritik ilaç/olumsuzluk ifadelerini değiştirdi; rol etiketli metinde bile asistan öyküsü hasta alanına sızdı, hekim sorusu ilaç beyanı oldu. Bulgular/plan karışması ve fazla tekrarlar var. Kaynak sonuçları kısmi; kontrol sayıları başarı oranı değildir. Hekim onayı veya klinik kayıt yapılmadı.

subject PATIENT/OTHER/UNKNOWN doğrulaması, hasta durumu sorusunu kayıt saymama ve planı bulgulardan ayırma için RED/GREEN korumalar eklendi; çapraz alan ve örtüşen alıntı sınırları bağımsız incelemeyle düzeltildi.471Python ve11Node geçti;83odaklı testte engel yok. Bu ses konuşmacısı doğrulaması/ASR düzeltmesi değildir; yanlış model etiketi hâlâ mümkün. Ayrıntılı tablo ve değişiklik öncesi sentetik gerçek çıktılar: docs/voice_extended_validation_2026-11-01.md ve docs/voice_extended_results_2026-11-01.json. Yeni korumanın canlı tekrarı ayrıca doğrulanmalı.


#22843ddb4b1,19:09:31 İstanbul'da live doğrulandı. Aynı26replik metnin gerçek tekrarında yeni aidiyet şeması çalıştı; asistanın şikâyeti ve hekimin ilaç sorusu hasta alanlarından çıktı, aktif ilaç korundu. Ancak plan alanı bu koşuda hiç oluşmadı; model eksiltmesi/etiket-filtre sebebi UI kaydından ayrıştırılamadı. Planın tam çıkarıldığı veya ASR hatalarının çözüldüğü iddia edilmiyor. Sonuç1kaynak/2kontrol, kısmi; hekim kaydı onaylanmadı. Güncel kanıtlar ve açık kusurlar uzun test raporu/JSON'unda.


## 2026-11-02 yayın denetimi ve gerçek plan kaybı

PR230 sayısal tanılama canlıda aynı26turluk3905karakterlik vaka için candidates=0/recorded=0 gösterdi: planı model üretmemiş, filtre silmemiş. PR231 günlük inceleme/kayıt doğrulama planlarını çıkarım talimatında açıklaştırır; üç uzun vaka artık plan alanı eksikse yalnız konu eşleşmesiyle geçmez. Sunucu klinik plan icat etmez.488Python ve11Node geçti; bağımsız82odaklı test ve incelemede engel bulunmadı. Dört skorlayıcı regresyonu önce başarısız oldu.

PR215 hâlâ açık/çakışmalı: tüm eski dalın canlı olduğu iddia edilmez. İki bağımsız eksik (mobil async mesaj await ve gerçek /api/mobile/v1 dahil klinik no-store) PR231'e taşındı. Eski ses denetleyicisi yeni mimariyi gerileteceği için kopyalanmadı. İstek kuyruğu/sağlayıcı slotu eski haliyle güvenle taşınmış sayılmaz; tekrarlanan iptal temizliği ayrıca gereklidir. Ayrıntı ve gerçek yayın sonrası sonuçlar docs/voice_validation_2026-11-02.md.

Kaynak kapsamı canlı koşuda kısmi; bazı final iletişim kontrolleri açıklanmış konuyu eksik saydı. Bunlar klinik başarı diye raporlanmaz. Gerçek mikrofon ve hekim onaylı altın test seti yok; uzak CI yeşil doğrulanmadı. Hasta dosyasına kayıt onaylanmadı.


### 2 Kasım gerçek tekrarların sonucu ve PR232/233

PR231 Render2957bfcd (05:27:33Zlive): kemik-ilacı vakası plan alanını geri getirdi (3kaynak5kontrol), kaplama vakası plan/randevu reddini korudu (2kaynak2kontrol), implant vakası iki kez aidiyet çakışmasında durdu ve metni korudu. Bunlar gerçek model/metin UI koşularıdır, mikrofon değildir. Kaplamada model “üstündeki”yi çene konumuna çevirerek yanlış çelişki üretti. PR233 başvuru şikâyetini kaynak alıntısının özgün metniyle korur; karışık aile/hasta cümlelerinde kişi başına kısa cümlecik alıntısı ister, çakışma korumasını kaldırmaz.492Python ve11Node geçti.

PR232 sahte route modellerini özel SQLModel registry'sine ayırdı; üretim globalmetadata'sını değiştirmedi. Gerçek uzakCI artık voice toplama hatasını geçti; application-regressions1952geçti/43başarısız/48atlandı,594alttest geçti. Başarısız listede test_voice yok. Akademik hatalar ve PostgreSQL42geçti/2başarısız ayrı açık sorun; tümCI yeşil değil. Tam görünür koşular/nihai dağıtım kanıtı docs/voice_validation_2026-11-02.md ve docs/voice_live_results_2026-11-02.json içinde. Klinik altın set/gerçekmikrofon/ASR doğruluğu bu testlerle kanıtlanmadı.

Sonuç: PR233/2abdbb4e Render05:38:03Zlive doğrulandı. Kaplama özgünmetin tekrarında şikâyet aynen korundu ve yanlış üst/alt çene çelişkisi yok;2kaynak0kontrol, eksik kapsam açık. İmplant üçüncüdenemede de aidiyet çakışmasında durdu; prompt bunu çözmedi, metin korundu. UzakPR233voicejob125114274998482Python+11Nodebaşarılı; genelsiteCI kırmızı. Altı yayınsonrasıdenemenin DOMkanıtları voice_live_results_2026-11-02.json; ayrıntılı açıklar voice_validation_2026-11-02.md. Akıştamamensorunsuz/klinikgüvenli denmiyor.


## 2026-11-02 — 90 saniyelik klinik ses kampanyası ve HeyGen

PR234/93c0e8ed çakışan hasta/başka kişi alıntısında tüm çıkarımı durdurmak yerine yalnız çakışan bilgiyi dışarıda tutar. Bağımsız bilgiler, plan ve mevcut kaynak/diş/randevu dışlamaları korunur. Sabit eksik kapsam bildirimi muayene sonundadır; yeni ücretli çağrı veya muayene sırasında hekim doğrulaması eklenmedi. İlk perio sesinin aynı metni yayın sonrası son değerlendirmeye ulaştı; ASR kaynaklı bozuk bilgi ve yanlış plan/çelişki sorunları klinik başarı sayılmadı.

Sekiz farklı konu için12turluk185–206kelimelik diyaloglar ve tam90s temiz/uğultulu16sentetik ses üretildi. eSpeak robotik olduğundan doğal insan sesi testi değildir. Perio/cerrahi/implant/kron/endo/çocuk seslerinde tamamlanmış ve yarıda kalmış aşamalar ayrı kaydedilir; sekizli kampanya tamamlandı diye sayılmaz. Ortodonti ve protez için sesler hazır, canlı tam akış henüz tamamlanmadı.

HeyGen bağlantısı doğrulandı. Katalog önerisiyle yapılan tek Starfish sentezi, çalışma alanının Orca zorunluluğu nedeniyle400 döndürdü; ses üretilmedi. narrator yönergesindeki hata sonrası onay kuralı nedeniyle otomatik yeni motor çağrısı yapılmadı. Orca/HeyGen Voice üretimi kullanıcı onayını bekliyor. Kesin istek/hata: docs/voice_clinic90_heygen_2026-11-02.json.

PR235/b54cdcb7 JSON olmayan hizmet yanıtında ham DOCTYPE/parser hatası yerine Türkçe hata ve taslak/ses yeniden deneme yolunu korur; v22. Regresyon önce başarısız oldu, sonra494Python/11Node geçti; bağımsız incelemede engel yok. Ayrıntı: docs/voice_clinic90_validation_2026-11-02.md. Genel site CI ve gerçek mikrofon/klinik doğruluk hâlâ ayrıca doğrulanmalıdır.
