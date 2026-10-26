# Finish-only live examination

The main live microphone path now retains completed transcription segments in the open browser page. It does not call clinical extraction during listening or pause. The Finish button waits for provider flush, then extracts clinical context and verified closed taxonomy topics in bounded chunks, retrieves sources and runs the existing final review. Alternative 90-second clips now also request transcription only and append to the same draft; clinical extraction is deferred to the explicit evaluation/Finish action. Legacy API clients without the new header keep the old response contract.

## Draft lifecycle

- Full transient transcript: at most 72,000 JavaScript characters / 216,000 UTF-8 bytes accepted for processing. New listening is blocked at 60,000 / 180,000 to leave space for buffered final speech.
- Extraction chunks: at most 12,000 characters / 36,000 bytes, split losslessly at whitespace where possible. The existing 24 KB structured-context cap remains separate. Over-limit context reports an error and retains the transcript; it is never silently truncated.
- Successful chunk cursor survives extraction failures in the open page. Final-review retry does not repeat extraction. Editing/replacing transcript invalidates extraction checkpoints. Editing extracted fields invalidates the final result and preserves clinician edits.
- No browser or server transcript persistence. Discard, save or navigation clears transient data; unsaved navigation warns. Closed/reloaded pages cannot recover the transcript. Failure recovery is only within the open page.
- A normal short examination uses one extraction plus one final review, excluding transcription. Longer examinations need additional extraction calls. Unchanged partial-source retries skip the final model using a fingerprint bound to clinical context, prompt, model and public evidence (excluding retrieval timestamps). Total source outages stop before the final model. Explicit retry of an ambiguous provider/network timeout may still incur another provider charge; this change does not provide server-side idempotency.
- After pause or connection failure, an incomplete flush remains incomplete; pressing Finish cannot certify it. The server drains finalized segments for a bounded three-second window instead of closing after the first segment. An eight-second client watchdog exits a hung stopping state. This is a bounded heuristic, not proof of complete real-provider speech capture.
- No speech-triggered Finish command. An unconfirmed final flush requires the clinician to inspect the text and explicitly run evaluation.

## Closed source topics

Existing sixteen areas remain available. Five explicit endodontic topic IDs were added: instrument separation, root perforation, missed canal, postoperative pain and irreversible pulpitis. IDs are in the extraction schema enum and validated by the existing normalization/context contracts; original speech quotes are required. Fixed search strings are server-owned. No model-authored free-form literature query is introduced. The drug lookup still uses its existing validated ingredient vocabulary.

Topic selection is not diagnosis. Absent, historical or uncertain findings must not become confirmed patient findings. Unsupported conditions remain outside this bounded taxonomy. Real clinical recall and source-query quality have not been established by the software tests.

## Source retrieval

Fixed documents use 6 workers and at most 12 admitted jobs. Source groups use 4 workers and at most 8 admitted jobs. Shared outstanding document requests prevent duplicate fetches. Waiting ends after 12 seconds for documents / 16 seconds for groups; running threads cannot be forcibly killed and retain admission slots until completion. These are wait budgets, not an end-to-end execution guarantee. Local drug fallback and model review are separate stages.

Successful documents cache for one hour; failures cache for ten minutes. Total source excerpt text is bounded to 40,000 characters and final prompt+data to 80,000 characters. Omitted source text is reported as unavailable; grounding uses the same included excerpts. Existing keyword fallback, GDC communication selection, clinical prompt safeguards and response fields remain intact. Timing logs contain counts/durations rather than clinical text.

## Optional local PubMed catalogue

Default remains `VOICE_LITERATURE_MODE=remote`. For a pilot, build an offline snapshot with:

```sh
python -m scripts.build_voice_literature --db /persistent/literature.sqlite
```

Set `VOICE_LITERATURE_MODE=local` and `VOICE_LITERATURE_DB` only after reviewing and validating a populated catalogue. Local retrieval uses verified topic memberships ranked by evidence level/date; it never sends patient text to PubMed or falls back to network on a missing/corrupt index. This setting changes only the PubMed layer: other existing source groups can still make network requests.

Build uses all 21 closed topics and at most 200 relevant PubMed records per topic, without an arbitrary publication-date lower bound. Full abstract sections are retained; existing eligibility metadata still restricts clinical use. A complete replacement drops stale records and topic memberships. Transport/error envelopes or incomplete fetched PMID batches abort publication, preserving the previous file. All source metadata is a selection aid, not a guarantee of scientific quality or clinical applicability. A genuinely successful empty search can remove a topic; inspect the build report before rollout. Weekly scheduling and durable storage placement are operator rollout steps, not installed by this PR.

## Verification

194 Python tests and 10 Node controller/worklet harnesses passed locally, using pinned web dependency versions for the tested subsystem. Tests include closed topics, source grounding, ownership/consent/atomic apply, lossless splits, checkpoint recovery, no mid-speech extraction, source queue/cache bounds, normal PubMed XML headers and error-batch protection. Two upstream deprecation warnings remain. Independent code review findings were repaired with regression tests.

This workspace contains the voice-subsystem snapshot, not every repository test. A dedicated PR workflow runs all voice Python tests and browser harnesses against the complete checkout. A direct synthetic fixed-topic PubMed ESearch attempt timed out in this runtime, and the hosted web fetch could not access the endpoint. Real microphone, actual model calls, real catalogue ingestion, clinical accuracy and production load are not verified here. No production merge or deployment is performed.
