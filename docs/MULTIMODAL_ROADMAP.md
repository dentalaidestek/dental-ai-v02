# Dental AI — modality roadmap

## Phase 1 — PANORAMIC (current priority)

Do not start production deploy before panoramic Vision48 runtime validation is complete.

Acceptance target:
- 48/48 canonical findings have a real executable motor strategy.
- Ready public checkpoints are preferred when they are specific enough.
- If a ready checkpoint is missing or fails validation, train a dedicated specialist.
- Positive + negative panoramic smoke validation is required before a finding is marked PASS.
- General LLM providers never receive radiograph pixels; they receive only structured findings/FDI/measurements/clinical text.

## Phase 2 — PERIAPICAL

Do not force the panoramic 48-finding catalog onto periapical images. Build a modality-specific catalog around findings that are actually visible and clinically useful in this field of view.

Initial high-priority candidates to research/validate:
- periapical radiolucency / apical lesion
- periapical radiopacity / condensing pattern
- widened PDL
- loss/interruption of lamina dura
- root canal treated
- underfilled root canal
- overfilled root canal
- broken endodontic instrument
- apical surgery / retrograde filling pattern
- internal/external root resorption
- root fracture / tooth fracture where visible
- caries / deep caries when field of view supports it
- recurrent caries around restorations
- post/core, crown, filling, implant
- peri-implant bone loss when implant is visible

Final catalog must be based on ready-model/dataset evidence and modality-specific validation, not by copying the panoramic list.

## Phase 3 — BITEWING

Bitewing should prioritize findings for which this view is naturally strong.

Initial high-priority candidates to research/validate:
- proximal/interproximal caries
- deep caries
- recurrent caries
- restoration/filling/crown/inlay-onlay
- restoration margin/overhang candidate if a reliable dataset exists
- calculus
- horizontal bone loss
- vertical/angular bone loss when visible
- furcation bone loss when visible
- secondary caries around restorations

Do not include panoramic-only anatomy/pathology classes merely to inflate the finding count.

## Phase 4 — INTRAORAL PHOTO / SHORT VIDEO

This is a separate visual modality from radiography and must use a separate finding catalog and separate confidence/validation thresholds.

Initial high-priority candidates to research/validate:
- visible caries/cavitation
- visible restorations/crowns/bridges/implants
- missing tooth / spacing / crowding / malalignment
- fractured/chipped tooth
- calculus / plaque if datasets are sufficiently reliable
- gingival inflammation/redness
- gingival recession
- discoloration/staining
- orthodontic appliance
- visible mucosal/soft-tissue lesion candidates only if a sufficiently strong dedicated dataset/model exists

Photo/video output must never be presented as radiographic or volumetric diagnosis.

## Shared implementation rules

1. One public product: dentalai.tr.
2. Each modality has its own router, catalog, model manifest, thresholds and validation matrix.
3. Shared FDI/tooth identity layer may be reused when technically valid.
4. Never convert a generic helper class into a more specific pathology without validated evidence.
5. Never treat single-image confidence as model accuracy/mAP.
6. Ready model first; train only when a sufficiently strong ready model is unavailable or fails validation.
7. Training checkpoints must be written to persistent storage and support resume from last checkpoint.
8. No 48/48 or modality-complete claim until the corresponding runtime validation matrix is PASS.
