# External clinical review follow-up

User authorized reviewing Claude's findings against current code and continuing justified improvements without routine approval questions. Existing work preserved on feature/voice-clinical-review-20261029; publish a separate draft PR, no automatic deployment or merge.

Scope chosen after reading current normalization, final prompts, UI state and evaluation scripts: explicit transient clinician assertions plus repeated routing/attribution measurement. Existing alternatives were prompt-only changes (no visible coverage), unconditional hand-coded clinical rules (not validated and can create false alarms), and the current single-review route with bounded transient assertion anchors. Selected the last; no extra production model call or clinical correctness claim.

- RED then GREEN: preserve an exact clinician_statement as transient data, never patient record; final review shows unverified assertions rather than silently clearing them.
- Integrated rendered-panel RED then GREEN: assertions survive into final payload, displayed uncertainty, explicit save excludes them, overflow preserves draft and blocks incomplete finalization.
- RED then GREEN: five-attempt consistency/failed-attempt reporting, provider-error stop and explicit model-call budget.
- RED then GREEN: topic routing alone cannot pass omitted, misattributed or ungrounded clinician assertions.
- Added six independent synthetic attribution cases (total 50); expectations provisional, not clinical gold labels.
- Full offline verification and publish validation records; real provider/microphone blocked by missing configuration / unavailable real device coverage.

Remaining clinician-adjudicated gold set, actual source-entailment and alert-sensitivity measurements, structured medication reconciliation, source/version coverage and feedback/consent design are documented in docs/voice_clinical_validation_protocol.md. Do not mark those complete from this patch.
