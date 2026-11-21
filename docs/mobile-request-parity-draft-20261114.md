# Native consultation-request parity draft — 14 November 2026

Inspected web source: app/templates/expert_request.html,
expert_support_request_page/create in app/main.py and the existing receipt service.
Continues the native chat draft; it is not a release-ready completion claim.

## Source changes
- Patient profile now opens the expert directory with its selected patient.
  Previously it opened NewConsultation without an expert, which the old form
  dereferenced unconditionally.
- The expert directory forwards patient context and disables requesting a passive
  expert. The form loads canonical availability, capacity, fee, urgency labels and
  response duration; the write rechecks the existing web eligibility rules.
- Native patient selection returns an actual owned record ID. Free-text Patient ID
  input is removed. Optional patient linkage can be cleared explicitly.
- Mirrors the web request fields: selected clinical media, urgency, tooth/region,
  clinical summary, requester opinion and question. Shows the web privacy summary
  and fee. Only explicitly selected owned media are sent; no AI result is attached.
- A stable request_key is forwarded to the existing web receipt/hash mechanism.
  The old adapter omitted it. The exact pending payload/key is persisted with
  SecureStore before POST and frozen after an uncertain result. Retry checks an
  owner-scoped receipt and uses the same key, rather than generating a second case.
- Successful creation/recovery opens the specific ConsultationChat case.
- Backend rejects unowned patient/media selections before creating a new case,
  preserves meaningful plain web errors, and accepts only a confirmed case redirect.
- Four backend and three client regression cases authored and wired into CI.

## Limits
The execution environment remains unavailable. No dependency installation,
TypeScript check, test run, Expo export, native build or two-account device test
was executed for this commit. The seven new tests are unexecuted. Static source
review/readback is not functional verification.

Remaining chat work is not represented as complete: general PDF/audio selection,
protected native file opening/playback, bitmap image editing/compositing,
case-shared media selection in chat, durable text/media send idempotency,
deadline/reconnect/device acceptance and full web/native regression tests.
Compatible native package versions were inspected in Expo's sdk-54 source, but
required packages were not added by guessing a dependency lockfile while npm and
the native build environment are unavailable.

No main merge, live deploy or store publication. The new backend routes require a
separately approved deployment; the current installed APK does not gain them
merely because source was committed.
