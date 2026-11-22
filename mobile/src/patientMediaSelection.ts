/**
 * Mirrors the web clinical gallery's select-all toggle.
 *
 * The web gallery selects the first capped set when the current selection is
 * partial; it clears only when the selected count already equals the target
 * count. Do not treat any non-empty partial selection as a clear action.
 */
export function patientMediaSelectAllIds(
  selectedIds: readonly number[],
  visibleIds: readonly number[],
  limit: number,
): number[] {
  if (!Number.isSafeInteger(limit) || limit < 1) {
    throw new Error("Klinik görsel seçim sınırı geçersiz.");
  }

  const targetIds = Array.from(new Set(visibleIds)).slice(0, limit);
  const selectedCount = new Set(selectedIds).size;
  const targetCount = Math.min(new Set(visibleIds).size, limit);

  return targetCount > 0 && selectedCount === targetCount ? [] : targetIds;
}

export function patientMediaSelectAllLabel(
  selectedIds: readonly number[],
  visibleIds: readonly number[],
  limit: number,
): string {
  if (!Number.isSafeInteger(limit) || limit < 1) {
    throw new Error("Klinik görsel seçim sınırı geçersiz.");
  }

  const targetCount = Math.min(new Set(visibleIds).size, limit);
  return targetCount > 0 && new Set(selectedIds).size === targetCount
    ? "Seçimi kaldır"
    : `İlk ${limit} Görseli Seç`;
}
