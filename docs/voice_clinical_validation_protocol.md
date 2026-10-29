# Clinical validation protocol — 29 October 2026

This is a validation plan and an interpretation guide, not a clinical safety certificate. The current fixture has 50 synthetic conversations with provisional routing/attribution expectations. No clinician-adjudicated gold set or authenticated model accuracy result exists yet.

## Review of the external feedback

- Correct: offline test passes do not measure clinical sensitivity, false alarms, source entailment, actual ASR or live tool support. These remain release limitations.
- Historical, not a current reproduction: the clarithromycin/simvastatin and rosuvastatin observations came from the earlier live version. They are useful regression scenarios, not evidence that the current native-web implementation has the same measured failure rate. Re-run on the target revision with configured providers before claiming fixed or persisting.
- Partly already implemented: medications/plan/allergy fields preserve CURRENT/HISTORICAL/PLANNED/NEGATED/UNKNOWN fact labels and exact spoken medication quotations. Incremental omission/daily-denial retention has regression coverage. These are not a complete structured medication reconciliation ledger; speaker attribution, confirmation/correction and linkage between drugs/doses remain open work.
- Overstated: clinician treatment plans were already extracted and reviewed; there was no blanket exclusion of clinician speech. The gap was explicit handling of clinician assertions beyond communication coaching and visible per-assertion coverage. This continuation adds transient clinician_statement routing and per-assertion review status.
- Not adopted as unvalidated clinical rules: broad rules such as any macrolide/statin, any penicillin allergy/antibiotic or any anticoagulant/NSAID must not become unconditional contraindications. Exact products, indications, histories and current primary-source recommendations need clinician-approved rules and negative controls. No new treatment rules or source-free warnings were added.
- Open: current TDB/Ministry-of-Health coverage, provider contracts/legal compliance, real microphone/speaker validation, and an optional consent-aware feedback data lifecycle were not established by this review. No legal-compliance claim.

## First implemented steps

The existing extraction schema adds clinician_statement (no extra provider call). Its exact grounded quote is emitted as CLINICAL_STATEMENT in transient insights, never a patient-record field. The model must select applicable existing source topic IDs. Attributed speaker identity remains unverified, not diarization.

Final review sees clinician_ anchors separately from communication_. It can examine a stated dose without generating a replacement dose. Every displayed clinical control point still needs literal patient/clinician and source anchors and an eligible source. An attributed statement with no accepted control point gets status unverified; presence of a control point is not a correctness/error verdict. The UI displays this distinction and explicit overflow, and confirmed save does not include these transient assertions.

The spoken evaluator now accepts --repeat 1..10, with --max-calls 1..500 (default 25) enforced before provider import/calls. Repeats are independent attempts, not retries. Any provider/parse failure stops the run. It reports per-attempt failures, required-group routing recall, forbidden routes and route consistency (the most frequent grounded topic set divided by completed route sets). Stable incorrect routing can have high consistency: all_attempts_passed is separately required. Clinician attribution omissions/forbidden attributions/ungrounded quotations are scored. These are routing and attribution metrics, not clinical sensitivity or source entailment.

Examples, run in the existing repository environment:

```sh
PYTHONPATH=.:../testdeps python scripts/evaluate_voice_spoken.py
PYTHONPATH=.:../testdeps python scripts/evaluate_voice_spoken.py --live --limit 5 --repeat 5 --max-calls 25
```

Expected configuration remains the existing ANTHROPIC_API_KEY and explicit VOICE_EXAM_CLAUDE_MODEL. Do not retrieve keys from unrelated accounts or print secrets. The actual run in this environment still stopped with missing_provider_configuration, model_calls=0.

## Building the clinical gold set

A clinical reviewer should approve at least 100 distinct realistic synthetic or appropriately de-identified cases, not 100 paraphrases counted as independent diseases. Cover all dental branches and include positive, close negative, uncertain-name, negation, historical, other-person, proposed-versus-completed, dose/unit/missing-indication, communication, ASR-corrupted and no-source cases. Include near-identical negative controls for every high-risk positive case. Keep raw audio and real patient data out of the repository.

Each case needs: case ID/version, target stage (ASR/extraction/research/final), provisional versus clinician-approved status, reviewer/date, exact input, reference source URL/version/date/passage, required clinical control points, forbidden control points, clarification needs, supported patient/source anchors, and handling of inaccessible/no evidence. Separate clinician attribution from correctness. At least two reviewers should resolve disagreements before scoring a gold label. Expected labels must never be sent in the provider prompt.

Run each approved case at least five times on a pinned application revision and the configured provider/model/tool policy. Record denominator and failed attempts. Evaluate extraction, source recall, source applicability, final unsupported claims and clinician-facing display separately. For labelled clinical alerts measure TP/FN and FP/TN, sensitivity and false-positive rates with their denominators; report critical misses by severity and consistency across repeats. Do not substitute topic-group recall for these metrics.

External faults need controlled cases too: unavailable sources, unsupported tools, timeout, partial evidence, outdated documents, and negative controls for unreported medication classes. Check no repeated paid extraction on retry, no missing last audio segment, and no record changes before physician approval.

## Remaining live pilot

A clinician-supervised pilot with real browser/microphone and synthetic dialogue must verify Turkish recognition under noise/overlap, final flush, attribution uncertainty, same-provider extraction/native research/final response, real source passage relevance, failure UI, correction/retry and explicit save. Do not label the current automated checks as this pilot. Render's existing build quota blocker must be resolved separately; no new production rollout is included in this continuation.

Validation after independent review fixes: 370 Python tests passed (two dependency deprecations), 11 Node harness files passed. Required clinician quotations currently match exact labelled spans and can conservatively fail a semantically valid shorter quotation. Forbidden utterances reject contained shorter spans as well as full matches. Human-approved acceptable-span alternatives/semantic adjudication are needed before interpreting these counts as clinical performance. Contradiction schema now accepts transient clinician anchors too, including clinician-only encounters.
