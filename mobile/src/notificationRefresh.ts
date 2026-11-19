const HOME_NOTIFICATION_EVENTS = new Set([
  "NOTICE_CREATED",
  "NOTICE_RESOLVED",
  "NOTIFICATIONS_READ",
]);

/**
 * The home badge represents AdminNotice rows only. Match the web sync handler:
 * patient, analysis, program and chat events must not trigger a notice-count read.
 */
export function shouldRefreshHomeUnread(event: unknown): boolean {
  if (!event || typeof event !== "object") return false;
  const value = event as { event_type?: unknown; type?: unknown };
  const eventType =
    typeof value.event_type === "string" && value.event_type.trim()
      ? value.event_type
      : value.type;
  return typeof eventType === "string" && HOME_NOTIFICATION_EVENTS.has(eventType.trim().toUpperCase());
}
