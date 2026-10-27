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
