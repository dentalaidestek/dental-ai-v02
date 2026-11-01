# Published case dialogue implementation plan

**Goal:** Add source-traceable, everyday Turkish three-speaker conversations to the existing voice evaluation flow.

**Architecture:** Keep the original 50-case fixture unchanged. A separate draft fixture contains 12 published-case-inspired pairs (24 dialogues), public source provenance, contrast conditions and clinician review checklists. The existing extractor evaluator accepts a fixture path and assistant turns; clinical outcome adjudication remains manual and separate.

**Constraints:** No real patient identities or copied conversations; no assumption that published treatment is current guidance. No provider substitution, production prompt changes, medical rules, deployment or merge. Source checklists and route labels are provisional, never clinician-approved gold labels. Expectations never enter the provider request.

**Work:**
- [x] Add failing tests for assistant/8-turn input and fixture CLI selection.
- [x] Extend evaluator to 2–12 turns and Asistan; add --fixture without changing the default.
- [x] Write 24 original dialogues from 12 published case reports; record what was changed, and distinguish invented controls from reported facts.
- [x] Validate source references, pair links, topic IDs and draft labels; add safety scoring checks that detect forbidden routes and speaker attribution.
- [x] Run available regression tests and explicit provider preflight; report unavailable validation without synthetic success claims.
- [x] Document evidence and publish only intended files to existing draft PR using expected_sha.

**Review focus:** Assistant personal history must not become patient history; missing symptoms do not prove a negative; a possible diagnosis does not become a confirmed disease; planned actions are not completed; clinical red flags cannot wait for the finish-time evaluator.

Verification: 448 Python / 11 Node tests passed. Real provider preflight exited 2 with missing_provider_configuration and model_calls=0. Independent read-only review found no actionable issue. Source/clinical labels still draft; clinician adjudication and real microphone tests remain outstanding.
