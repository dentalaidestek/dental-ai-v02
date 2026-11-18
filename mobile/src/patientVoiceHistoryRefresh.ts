import { shouldRefreshOnAppResume } from './appResumeRefresh';

/**
 * Keep the existing voice-history API while sharing the same transition gate
 * with the other patient screens.
 */
export function shouldRefreshPatientVoiceHistoryOnResume(
  previousState: string | null | undefined,
  nextState: string,
  focused: boolean,
): boolean {
  return shouldRefreshOnAppResume(previousState, nextState, focused);
}
