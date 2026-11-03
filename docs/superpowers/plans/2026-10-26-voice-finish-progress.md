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


## 2026-11-03 — Eksik canlı aktarım sonrası tepkisiz özet düğmesi

Kullanıcının gerçek telefon denemesinde “Son konuşmanın tamamlandığı doğrulanamadı” uyarısı ve “Özeti kontrol et” düğmesi görüldü. Kök neden: `flushed=false` durumunda çıkarım başlamıyor ve `.voice-review` gizli kalıyor; canlı denetleyicinin düğmesi yalnız gizli özete kaydırıyordu. Sonuç üretilmediği halde özet varmış gibi davranıyordu.

Düzeltme: özet henüz yoksa düğme “Metni kontrol et” olur; tıklama korunan konuşmanın bulunduğu bölümü açar ve metne odaklanır. İşleme yalnız kullanıcının mevcut “Metni işle ve değerlendir” eylemiyle başlar. Hazır özet varsa mevcut özet gezinmesi korunur. Yeni model çağrısı, otomatik onay veya hasta kaydı eklenmedi. Canlı betik önbellek sürümü v7.

Regresyon, bağlantı kopması ve normal bitişte `flushed=false` durumlarını gerçek Jinja paneli ve iki denetleyiciyle jsdom içinde çalıştırır; düzeltmeden önce kapalı kalan metin bölümü nedeniyle başarısız oldu. Düzeltme sonrası açık bölüm/odak, kullanıcı eylemine kadar sıfır çıkarım/son değerlendirme çağrısı, sonraki tek işleme ve hazır özet gezinmesi doğrulandı. Bağımsız incelemede engel bulunmadı. Tam yerel koşu: **494 Python geçti** (iki mevcut bağımlılık uyarısı), **11 Node geçti**.

Sınır: bu düzeltme eksik son ses aktarımının ağ/sağlayıcı nedenini çözmüş sayılmaz; kullanıcının gerçek sesi ve tarayıcı/mikrofonla aynı olay yeniden üretilemedi. Gerçek konuşmanın tam geldiği veya klinik sonucun doğru olduğu iddia edilmiyor. Açık sayfadaki geçici metin yenilemeyle kaybolabilir; yeni betik için sayfa yenilemeden önce metin kopyalanmalı. Dağıtım sonucu ayrıca doğrulanacak.
