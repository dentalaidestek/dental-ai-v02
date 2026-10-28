# Claude-managed web research implementation plan

User explicitly requests connecting Claude web research. This supersedes the earlier ban on model-authored search expressions for the isolated public research stage. Existing clinical extraction still selects quote-validated closed topic IDs; no raw patient wording becomes an external query.

Design: Finish extraction -> Claude native web research on public topic scopes/generic drug names only -> existing grounded patient-specific final review. Search/fetch use the same configured review provider/model and trusted-domain allowlist. This adds a bounded research model stage and native search usage; no unchanged-call-count or cost claim. Separating public research from patient-specific structured review prevents native tools from seeing patient text and avoids mixing native citations with strict JSON output.

- [x] RED: provider-native tools payload, no structured-output constraint, same key/model/budget transport, no plaintext secret logging.
- [x] Implement provider.research_message and bounded native adapter (two search uses, three fetch uses; at most two HTTP messages; caller waits up to 45sec (not a hard worker/cost cap)). Parse actual tool results, never model prose as source evidence. Unsupported PDF/failed tools explicit gaps; bibliography alone cannot ground claims.
- [x] Default source mode claude_web in the Finish/manual clinical source boundary; explicit legacy mode retained. No silent fallback if web support/config unavailable. Native search expressions/URLs may vary within allowlisted public domains; fixed document route is no longer the only source path.
- [x] Cache/singleflight by public scope+configured model/tool policy to preserve successful source work on retry; retain clinician approval, quote grounding, failure draft and final fingerprint behavior.
- [x] Run full offline Python/Node tests and opt-in safe source smoke. Real model requires existing configured credentials/console capability; absent config must stop without provider/network call.
- [x] Independent review, actual limitations/cost/call topology docs, commit and expected-SHA publish to existing draft PR. No main merge/deploy or new account/credential retrieval.

Official references: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool and https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool . Native tool success/error blocks and pause_turn must be interpreted, not inferred from HTTP200. Research evidence has to bind to genuine successful web_fetch results with validated URLs and literal returned text.

2026-10-28 completion: native permanent-gap versus transport-error P1 reproduced RED and fixed. Full offline suite 275 Python + 11 Node26 harness files passed. Existing config is missing; live evaluator made zero model calls. See docs/voice_finish_review.md for fresh validation and limits. No main merge/deploy.
