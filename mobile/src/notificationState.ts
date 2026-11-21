export type NotificationReadState = {
  created_at: string;
  read_at?: string | null;
  is_read?: boolean;
};

/**
 * Prefer the canonical read flag when the API supplies it. Older mobile
 * responses exposed only read_at, so retain that as a backwards-compatible
 * fallback until every supported server has the canonical field.
 */
export function normalizeNotificationReadAt(item: NotificationReadState): string | null {
  const isRead = typeof item.is_read === "boolean" ? item.is_read : Boolean(item.read_at);
  if (!isRead) return null;
  if (typeof item.read_at === "string" && item.read_at.trim()) return item.read_at;
  return typeof item.created_at === "string" && item.created_at.trim() ? item.created_at : null;
}

/** API datetimes without an explicit offset are naive UTC, like the web client treats them. */
export function parseNotificationTimestamp(value: string): number {
  if (typeof value !== "string" || !value.trim()) return Number.NaN;
  const raw = value.trim();
  const hasOffset = /(?:Z|[+-]\d{2}:\d{2})$/i.test(raw);
  return Date.parse(hasOffset ? raw : raw + "Z");
}

/** Optimistically mark only notices that existed at the captured cutoff. */
export function applyNotificationReadAllSnapshot<T extends NotificationReadState>(
  items: readonly T[],
  seenBefore: string,
): T[] {
  const cutoff = Date.parse(seenBefore);
  if (!Number.isFinite(cutoff)) {
    throw new Error("Geçersiz bildirim zaman sınırı.");
  }
  const readAt = new Date(cutoff).toISOString();
  return items.map((item) => {
    const createdAt = parseNotificationTimestamp(item.created_at);
    if (!Number.isFinite(createdAt) || createdAt > cutoff || item.read_at) {
      return item;
    }
    return { ...item, read_at: readAt };
  });
}
