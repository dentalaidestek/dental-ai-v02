# Claude native web connection — unfinished checkpoint (2026-10-27)

Status: implementation exists in the unavailable local workspace, is NOT published in this PR and is NOT deployed. This checkpoint publishes documentation only. Existing PR code remains at the previously verified everyday-speech implementation until the pending files can be recovered and finalized.

Workspace: /workspace/scratch/9fe71751f53b/dental-ai
Local branch: feature/voice-finish-review
Starting local HEAD: b6244d2
Starting remote HEAD: 44ebf3140a298e8429c7c0b44627743842eb5679
Target remote branch: work/voice-finish-review-20261026
PR: #216 (keep draft). No main merge/deployment.

## Requested architecture

The user explicitly requested connecting Claude web research. The research stage may generate search expressions/URLs within trusted public domains; this supersedes the previous free-query restriction only for isolated public research. Extraction still chooses validated topic IDs. Do not expose raw patient conversation/private fields to native web tools.

Pending implementation:
- provider.research_message in app/voice_exam_review_provider.py: same configured Claude/key, shared request budget and HTTP transport, no strict JSON output on native research.
- app/voice_exam_web_research.py: native web_search_20250305 and web_fetch_20250910; two search / three fetch uses; at most two HTTP requests; caller wait45sec; trusted-domain allowlist; public scopes only; closed public generic-name vocabulary before spelling validation.
- Literal fetched text only as evidence. Validate actual tool IDs and HTTPS URLs; handle native char_location citations by document_index across pause turns. Search snippets/model prose alone are not evidence. PDF/base64 and unassessed journal limitations are explicit.
- public-only bounded64-entry cache with singleflight workerpool2/capacity4; successful1h, partial60sec, failures15sec TTL; deep-copy results and isolate test pools.
- app/voice_exam_research.py dispatch: claude_web default, explicit VOICE_EXAM_SOURCE_MODE=legacy, no automatic legacy fallback after web failure.
- Finish and manual clinical source boundaries route through dispatch. Final grounded review remains separate, with raw patient data excluded from research. Normal flow becomes extraction + research + final review (3 model stages, up to4 HTTP requests if research pauses); this is NOT the previous unchanged-call-count design.
- Research material is marked research_material_unverified / research_background_unverified, not topic-specific verified evidence. JS v17 renders this distinction.
- The key/model/org web capability is not configured in this runtime; no real native-tool call was verified.

## Verified before environment loss

Adapter author reported complete Python suite270 passed, two existing dependency deprecation warnings; adapter-specific30 mocked tests passed. Parent verified3 native transport tests,4 dispatch tests and1 mocked integrated final-review test (public research -> private grounded final review -> cache/fingerprint retry with no further calls). Native-status jsdom regression was observed RED then GREEN. Full Node suite after the native changes was not completed here. None of these results proves live native-tool availability or clinical accuracy.

## Important unresolved review finding

Every adapter gap is currently named *-unavailable*, and retryable_unavailable treats any such marker as transport failure. Consequently final.finalize raises when references are empty even for permanent/non-network states. Reproduced by reviewer without network:
retrieve_web([],[]) -> web-research-unavailable:no-public-concepts -> retryable True -> valid routine examination cannot finish.

Fix with RED->GREEN regressions before enabling/publishing pending product code:
1. No-public-concepts must allow the normal limited summary/clarification path, with no research provider call.
2. Completed research with no evidence must remain distinct from transport/provider/capacity failure.
3. Unsupported-only document formats and unverified generic-name scope gaps must not imply a recoverable network outage or an infinite retry path.
4. Genuine all-source transport/configuration failure must still stop before charging patient-specific final review.
5. Keep explicit clinical/source gaps and never treat no evidence as safety.
Use distinct non-retryable gap markers or typed status; do not globally weaken all-source outage protection.

Bounds caveats:45sec is a caller wait, not hard worker/provider cancellation (shared urllib3 read timeout is inactivity-based). Running workers retain admission slots. Native max_content_tokens excludes PDFs; rejecting a PDF after API processing does not impose a hard provider input-token cost cap. Keep call/tool limits and disclose these limits honestly.

## Resume

Recover current git status/diff first; do not redo the earlier broad taxonomy/daily-speech commits. Pending paths include:
app/voice_exam_review_provider.py, app/voice_exam_web_research.py, app/voice_exam_research.py, app/voice_exam_final.py, app/voice_exam_clinical.py, app/static/voice-exam.js, app/templates/voice_exam_panel.html, tests/test_voice_native_transport.py, tests/test_voice_web_research.py, tests/test_voice_research_dispatch.py, tests/test_voice_web_final_integration.py, tests/voice_integrated_dom.cjs, docs/superpowers/plans/2026-10-27-claude-web-research.md.

Run PYTHONPATH=.:../testdeps python -m pytest -q
Run PYTHONPATH=.:../testdeps NODE_PATH=../domdeps/node_modules ../verification-runtime/node-v26.12.1-linux-x64/bin/node --test tests/voice*.cjs
Run git diff --check.
Only after the unresolved finding is fixed and fresh checks pass: update docs/PR, commit, and publish changed paths atop fresh remote tree with expected_sha. No main merge/deployment.
