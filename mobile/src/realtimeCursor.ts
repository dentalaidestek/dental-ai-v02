// Commit order can differ from event allocation order. Deduplicate observed IDs,
// never discard an unseen event merely because its ID is below the cursor.
export class RealtimeCursor {
  current = 0;
  private seen = new Set<number>();
  constructor(saved: unknown = 0) {
    const n = Number(saved);
    if (Number.isSafeInteger(n) && n >= 0) this.current = n;
  }
  resumeAfter() { return Math.max(0, this.current - 500); }
  accept(event: {event_id?: unknown; id?: unknown}): boolean {
    const id = event.event_id ?? event.id;
    if (typeof id !== 'number' || !Number.isSafeInteger(id) || id <= 0) return false;
    if (this.seen.has(id)) return false;
    this.seen.add(id);
    if (this.seen.size > 2000) this.seen.delete(this.seen.values().next().value!);
    this.current = Math.max(this.current, id);
    return true;
  }
}
