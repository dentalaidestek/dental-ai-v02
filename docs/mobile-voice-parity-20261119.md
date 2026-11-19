# Mobile voice examination parity — 2026-11-19

## Web flow inspected first

The web reference is `app/templates/voice_exam_panel.html` plus
`app/static/voice-exam-live.js`, `voice-exam.js`, and
`voice-finish-draft.js`.

The web flow keeps live speech as transcript-only input. On the explicit
`Muayeneyi bitir` action, it drains the final buffered segment, processes the
bounded transcript chunks sequentially, then calls `finalizeReview()` for the
whole examination. The final source-backed result is displayed separately
from the later clinician selection/save action.

## Native gap and correction

Before this change, `mobile/src/VoiceExamEntry.tsx` completed
`extractVoice()` after the explicit recorder finish but stopped at the
extracted review. A second clinician action was required to call
`finalizeVoice()`. This was a functional difference from the web workflow.

The native flow now:
1. Keeps speech recognition/transcription separate from clinical extraction.
2. Waits for the explicit recorder finish or the manual
   `Muayeneyi Bitir ve Metni Çözümle` action.
3. Processes the existing 12,000-character / 36 KB chunks and preserves the
   encrypted account/patient/session checkpoint.
4. Passes the exact newly extracted review and the exact full transcript to
   `finalizeVoice()` after extraction succeeds.
5. Allows a retry after a final-review error or after the clinician edits the
   extracted draft.

The explicit recorder-finish path bypasses only the stale recorder busy/session
flags that can remain true until the recorder's own `finally` callback. It
does not bypass consent, patient scoping, the extraction lock, or the request
generation checks.

The final review is still **not** written to the patient record automatically.
`NativeVoiceApproval` remains the separate explicit clinician approval and
idempotent write path.

## Approved anamnesis privacy

The web/backend approved-history contract intentionally returns no transcript
quote. The mobile client previously accepted a non-empty `quote` field even
though the patient-profile UI did not render it. The type is now
`quote: ""`, and `getVoiceHistory()` rejects any non-empty quote. Valid
fixtures were aligned with that contract.

Additional regressions cover:
- A late approved-history response from a previous account when the patient
  numeric ID is unchanged.
- Refresh only for the matching patient's `PATIENT_UPDATED` event.
- Retry a failed source-backed final review without repeating completed extraction chunks.
- Rejection of a history response that attempts to include transcript text.

## CI findings and limits

At the inspected branch head before this work, GitHub reported no commit
statuses and no check runs. The 18 November Android APK push runs inspected
(44273348890, 44273301976, 44273188492) ended before step 1 with
`runner_id=0`, an empty runner name, and no job steps. Those records do not
show a TypeScript, Gradle, or test failure; they show hosted-runner allocation
failure.

The Android and security recovery workflows remain manual-only to avoid
restarting the previous repeated CI notification stream. No workflow was
dispatched during this work. Therefore the new native tests and full Android
typecheck have **not** been executed in this run.

## Remaining validation

- Run `cd mobile && npm test` on a working Node environment.
- Run the manual Android workflow only when hosted runner allocation is
  confirmed healthy.
- Revisit the existing `npm audit` findings separately; do not use
  `npm audit fix --force` because it can force an Expo major-version change.
- Device-level microphone, foreground/background, Android build, and
  60,000-user load validation remain outstanding.


## Additional web-parity regression — terminal finish state

A second pass compared the actual web control lifecycle in
`app/static/voice-exam-live.js` with
`mobile/src/NativeVoiceRecorder.tsx`.

On web, `stateChanged()` hides the microphone start control whenever
`finished === true`. The native recorder previously kept rendering
`Devam et` after `draft.ended` was persisted. Its `start()` guard did not
check that terminal flag, and the prop-to-draft synchronization effect reset
`ended:false` whenever the transcript changed. That meant editing the
already-finished transcript could reopen the microphone in the same exam
session; a repeated finish action could also repeat the ASR/final-review
handoff.

The native flow now:
- Uses `canResumeVoiceDraft()` as a shared terminal-state predicate.
- Rejects microphone start when the draft is ended or still has pending audio.
- Rejects a second finish callback for an already-ended draft.
- Shows `Muayene tamamlandı` and disables both start and finish controls.
- Preserves the ended flag when the clinician edits the transcript; text edits
  remain available for a fresh extraction/final review but do not reopen audio.
- Requires clearing the local draft before starting a new voice session.

A component-level regression now records and finishes one session, attempts
both controls again, edits the transcript, and verifies that the session stays
closed and no second ASR or finish callback occurs. The shared helper also has
fresh/ended/pending-segment assertions.

## Current branch CI snapshot

At the previously inspected HEAD `382df6282241ba7bdebc7f2d7e0b0b9df26e77b8`,
GitHub returned zero check runs and a pending commit status with no status
entries. The most recent Android APK push run available for inspection,
`44273348890`, targets an older SHA
`5b692f7637d60136446f1efaa09178009ba1d209`; its only job ended before step
1 with `runner_id=0`, an empty runner name, and no steps. It is not evidence
that this branch's typecheck or tests failed or passed. Both Android and
security recovery workflows are still manual-only; no workflow was
dispatched during this change.


## Native audio-file import parity — transcript budget and MIME discovery

A fresh comparison inspected the web file input in `voice_exam_panel.html` and
the `audioFile` handler in `voice-exam.js`, then traced the native
`DocumentPicker` → private cache copy → duration validation → encrypted
account/patient draft → idempotent ASR receipt flow.

The native audio-file import was already present on this branch, so this pass
did not duplicate it. It found two remaining web/native differences:

- The web UI refuses another audio segment when the current transcript reaches
  54,000 characters (and its general control state also accounts for the
  180 KB UTF-8 boundary). Native recording and file import previously had no
  equivalent pre-capture guard. The later 72,000-character draft limit could
  reject an already-paid ASR result after upload.
- The native document picker listed only canonical MIME strings. Android and
  document providers can report WAV/M4A aliases such as `audio/x-wav` and
  `audio/x-m4a`; the strict resolver already understands these aliases, but
  the picker filter could hide them before validation.

The native flow now:
- Uses a shared `canAcceptVoiceAudioInput()` predicate matching the web
  54,000-character / 180 KB pre-ASR threshold.
- Disables both new microphone capture and file selection at that threshold,
  including the automatic 15-second recording rotation.
- Rechecks the latest transcript after asynchronous duration parsing and
  before persisting a new file segment.
- Uses the broad platform picker filter `audio/*`, then still rejects every
  unsupported MIME/extension combination through `resolveVoiceAudioAsset()`.
  This allows platform aliases to be selected without widening the accepted
  upload formats.
- Keeps the existing consent checks after picker, copy, and duration awaits,
  private-cache containment, 8 MiB / 90.5-second limits, and owner/patient
  idempotent ASR request key.

Regressions added to the existing `voiceWorkflow.cjs` and
`voiceAudioImport.cjs` suites cover the 54,000-character boundary, UTF-8 byte counting (with 180 KB as a
second defensive ceiling), the disabled native controls, MIME aliases, strict
AAC rejection, and the ordering of consent/budget checks before
persisting a segment. Both files are already included in `test:beta` and
the manual `security-recovery` workflow; no new workflow trigger was added.

## CI snapshot for this pass

Starting branch HEAD was `a236cd3be5af9d8e427595a3a151e9f3757daa80`.
It had zero check runs and zero commit status entries. The inspected
18 November APK run `44273348890` had one job with `runner_id=0`,
an empty runner name, and no steps; fetching its job log returned
`BlobNotFound 404`. This is a runner/log-retention infrastructure failure,
not a recorded TypeScript or test assertion failure.

The Android and security workflows remain `workflow_dispatch` only.
No CI run was dispatched in this pass. The new tests, full
`npm test`, Android typecheck, and device-level import/cancel/recovery
behavior remain unexecuted and must not be treated as passing.


## Post-change branch verification

The audio-import parity work was committed in seven fast-forward commits after
starting HEAD `a236cd3be5af9d8e427595a3a151e9f3757daa80`. The final source
comparison reports exactly five changed files and no divergence from the PR
base. The PR head matches the branch head.

The new branch head has zero GitHub check runs and zero commit status entries.
No Android or security workflow was dispatched. The isolated helper/MIME test
run passed 5/5 locally, but it is not a substitute for the repository's full
`npm test`, TypeScript project check, React Native component suite, or Android
build. Those remain unverified.
