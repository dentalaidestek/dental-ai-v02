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
