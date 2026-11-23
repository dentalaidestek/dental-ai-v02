/** Validate the owner-scoped patient identifier received by the standalone media route. */
export function resolvePatientMediaRouteId(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
    ? value
    : null;
}
