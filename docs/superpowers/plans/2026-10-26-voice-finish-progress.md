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


Dağıtım doğrulaması (3 Kasım): PR236, kaynak başı `f87e525e`, main/runtime `f5b5ae2a6668b1828a20a7debb28eb2e6f3d087c`. Render `dep-dbks0kgae00c73ftmo50` **14:08:50 Türkiye saati** itibarıyla `live`. Oturum sayfasında `/static/voice-exam-live.js?v=7` doğrulandı. Uzak PR236 `voice` kontrolü başarıyla tamamlandı; genel site CI için başarı iddia edilmiyor.

Canlı mikrofon başlatma adımı, bu tarayıcının bilinmeyen ortam sesini sağlayıcıya aktarabilmesi nedeniyle otomatik güvenlik denetimince engellendi; engel aşılmadı. Bunun yerine önceden yazılmış sentetik perio konuşmasıyla canlı metin/çıkarım/değerlendirme ve kart açma yolu kontrol ediliyor. Bu, kullanıcının arkadaşla yaptığı mikrofon denemesinin tekrarlandığı anlamına gelmez.

Canlı metin denemesi tamamlandı: günlük altı turluk sentetik perio konuşması,1 kaynak/2 kontrol notu,5 bilgi,2 iletişim notu,6 soru. Kaynak kapsamı eksik uyarısı ve yeniden deneme yolu görünür kaldı. “Görüşmeden çıkan bilgiler”, “Kaynaklara göre kontrol edilecekler”, “Hastayla iletişim”, “Netleştirilecek sorular”, “Kaynaklar”, “Kaydedilecek bilgiler” başlıkları gerçek tarayıcıda açılıp kapatıldı; ilk kontrol notunun özgün ADA alıntısı da açıldı. Kayıt onayı verilmedi, hasta dosyasına yazılmadı. Plan alanı bu koşuda görünmedi ve aidiyet/alıntı çakışması uyarısı vardı; bunun nedensel ilişkisi ayrıca doğrulanmadı, tam klinik başarı sayılmadı. Açık sayfa sonucu sentetiktir; gerçek mikrofon akışı test edilmedi. PR236 voice kontrolü geçti; static-safety, postgres-integration ve application-regressions başarısız olduğundan tüm CI yeşil değildir.


## 2026-11-04 — Okunur özet ve materyal/işlem kaynak kapsamı

Telefon ekranında iç içe kenar boşlukları metni daraltıyordu. Oturum genişliği büyük ekranda960px, telefonda ekran genişliğine yakın olacak biçimde düzenlendi; kart iç boşlukları azaltıldı. Özet artık her değerin alan adını gösterir ve satır sonlarını korur. “Güncel” iç etiketi görünmez; “Geçmiş” yerine “Önceden”, “Belirsiz” yerine “Net değil”, “Olumsuz beyan” yerine “Olmadığı belirtildi” yazılır. Negatif etiket sadece silinmez: “Olumsuz beyan: Penisilin alerjisi” gibi isim biçimli negatif bilgi pozitif alerjiye dönüşmemelidir. Bu durum incelemede yakalandı, regresyon RED→GREEN ile düzeltildi. Anlaşılır görünüm, değiştirilmemiş alanların özgün klinik değerini/alıntı dayanağını veya onaylı kayıt yükünü değiştirmez.

Önceki geniş “protez malzemeleri” konusu özgül materyal seçimini kaynak aramasına yeterince taşımıyordu.10 kapalı ve sunucuya ait konu eklendi: zirkonya, cam seramik/lityum disilikat, metal seramik, veneer/lamine, post-kor, irrigasyon, obturasyon/sealer, direkt restoratif materyaller, rejeneratif greft/membran, implant parçası uyumu. Toplam80 doğrulanan konu vardır; bu sayı80 klinik kural veya tüm diş hekimliğinin doğrulandığı anlamına gelmez. Model yalnız kayıtlı kimlikleri seçer, alıntı doğrulanır; araştırmaya kişisel konuşma yerine sabit kamusal kapsam/sorgu gider. AAE restorabilite başlangıç sayfası eklendi. Kaynak yönlendirmesi, web araştırması ve son değerlendirme mevcut review_provider bağlantısını kullanır; otomatik ek model aşaması eklenmedi.

Araştırma ve değerlendirme istemleri; işlem amacı, hasta öyküsü, diş/bölge/dentisyon, kalan doku, kapanış/yük, izolasyon, preparasyon ve bağlantı koşullarını konuşma ve kaynak elverdiği ölçüde birlikte incelemeyi ister. Materyal sınıfından tüm ürünlere yasak çıkarılmaz; ürün varyantı ve üretici talimatı bilinmiyorsa uygunluk onayı verilmez. “Kanal tedavisi enfeksiyonu temizler, muayene gerekir” gibi genel tanımlar hasta için özgül kontrol notu diye doldurulmamalıdır.

Doğrulama:10 gündelik materyal/işlem cümlesi kapalı kimlik doğrulamasında önce başarısız oldu; düzeltme sonrası12 yönlendirme/gizlilik testi geçti. Gerçek Jinja/jsdom testinde alan adı, geçmiş/belirsizlik/negatif anlam ve değiştirilmemiş özgün kayıt yükü doğrulandı. Tam yerel koşu **516 Python** ve **11 Node** geçti; iki mevcut bağımlılık uyarısı vardır. Bağımsız inceleme son düzeltmede engel bildirmedi.

Sınırlar: bu testler modelin klinik başarısını ölçmez. Kamuya açık ADA dolaylı/direkt materyal sayfaları ve AAE restorabilite kaynağı başlangıçtır; her marka/varyantın güncel kullanım talimatı sistemde mevcut değildir. Kaynak bütçesi2 arama/3 getirme ile sınırlı olduğundan çok konulu görüşmelerin tümü kapsanmayabilir. Mikrofon ve hekim onaylı klinik altın set doğrulaması hâlâ tamamlanmadı. Uzak genel CI yeşil kabul edilmez. Yayın ve gerçek model/metin tekrarları ayrıca kaydedilecek.

Birincil başvuru kaynakları (4 Kasım erişimi):
- https://www.ada.org/resources/ada-library/oral-health-topics/materials-for-indirect-restorations
- https://www.ada.org/resources/ada-library/oral-health-topics/materials-for-direct-restorations/
- https://www.aae.org/specialty/fundamentals-of-restorability/


### 4 Kasım gerçek model tekrarları ve ikinci düzeltme

PR237/312af794, Render dep-dblf0697lnhs739l5ch0 **11:44:43 Türkiye** itibarıyla live. Oturumda JSv23/CSSv12 doğrulandı. Gerçek Claude/metin tekrarları: zirkonya köprü+diş sıkma2kaynak1kontrol; post-kor3kaynak1kontrol. İki sonuç da kısmi kapsam uyarısıyla çıktı. Başlangıç kanıtı docs/voice_material_before_2026-11-04.json, özgün sentetik diyaloglar tests/fixtures/voice_material_dialogues.json içinde. Gerçek mikrofon yok, kayıt onayı verilmedi.

Bulunan açıklar: zirkonya sonucunda konuşmadaki sağ üst bölgesi eksik sayıldı; post sonucunda özgül post yerine genel kompozit sınırlaması verildi. Postta “film açık” beyanı bulgular özetinde “film çekildi” oldu. Düzenli ilaç kullanmadığını ifade eden birleşik olumsuz cümleye rağmen ilaç listesi sorusu üretildi. Bu koşular tam klinik başarı değildir.

İkinci düzeltme: konuşulan özgül materyal/işlem hedefleri aynı son modele açıkça iletilir. Kontrol maddesi kapalı review_topic kimliğiyle ilişkilendirilir. Materyal kimliğiyle sunulan kaynak alıntısında ilgili özgül terimler yoksa madde çıkarılır. Genel kompozit cümlesi post-kor kontrolünü tamamlayamaz; post-operative/post-treatment gibi zaman önekleri ve platform/connection gibi genel sözcükler de kabul edilmez. Ekranda her materyal için kaynak alıntılı kontrol noktası var veya uygunluk kontrolü tamamlanamadı durumu gösterilir. Sözcük eşleşmesi klinik uygunluk kanıtı değildir; olumlu durum dahi uygunluk onayı sayılmaz. Araştırma bütçesi veya çağrı sayısı artırılmadı.

Muayene bulguları alanında kaynak alıntısı hem atomik hem eski özet yolunda aynen korunur; “açık film”den yeni çekim yapıldığı bilgisi üretilemez. Önceden bilinen alanın son değerlendirmede eksik sayılmaması için çapraz alan kontrolü istendi; bunun ve birleşik ilaç olumsuzluğunun gerçek model doğruluğu ayrıca izlenmelidir, düzeldiği varsayılmadı.

Yeni regresyonlar önce başarısız oldu: ilgisiz kompozit→post, post/core boşluğu görünürlüğü, geçerli ferrule alıntısı, yanlış film parafrazı, dört genel/temporal sözcük eşleşmesi. İnceleme, filtredeki temporal/generic yanlış eşleşmeleri yakaladı; bunlar RED→GREEN ile düzeltildi ve yeniden incelemede engel kalmadı. Son yerel koşu526Python/11Node; iki mevcut bağımlılık uyarısı. Uzak genel CI yeşil değil.


### Son özgül kaynak kapısı

PR238/2a24b8f9, Render dep-dblf61dckfvc73ffk62g **11:57:19 Türkiye** itibarıyla live. JSv24 doğrulandı. İkinci post ve zirkonya gerçek model/metin tekrarlarının DOM kanıtı docs/voice_material_second_2026-11-04.json içinde. Postta “film açık” özgün olarak korundu. Materyal durumları iki vakada da tamamlanamadı diye açık gösterildi; klinik başarı sayılmadı. Zirkonya tekrarında tabakalı porselen tartışması lamine/veneer konusu olarak da seçildi; bu gereksiz konu eşlemesi hâlâ açıktır. Birleşik “ilacım ve alerjim yok” ifadesine karşı gereksiz ilaç sorusu da sürdü.

İkinci post koşusunda model özgül post yerine seçilmemiş yüksek soy/baz metal alaşımlarına ait iki not oluşturdu. Son dar kapı, özgül materyal hedefi varken ADA genel direkt/dolaylı restorasyon karşılaştırma tablosundan gelen bir notun alıntısında seçili hedefle ilişki bulunmasını zorunlu tutar; broader/other konu kimliğiyle kaçınamaz. Başka ilaç kaynakları bu kapıyla süzülmez. Kapsam yalnız bu iki genel tablodur; tüm klinik uygunluğun anlamsal doğrulaması değildir. URL eşlemesi ADA hostname ve gerçek path üzerinden yapılır; query/fragment aynı belgeyi süzgeçten kaçırmaz. Eski eksik süzgeç çıktısı kaynak değişmedi diye korunmasın diye doğrulayıcı sürümü değerlendirme parmak izine katılır.

Son regresyonlar: seçilmemiş alaşım notu, aynı ADA URL'sinin query/fragment biçimleri ve doğrulayıcı değişince eski sonucun yeniden kullanılmaması RED→GREEN doğrulandı. Son tam yerel koşu530Python/11Node; iki mevcut bağımlılık uyarısı. Gerçek son tekrar/yayın durumu ayrıca eklenecek. Kayıt onayı hiçbir sentetik canlı testte verilmedi.

Son dağıtım: PR239/9dff17f531377b41368b56339b2eb87dd6505017, Render dep-dblfaqp7lnhs739lh96g **12:07:23 Türkiye** itibarıyla live. Materyal tablosu/URL/parmak izi düzeltmesi bağımsız incelemede engel kalmadan yayımlandı. Önceden çıkarılmış aynı post bağlamında yalnız son değerlendirme/kaynak yeniden denemesi başlatıldı; konuşma yeniden çıkarılmadı. Sonuç ayrıca aşağıya kaydedilecek.

Son canlı post tekrarı (9dff17f5):2kaynak/0kontrol, özgül post uygunluğu tamamlanamadı durumu görünür; önceki seçilmemiş alaşım/nikel notları gösterilmedi. Bu gerçek model/metin koşusudur, klinik doğruluk başarısı değildir. Kanıt docs/voice_material_final_2026-11-04.json içinde. Özgün “Film açık” bulgusu korundu ve ham iç etiketler yerine alan başlıklı sade görünüm çalıştı; gerçek masaüstü tarayıcıda oturum genişliği960px ölçüldü. Mobil medya kuralları güncellendi fakat fiziksel Android'de yeniden ölçüm yapılmadı. Gereksiz ilaç sorusu, diş tedavisi öyküsünün sistemik öykü alanına sınıflanması ve zirkonya tabakası/lamine ayrımındaki konu seçimi hâlâ açık kalite sorunlarıdır. Genel CI static-safety, postgres-integration ve application-regressions başarısız; voice kontrolü başarılı. Tüm materyal/işlem/hasta koşulları doğrulandı denmiyor.


### 4 Kasım: soru kapsamı ve materyal kaynağını kullanma denetimi

Önce canlı main ee048021 / runtime 9dff17f5 ile yerel çalışma eşleştirildi. Yeni regresyonlar önce başarısız oldu: açık düzenli ilaç yokluğundan düzenli ilaç adı sorusu üretilebiliyor; son modele materyal başına ilgili birebir kaynak parçaları ayrı verilmiyordu.

- Çıkarım ve son değerlendirmede dar bir soru denetimi eklendi. Hem hastanın açık olumsuz cümlesi hem soru düzenli kullanımı hedefliyorsa isim/doz sorusu çıkarılır. Başka ilaç yok ifadesi aktif ilacı silmez. Haftalık iğne, gerektiğinde kullanım, yeni/planlanan reçete, kısa süreli güncel ilaç ve kapsamı belirsiz genel sorular korunur. Bu bir ilaç uzlaştırması veya genel Türkçe olumsuzluk çözücüsü değildir. Canlıda görülen kapsamı belirsiz genel ilaç sorusu tamamen çözülmüş sayılmaz.
- Mevcut kaynakların uygun klinik kullanım işaretli, hedefe ilişkin birebir parçaları aynı son çağrıya materyal başına en çok bir aday olarak aktarılır (en çok 1800 karakter/hedef). Yeni dış kaynak veya model çağrısı açılmaz. Uzun parçada ilgili bölüm ilk 1800 karakterin dışındaysa hedef çevresinden birebir pencere alınır. Sözcük eşleşmesi klinik uygunluk onayı değildir.
- Her materyal için eşleşen kullanılabilir kaynak sayısı ve kabul edilen kontrol sayısı ayrı dönülür. Böylece kaynak getirilememesi ile kaynak olmasına rağmen kontrol üretilememesi ayrılabilir. Aday bulunması, ekrandaki tamamlanamadı durumunu tek başına değiştirmez.
- Materyal diyalog fixture değişiklikleri CI tetikleyicisine eklendi. Bağımsız inceleme iki aşırı geniş soru bastırma durumunu yakaladı; kapsam düzenli kullanım ile daraltıldı, yeni karşı örnekler önce RED sonra GREEN doğrulandı.

Hedeflerin durumu:

| Hedef | Doğrulanan durum / açık sınır |
|---|---|
| Dinleme boyunca yalnız metin; bitişte çıkarım/kaynak/son kontrol | Yerel yaşam döngüsü ve bütünleşik DOM testleri var; gerçek insan mikrofonuyla bu oturumda tamamlanmadı. |
| Taslak ve başarılı aşamaları yeniden denemede koruma | Aynı açık sayfada kontrol noktaları ve değişmeyen kaynakta son çağrıyı tekrarlamama testli; sayfadan ayrılmada taslak temizlenir. Yenileme sonrası kalıcı kurtarma yok. |
| Yalnız hekim onayıyla hasta kaydı | Seçim/onay kapısı testli; canlı sentetik kontrollerde hasta kaydı yapılmadı. |
| Geniş diş hekimliği ve materyal/işlem kapsamı | 80 kapalı konu, 10 özgül materyal hedefi var; bunlar tüm klinik koşulların doğru değerlendirildiğinin kanıtı değildir. |
| Materyale özel gerçek kontrol | Önceki post koşusu 2 kaynak/0 kontrol; yeni aday aktarımı canlıda ayrıca sınanmalı. Kaynak eksikse uygunluk onayı verilmez. |
| Doğal konuşma ve alan sınıflaması | Genel ilaç sorusu, diş tedavisi geçmişinin sistemik öykü alanına girmesi, tabakalı zirkonya/lamine ayrımı açık. |
| Tarayıcı ve mobil görünüm | Masaüstü 960px önceki sürümde ölçüldü; fiziksel Android tekrar ölçümü tamamlanmadı. |
| Klinik doğruluk | Hekim onaylı altın set, gerçek insan sesiyle kapsamlı ASR ve yanlış alarm/kaçırma ölçümü tamamlanmadı. Sentetik testler bunun yerine geçmez. |

Son tam test sonucu ve yayın kanıtı aşağıya eklenecek. Genel uzak CI yeşil kabul edilmiyor.

Bu değişiklik için son tam yerel doğrulama: **546 Python geçti** (iki mevcut bağımlılık kullanımdan kaldırma uyarısı), **11 Node geçti**. Bağımsız dar kapsam incelemesi71test ile engel kalmadığını bildirdi. Canlı sonuç aşağıda ayrıca kaydedilecek.


### 5 Kasım: alan ve konu kapsamının genişletilmesi

Önceki PR240/830730de306ad37be5b1db03519751f6838ac9bc dağıtımı Render dep-dblh2vtckfvc73fhpr60 ile **4 Kasım14:07:32 Türkiye** itibarıyla live olmuş;5 Kasım tekrar doğrulandı. Önceki materyal aday aktarımının canlı gerçek model tekrarı henüz tamamlanmadı.

Yeni çalışma: diş hekimliğinin15 ana dalında kapalı konu sayısı80'den92'ye çıktı. Daimi dişte canlı pulpayı koruma, yeniden kanal, derin çürük, restorasyon tamiri, dijital ölçü, implant destekli hareketli protez, implant planlama/yükleme ve bakım, periodontal destekle ortodonti, kemik artırımı, çekim sonrası soket ağrısı ve nöropatik/diş dışı ağrı ayrı sabit kapsam/sorgularla desteklenir. Bu, tüm kaynakların veya klinik doğruluğun doğrulandığı anlamına gelmez; yeni konulara ilgisiz genel belge atanmadı. Araştırmanın24 konu/2 arama/3 getirme sınırı değişmedi.

Önceki diş tedavileri (dental_history) ve ağız bakımı/alışkanlıklar (oral_habits) ayrı alan oldu. Çıkarım şeması, atomik ve eski biçim alıntı doğrulaması, zaman/olumsuzluk, düzenleme, son model bağlamı, seçmeli hekim onaylı kayıt ve onaylı geçmişten geri okuma güncellendi. Yeni diş tedavisi geçmişinin sistemik alana gitmemesi model talimatında ayrıldı; eski kayıtlar otomatik taşınmadı. Modelin her vakada doğru sınıfladığı henüz kanıtlanmış değil.

Ekranda Sağlık geçmişi, Önceki diş tedavileri, Ağız bakımı ve alışkanlıklar, İlaç bilgileri, Alerji bilgileri, Konuşulan tedavi planı başlıkları var; kontrol bölümü Tedavi planı ve dikkat edilecekler oldu. Panel JSv25. Zirkonya üzerine porselen tabakası ile lamine veneer ayrımı konu tanımında netleştirildi; gerçek model tekrarına ihtiyaç sürüyor.

Yeni testler önce12 konu ve2 alan/kayıt yolu için RED oldu, sonra GREEN. Bağımsız inceleme tüm11 alan seçilince eski9 alanlık kayıt sınırının422 verdiğini yakaladı; bu da RED→GREEN düzeltildi. Bilinmeyen alan reddi korunuyor. Yeni alanlarda soru cümlesinin hasta beyanı sayılmaması ve eski biçim model özetinin birebir alıntıyı değiştirememesi de testli. Bütünleşik DOM yeni alanları, başlıkları, kanonik değerleri ve onaylı kaydı doğruluyor.

Son tam yerel doğrulama: **577 Python geçti**, **11 Node geçti**; iki mevcut bağımlılık uyarısı. Bağımsız son kayıt sınırı incelemesi58 odaklı testte engel kalmadığını bildirdi. Ayrıntılı15 dal/alan tablosu docs/voice_scope_2026-11-05.md içinde. Bu sayılar klinik doğruluk veya gerçek mikrofon başarısı değildir.

Genel uzak CI hakkında gözlenen kanıt: PR240 static-safety işi40 başarısız/966 başarılı/34 atlanan test raporladı; hata adları academic_v2 altında batch_generation, quiz_contract, study_dialogue vb. PostgreSQL işi test_semantic_postgres.py::test_every_allowed_planner_search_reaches_real_postgres[8] ve[16] için DID NOT RAISE ValueError,42 başarılı/2 başarısız raporladı. Sesli/contract/ready-model kontrolleri geçti. Bunlar genel CI'nin yeşil olduğu şeklinde sunulmuyor; akademik sistem bu sesli kapsam değişikliğinde değiştirilmedi.

Yayın ve canlı ekran/model doğrulaması aşağıya ayrıca kaydedilecek. İnsan mikrofonu, fiziksel Android ölçümü, hekim onaylı altın test seti ve sayfa yenilemede kalıcı taslak kurtarma açık sınırlar olarak duruyor.

PR241/e3a888e0d4c23a0cc3f8494d915f255c1c0d0054, Render dep-dbme73o473hc73e1h9fg **5 Kasım23:16:05 Türkiye** itibarıyla live. Canlı panelde voice-exam.js?v=25 doğrulandı. Yeni post ve implant sentetik metin denemeleri başlatıldı; sonuçları henüz tamamlanmadı. PR241 sesli, contract ve ready-model kontrolleri başarılı; genel static-safety günlükleri yine40 akademik başarısız test, PostgreSQL günlükleri aynı iki semantic_postgres parametresi için2 başarısız test gösteriyor. Genel CI yeşil değil.


5 Kasım canlı gerçek model/metin sonuçları: post-kor **2 kaynak/0 kontrol**, implant **2 kaynak/4 kontrol**; ikisi de kısmi kapsam uyarılı. Kaynak/control sayısı klinik doğruluk oranı değildir. Eski kanal/implant öyküsü yeni dental_history alanına, sigara oral_habits alanına gitti; asistanın şikâyeti ve annenin diyabeti pozitif hasta hastalığı yapılmadı. Yeni başlıklar görüldü. Hasta kaydı için onay verilmedi.

Açık kalite bulguları: postta AAE restorabilite sayfası gelmesine rağmen özgül kontrol üretilmedi (günlükte accepted=0, rejected_reasons={}). Açık düzenli ilaç yokluğu hâlâ belirsiz denilip ilaç adı/dozu soruldu; önceki dar denetim bütün üretim biçimlerini kapsamıyor. İki vakada da verilmiş koşullu hekim yanıtı final iletişim sorularında yok sayılabildi. İmplantta yaklaşık işlem zamanı varken tarih eksik ifadesi tam tarih/ yaklaşık tarih ayrımı yapmadı; hastanın diyabet tanısı yok beyanı öyküde korunmayınca soru yeniden üretildi. Postta mevcut dolgu çıkması ayrıca geçmiş etiketiyle yazıldı. Bunlar çözülmüş sayılmıyor. Kanıt docs/voice_scope_live_2026-11-05.json içinde.

Ek zirkonya tekrarı, işleme onay kutusunda tarayıcının otomatik güvenlik incelemesi tarafından Gemini/Claude'a sağlık verisi aktarımı gerekçesiyle reddedildi. Test fixture'ının sentetik niteliği kontrol edildi, fakat yeniden değerlendirmede erişim yine reddedildi. Sonrasında tamamlanan post ekranının salt okunur görüntüsü de engellendi; ekran görüntüsü oluşturulamadı. Ham tarayıcı/API, başka oturum veya başka yüzeyle engel aşılmadı. Zirkonya tekrarını veya yeni ekran görüntüsünü tamamlanmış göstermeyin; bu sentetik aktarım için açık kullanıcı onayı gerekir.


### 6 Kasım: kaynak temelli anamnez, materyal adı ve yanıt atfı

TDB'nin İZDO üzerinden yayımlanan anamnez kartı, ADA sağlık öyküsü, SDCEP genel/akut/periodontal öykü kaynakları incelendi. Tasarım ve kaynak bağlantıları docs/voice_anamnesis_review_2026-11-06.md içinde. Tarihli COVID talimatları, formdaki kimlik/iletişim ve ilgisiz özel hayat alanları yeni sesli kapsama taşınmadı. Kaynaklardan klinik ilaç yasağı veya otomatik tedavi kuralı üretilmedi.

Yedi anamnez grubunun kamusal inceleme kapsamı mevcut çıkarım ve son değerlendirme çağrılarına eklendi; ayrı bir model aşaması yok. Bitişteki Anamnezde konuşulanlar kartı yalnız dökümde bilgi var/yok durumunu gösterir; yokluk veya tamlık/güvenlik onayı değildir.13 alan arasında ayrı family_history ve materials var: aile öyküsü FAMILY atfıyla, konuşulan materyal ise birebir ad/ürün/tür ve planlanan/güncel/belirsiz durumuyla tutulur. Bilinmeyen marka, siman veya ürün varyantı uydurulmaz. Tüm13 alanın birlikte hekim onaylı kaydı ve yeni kayıtların geçmişten okunması testli; önceki hekim onayı kapısı korunur.

Cevapsız aile sorusu pozitif kayıt yapılamaz; FAMILY/OTHER/UNKNOWN çakışması ve açık klinik ekip birinci kişi yakını hasta ailesine yazılmaz. Hekim yanıtı, hasta geri anlatımı ve atfı belirsiz yanıt ayrı geçici kategorilerle aynı final çağrısına gider. Aynı satırdaki en yakın rol etiketi ve tekrarlanan/etiketsiz alıntı belirsizliği testlidir; gerçek ses konuşmacı ayrımı doğrulanmış sayılmaz.

Özgün klinik kısa alıntı, yalnız yeni istemcide edited:false açıkça geldiyse son modele eklenir; edited:true veya eski istemcide bayrak yoksa eski alıntı gönderilmez. Hekim düzeltmesinin eski konuşmayla geri alınması regresyonla engellenir. Ek alanlar için istemci/sunucu bağlam sınırı32KB, final toplam80.000karakter sınırı korunur. Yeni panel JSv26.

Canlıda yakalanan tam noktalı düzenli ilaç yokluğu + kutu/reçete sorusu RED→GREEN düzeltildi. Bu yalnız açık düzenli kullanım denetimidir; kısa süreli/PRN/aralıklı/planlanan kullanımların soruları korunur. Geçmiş, belirsiz veya planlanan yokluk güncel kullanım cevabı sayılmaz. Genel Türkçe olumsuzluk veya bütün soruların doğruluğu çözüldü denmiyor.

Materyal kontrolünün tamamlanamama nedeni ikiye ayrılır: kullanılabilir kaynak parçası seçilememesi veya aday metin varken hasta özelinde kontrol üretilememesi. Kamusal kimlik/sayı tanılayıcısı günlüklenir; hasta metni/alıntısı yeni günlüğe girmez. Eski post vakasındaki0 kontrol bununla başarılı sayılmaz; gerçek model tekrarı gereklidir.

Son tam yerel doğrulama: **603 Python geçti**, **11 Node geçti**; iki mevcut bağımlılık uyarısı. Bağımsız inceleme aile atfı, soru ve rol geçişi/tekrarlanan alıntı hatalarını yakaladı; RED→GREEN kapatıldı, son odaklı143test geçti. Son kaynak/tamlık testi gerçek model testi değildir.

Bu oturumda yeni canlı model veya mikrofon aktarımı yapılmadı: önceki tarayıcı otomatik güvenlik incelemesinin işleme onayı/origin engeli aşılmadı. Yeni gerçek model, insan mikrofonu, fiziksel Android ve hekim onaylı altın test seti hâlâ doğrulama gerektirir. Sayfa yenilemesinde kalıcı taslak kurtarma, üretici IFU/ürün varyantlarının eksiksiz doğrulanması ve genel akademik CI sorunları çözülmüş sayılmaz. Yayın durumu aşağıya ayrıca eklenecek.

Yayın öncesi ek gizlilik kontrolü: yaş alıntısı içinde isim geçerse final modele gereksiz kimlik taşınabiliyordu. RED regresyonla yakalandı; yaşın yalnız değeri aktarılır, yaş evidence_quote eklenmez. Bağımsız52 odaklı testte engel kalmadı. Son tam yerel koşu **604 Python/11 Node geçti** (iki mevcut bağımlılık uyarısı).


PR242/5738245f96cc5275fb39e44746beda9c8e23790d, Render dep-dbmn3hnf3r2c73aj82cg **6 Kasım09:22:32 Türkiye** itibarıyla live. Dağıtım SHA üzerinden doğrulandı; yeni tarayıcı ekranı veya gerçek model tekrarı yapılmadı. Sesli/contract/ready-model kontrolleri başarılı. Son uzak application-regressions43başarısız/2067başarılı/48atlanan/594alt-test başarılı, static-safety40başarısız/966başarılı/34atlanan, PostgreSQL2başarısız/42başarılı. Genel CI yeşil değil; ek hata adları test_production_optimization.py::test_study_generation_releases_db_connection_and_rechecks_course[False/True] ve test_study_index_v2_isolation.py::test_v2_streaming_is_feature_gated_end_to_end dahil akademik çalışma akışında.

Son uyumluluk düzeltmesi: eski açık istemciler yeni yanıt türünü category alanında görünce tanımsız iletişim başlığı gösterebiliyordu. Yanıt atfı ayrı response_type özelliğine taşındı; mevcut klinik iddia/engel kategorileri değiştirilmedi. Final eski category biçimini de okuyabilir. Bozuk liste/sözlük türleri önceden TypeError veriyordu;6 tür için route testi RED→GREEN, hepsi araştırmaya ulaşmadan422 döner. Son tam yerel doğrulama **611 Python/11 Node geçti**; iki mevcut bağımlılık uyarısı. Bağımsız113odaklı testte engel kalmadı. Uyumluluk yayını aşağıya eklenecek.


## 6 Kasım canlı vaka kampanyası (devam ediyor)

PR24366942150d6c284b924d947de591dd9913365deea,6Kasım09:35:34 Türkiye live doğrulandı. Yeni kullanıcı isteğiyle arayüz erişimi/işleme onayı çalıştı; eski tarayıcı engeli bu kampanya için geçerli değil. Sentetik üç konuşmacılı metinlerle cerrahi/varfarin, perio, implant, kron ve endodonti denendi. Gerçek mikrofon/ASR veya hekim onaylı klinik altın set değil; hasta kaydı yapılmadı.

Perio3kaynak/3kontrol, implant2kaynak/2kontrol; aile öyküsü ayrımı çalıştı. Cerrahi final iki kez422, üçüncüde2kaynak/4kontrolle kısmi hazır; önceki hataların nedeni kanıtlanmadı. Kron çıkarımında tools=2 hatası bulundu. Endodonti2kaynak/0kontrol; özgül pulpa belgesi yerine genel anestezi/AAPD Overview geldi. Plan/yanıt kaybı, bazı yanıtlara rağmen tekrar soru ve kişisel diyabet reddinin genel sistemik yokluğuna genişlemesi açık.

PR244ed0cf827620a030bca5933594e2106bce6e559af6Kasım09:52:20 Türkiye live: gizlilik koruyan stage/type/sabit neden/sayı tanılaması.613Python/11Node,32bağımsızodaklı test başarılı. PR245tek çıkarım aracına disable_parallel_tool_use=True ekledi; payload testiRED→GREEN,614Python,18provider testi. Klinik atıfları otomatik düzeltmez, ek ücretli otomatik çağrı veya başka sağlayıcı yok. Genel CI yeşil değil; sesli/contract/ready-model yeşil, akademik/PostgreSQL hataları mevcut.

Ayrıntı ve sentetik DOM kanıtları: [canlı kampanya](../../voice_live_campaign_2026-11-06.md). Devamındaki yayın ve yeniden deneme sonuçları o dosyaya eklenecek.

Kampanya tamamlandı:8farklı sentetik vaka,6kısmi final/2kaynak erişimi nedeniyle finalden önce durma. İlk hata denemeleri bu sayıya başarı diye gizlenmez. PR2455196f44440c5451fd5aa30d707cbe7c49c6a0405,6Kasım09:56:19Türkiye live ve eski hatalı kron metni yeniden işlendi; araç sayısı1 oldu.614Python/11Node son kodda geçti. Plan/yanıt kaybı, yanlış veneer konusu, özgül endodonti kaynağı yokluğu, süren yara değerlendirme kapsamı ve fazla/genişletilmiş negatif bilgiler hâlâ açık. Ayrıntı kampanya raporunda. Hasta kaydı/mikrofon testi yapılmadı.


## 7 Kasım 2026 — sade sonuç ve yenileme kurtarma

Ana ekran tekrarları birleştirildi; materyal eksikleri klinik kontrollerin içinde, alıntılar/kapsam açılır ayrıntıda. Anamnezde yalnız dökümde netleşmeyen başlıklar var; aynı soru ve iletişim konusu tekilleştiriliyor, farklı hekim iddia dayanakları korunuyor. Kişi kapsamı açık subject etiketleri, literal sağlık öyküsü/plan ve genel kaplamayı lamine saymayan sınır eklendi. NICE başlangıç kaynağı ve kısa araştırma yanıtı yönlendirmesi var; yeni klinik doğruluk iddiası yok. Aynı sekmede 30 dakikalık yenileme kurtarma kontrol noktalarını saklar; rıza/seçim/onay/mikrofon otomatik geri gelmez. 24 konu, kısaltılmış metin, BFCache ikinci pagehide ve eski taslak süresinin yenilenmemesi regresyonları kapatıldı.629 Python/11 Node; iki mevcut uyarı. Bağımsız 232 odaklı inceleme onayladı. Yayın ve gerçek model tekrarları henüz yapılmış sayılmaz. Ayrıntı kabul belgesinde.

7Kasım PR247/d9e3036 ana site11:33:54, vision11:37:51Türkiye live. Güncel dağıtımlar başarılı. Gerçek modelde kron/protez planları korundu ve yanlış veneer seçimi görünmedi. Normal yenilemede ham metin ve tamamlanmış sonuç geri geldi, yeni model çağrısı yoktu. Gerçek historyBack kontrolünde native form metni boşalttı; v28takip düzeltmesi RED→GREEN sınandı. Protez finalinde incompleteprovider sonucu açık, stop/token tanılaması eklendi; henüz sınır artırılmadı. Dar, bütün dayanağı doğrulanmış ilaç/alerji yokluğu doğru alana ayrılıyor; hasta anlatımı gözlenen klinik bulgu sayılmıyor, alerji adı uydurulamıyor.640Python/11Node; canlıv28tekrarı bekliyor. Ayrıntı kabul belgesinde.
