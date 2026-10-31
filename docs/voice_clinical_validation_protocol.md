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

## Follow-up: chart assertion boundary and human-adjudicated metrics

A new adversarial test reproduced a concrete normalization defect: if the model supplied EXTRACTED for “46 numaralı dişi yarın çekeceğiz”, the candidate was previously accepted. Proposed filling/crown/implant/root-canal statements, explicit negatives and unrelated state labels had the same gap. The core now calls app/voice_chart_assertions.py before retaining a chart candidate and explicitly flags withheld candidates in uncertain. No confirmed-save contract changed.

The quotation check requires affirmative existing-state evidence for the selected state. It does not infer a chart state from absence of proposal words. It separates numeric and spoken FDI subjects in an analysis-only copy, checks interrogatives without question marks, and cannot borrow “var/mevcut” from a different procedure to turn a new plan into an existing finding. EXTRACTED requires explicit completed-extraction language. Original quotes/transcripts are not rewritten. This is conservative, bounded Turkish evidence checking, not a general semantic parser or a clinical diagnosis. Valid shorthand/group descriptions may need manual review; it is not proven complete under arbitrary ASR corruption, grammar or speaker confusion.

Independent review reproduced question-particle, spoken-subject and unlisted-future-verb failures in the initial helper. RED/GREEN regressions drove the affirmative-state design above. Endpoint tests also verify that a withheld planned procedure cannot create a chart record and even a legitimate candidate cannot write records without confirmed physician approval. Three whitespace-only checklist/contradiction regressions were separately fixed; empty textual anchors are not meaningful evidence.

### Offline clinical outcome scoring

scripts/score_voice_clinical_review.py processes human-adjudicated alert IDs against exhaustive, declared clinician-approved case labels. It does NOT read clinical prose and decide whether a warning is true. A human reviewer must map real outputs to expected/extra alert identifiers. Approval/adjudication metadata are audit declarations, not authentication of reviewer credentials or proof of scientific validity.

```sh
PYTHONPATH=.:../testdeps python scripts/score_voice_clinical_review.py reviewed_results.json
```

The input format is illustrated by tests/fixtures/voice_clinical_review_template.json. That template deliberately remains draft/unapproved and the scorer rejects it. Do not mark it approved without actual review. Cases require approval_status=approved, labels_complete=true, nonempty approved_by/approved_at and required_alert_ids; critical_alert_ids must be a subset. Each run references a case and repeat index and is reviewed, failed or unreviewed. Reviewed runs need adjudicated_by/adjudicated_at and human-labelled observed_alert_ids. Duplicate runs/labels and unknown cases are rejected.

Reported units/denominators:
- True/false positive alerts compare reviewed observed IDs to exhaustive required IDs, counting each alert ID once per run.
- Reviewed misses are expected IDs absent from reviewed outputs. Provider-failure misses count all expected IDs for a failed attempt; no provider failure is treated as a clean clinical negative.
- End-to-end sensitivity = TP / (TP + reviewed misses + provider-failure misses). It is withheld (null) if any required outcome is unreviewed or unrecorded.
- Reviewed alert recall and alert precision use only their stated scored alert denominators. They are not full-cohort clinical performance when coverage is incomplete.
- Negative-run false-positive rate = reviewed negative-control runs containing any extra alert / reviewed negative-control runs. It does not mix alert counts with encounter counts; no reviewed negative denominator means null.
- Critical misses are known critical IDs missed in reviewed/failed runs; unreviewed/missing records remain unknown.
- coverage_complete requires every case/repeat to be recorded, reviewed and not provider-failed. CLI exit 0 means review-record coverage is complete, NOT that performance is good or the product is clinically safe. No release threshold is implemented.

Actual verification in this environment: full suite 416 Python tests passed (two existing dependency warnings, 25.43s), 11 Node26/jsdom harness files passed (9.91s), diff check passed. The synthetic adjudication unit fixtures test arithmetic and validation; these numbers are not measured clinical alert performance. ANTHROPIC_API_KEY, explicit VOICE_EXAM_CLAUDE_MODEL and GEMINI_API_KEY are absent; no local Chromium/Chrome/Firefox or Python Playwright was available. Actual --live --limit5 --repeat5 --max-calls25 stopped with missing_provider_configuration/model_calls=0. The template scoring command rejected unapproved records with zero model calls. No real browser/microphone/provider or clinician-approved gold measurement completed. The 100+ adjudicated case set is still required and cannot be manufactured by relabelling synthetic developer tests.


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
