export type NotificationReadState = {
  created_at: string;
  read_at?: string | null;
};

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
    const createdAt = Date.parse(item.created_at);
    if (!Number.isFinite(createdAt) || createdAt > cutoff || item.read_at) {
      return item;
    }
    return { ...item, read_at: readAt };
  });
}
