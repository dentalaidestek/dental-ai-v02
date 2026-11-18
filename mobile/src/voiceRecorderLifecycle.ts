/**
 * Distinguish an unexpected recorder stop from the normal stop/start gap
 * while rotating a bounded native audio segment.
 *
 * Expo Audio reports isRecording=false while a segment is being finalized.
 * The caller resets its previous-recording marker before invoking stop(),
 * then uses this guard for genuine stops outside an owned transition.
 */
export function isUnexpectedVoiceRecorderStop(
 wasRecording:boolean,
 recordingRequested:boolean,
 hasActiveSegment:boolean,
 transitionInProgress:boolean
):boolean{
 return wasRecording&&recordingRequested&&hasActiveSegment&&!transitionInProgress;
}
