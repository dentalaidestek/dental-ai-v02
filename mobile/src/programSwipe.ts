/**
 * Match the web Program page's horizontal swipe contract.
 * Returns 1 for next period, -1 for previous period and 0 for no navigation.
 */
export type ProgramSwipeDirection = -1 | 0 | 1;

export function programSwipeDirection(dx: number, dy: number): ProgramSwipeDirection {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return 0;
  if (Math.abs(dx) < 65 || Math.abs(dx) < Math.abs(dy) * 1.5) return 0;
  return dx < 0 ? 1 : -1;
}
