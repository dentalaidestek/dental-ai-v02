/**
 * Return true only for a real background/inactive -> active transition.
 * Screens load on navigation focus; this gate handles app resume without
 * turning repeated "active" notifications into duplicate clinical reads.
 */
export function shouldRefreshOnAppResume(
  previousState: string | null | undefined,
  nextState: string,
  focused: boolean,
): boolean {
  if (!focused || nextState !== 'active') return false;
  return previousState === 'background' || previousState === 'inactive';
}
