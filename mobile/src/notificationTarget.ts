export type NativeNotificationRoute =
  | { screen: "ConsultationChat"; params: { id: number } }
  | { screen: "Consultations" }
  | { screen: "Patients"; params: { screen: "PatientDetail"; params: { id: number } } }
  | { screen: "Program" }
  | { screen: "ExpertDirectory" }
  | { screen: "ExpertManagement" };

export type NativeNotificationTarget =
  | { kind: "none" }
  | { kind: "unsupported"; path: string }
  | { kind: "navigate"; route: NativeNotificationRoute };

function positiveId(raw: string): number | null {
  if (!/^\d{1,15}$/.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

/** Resolve only known, same-origin web notification paths to real native screens. */
export function resolveNativeNotificationTarget(value: unknown): NativeNotificationTarget {
  if (value == null || value === "") return { kind: "none" };
  if (typeof value !== "string") return { kind: "unsupported", path: "" };
  const raw = value.trim();
  if (!raw) return { kind: "none" };
  if (!raw.startsWith("/") || raw.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(raw)) {
    return { kind: "unsupported", path: "" };
  }
  const separator = raw.search(/[?#]/);
  const path = (separator < 0 ? raw : raw.slice(0, separator)).replace(/\/+$/, "") || "/";

  const caseMatch = path.match(/^\/(?:expert-support\/cases|expert\/consultations|consultations|cases)\/(\d+)(?:\/messages)?$/);
  if (caseMatch) {
    const id = positiveId(caseMatch[1]);
    return id ? { kind: "navigate", route: { screen: "ConsultationChat", params: { id } } } : { kind: "unsupported", path };
  }
  const patientMatch = path.match(/^\/patients\/(\d+)(?:\/.*)?$/);
  if (patientMatch) {
    const id = positiveId(patientMatch[1]);
    return id ? { kind: "navigate", route: { screen: "Patients", params: { screen: "PatientDetail", params: { id } } } } : { kind: "unsupported", path };
  }
  if (path === "/consultations" || path === "/expert/consultations") {
    return { kind: "navigate", route: { screen: "Consultations" } };
  }
  if (path === "/expert-support/profile") {
    return { kind: "navigate", route: { screen: "ExpertManagement" } };
  }
  if (path === "/expert-support") {
    return { kind: "navigate", route: { screen: "ExpertDirectory" } };
  }
  if (path === "/program") {
    return { kind: "navigate", route: { screen: "Program" } };
  }
  return { kind: "unsupported", path };
}
