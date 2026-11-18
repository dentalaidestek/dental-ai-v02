/**
 * A voice-anamnesis snapshot is refreshed only when its focused screen returns
 * from a real background/inactive transition. Repeated "active" notifications
 * are ignored, so this remains event-driven rather than a polling loop.
 */
export function shouldRefreshPatientVoiceHistoryOnResume(
  previousState: string | null | undefined,
  nextState: string,
  focused: boolean,
): boolean {
  if (!focused || nextState !== 'active') return false;
  return previousState === 'background' || previousState === 'inactive';
}
