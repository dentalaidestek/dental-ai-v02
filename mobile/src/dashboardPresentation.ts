export type DashboardProgramEvent = {
  id: number;
  title: string;
  start_time: string;
  type_label: string;
  patient_name: string;
};

export type DashboardProgramSnapshot = {
  label: "Bugün" | "Yaklaşan Program";
  event: DashboardProgramEvent | null;
};

const PROGRAM_EVENT_TYPES = new Set([
  "PROGRAM_CREATED",
  "PROGRAM_UPDATED",
  "PROGRAM_COMPLETED",
  "PROGRAM_DELETED",
]);

const PROGRAM_EVENT_FIELDS = new Set([
  "id",
  "title",
  "start_time",
  "type_label",
  "patient_name",
]);

export function dashboardGreetingForHour(hour: number): string {
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) return "Merhaba";
  if (hour >= 5 && hour < 12) return "Günaydın";
  if (hour >= 18 || hour < 5) return "İyi akşamlar";
  return "Merhaba";
}

/** Mirrors the professional-name prefix used by the web dashboard. */
export function dashboardProfessionalName(
  title: string | null | undefined,
  name: string | null | undefined,
): string {
  const cleanName = typeof name === "string" ? name.trim() : "";
  if (!cleanName) return "Dental AI";

  const prefixes: Record<string, string> = {
    "Diş Hekimi": "Dt.",
    "Uzman Diş Hekimi": "Uzm. Dt.",
    "Asistan / Araştırma Görevlisi": "Arş. Gör. Dt.",
    "Dr. Öğr. Üyesi": "Dr. Öğr. Üyesi",
    "Doç. Dr.": "Doç. Dr.",
    "Prof. Dr.": "Prof. Dr.",
  };
  const prefix = typeof title === "string" ? prefixes[title.trim()] : undefined;
  if (!prefix) return cleanName;

  const normalizedName = cleanName.toLocaleLowerCase("tr-TR");
  const normalizedPrefix = prefix.toLocaleLowerCase("tr-TR");
  return normalizedName.startsWith(normalizedPrefix + " ")
    ? cleanName
    : prefix + " " + cleanName;
}

export function isDashboardProgramEvent(
  value: unknown,
): value is DashboardProgramEvent {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return Object.keys(item).every((key) => PROGRAM_EVENT_FIELDS.has(key)) &&
    Number.isSafeInteger(item.id) && Number(item.id) > 0 &&
    typeof item.title === "string" && item.title.trim().length > 0 && item.title.length <= 200 &&
    typeof item.start_time === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(item.start_time) &&
    typeof item.type_label === "string" && item.type_label.length <= 80 &&
    typeof item.patient_name === "string" && item.patient_name.length <= 256;
}

/** Accept only the compact, versioned snapshot emitted by the web dashboard. */
export function parseDashboardProgramSnapshot(
  value: unknown,
): DashboardProgramSnapshot | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const event = value as Record<string, unknown>;
  const eventType = typeof event.event_type === "string"
    ? event.event_type
    : typeof event.type === "string" ? event.type : "";
  if (!PROGRAM_EVENT_TYPES.has(eventType)) return null;

  const payload = event.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const snapshot = payload as Record<string, unknown>;
  if (snapshot.payload_version !== 1) return null;

  const label = snapshot.dashboard_event_label;
  if (label !== "Bugün" && label !== "Yaklaşan Program") return null;

  const dashboardEvent = snapshot.dashboard_event;
  if (dashboardEvent === null) return { label, event: null };
  if (!isDashboardProgramEvent(dashboardEvent)) return null;
  return { label, event: dashboardEvent };
}

export function applyDashboardProgramSnapshot<
  T extends {
    dashboard_event?: DashboardProgramEvent | null;
    dashboard_event_label?: string;
  },
>(current: T, snapshot: DashboardProgramSnapshot): T {
  return {
    ...current,
    dashboard_event: snapshot.event,
    dashboard_event_label: snapshot.label,
  };
}
