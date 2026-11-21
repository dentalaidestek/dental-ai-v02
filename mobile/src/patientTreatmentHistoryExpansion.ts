/** Keep an expanded treatment history open on same-scope refreshes only. */
export function patientTreatmentHistoryExpansionAfterRefresh(
  expanded: boolean,
  previousScope: string,
  nextScope: string,
): boolean {
  return expanded === true && previousScope.length > 0 && previousScope === nextScope;
}
