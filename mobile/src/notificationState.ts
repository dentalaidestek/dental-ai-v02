export type NotificationReadState = {
  created_at: string;
  read_at?: string | null;
};

/** API datetimes without an explicit offset are naive UTC, like the web client treats them. */
export function parseNotificationTimestamp(value: string): number {
  if (typeof value !== "string" || !value.trim()) return Number.NaN;
  const raw = value.trim();
  const hasOffset = /(?:Z|[+-]\\d{2}:\\d{2})$/i.test(raw);
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
