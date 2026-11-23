export type ToothChartConflictSnapshot = Readonly<{
  kind: "tooth" | "surface";
  toothNumber: string;
  surface?: string;
  refreshed: boolean;
  latestStatus?: string | null;
  latestNote?: string | null;
}>;

const STATUS_LABELS: Record<string, string> = {
  HEALTHY: "Sağlıklı",
  CARIES: "Çürük",
  FILLING: "Dolgu",
  CROWN: "Kron",
  ROOT_CANAL: "Kanal",
  EXTRACTED: "Çekilmiş",
  IMPLANT: "İmplant",
  OTHER: "Diğer",
};

const SURFACE_LABELS: Record<string, string> = {
  OCCLUSAL: "Oklüzal",
  INCISAL: "İnsizal",
  MESIAL: "Mesial",
  DISTAL: "Distal",
  BUCCAL: "Bukkal / Vestibül",
  LINGUAL: "Lingual / Palatinal",
};

export function toothChartConflictTitle(conflict: ToothChartConflictSnapshot): string {
  if (conflict.kind === "surface") {
    const surface = conflict.surface ? SURFACE_LABELS[conflict.surface] || "Yüzey" : "Yüzey";
    return `Diş ${conflict.toothNumber} · ${surface}`;
  }
  return `Diş ${conflict.toothNumber}`;
}

/** Describe the other session's current snapshot without changing the clinician's local draft. */
export function toothChartConflictMessage(conflict: ToothChartConflictSnapshot): string {
  if (!conflict.refreshed) {
    return "Bu kayıt başka bir oturumda değiştirildi. Eski sürümle tekrar kaydetme kapalı; önce güncel kaydı yükleyin.";
  }
  const status = conflict.latestStatus
    ? STATUS_LABELS[conflict.latestStatus] || "Durum bilinmiyor"
    : "Kayıtlı durum yok";
  const note = typeof conflict.latestNote === "string" && conflict.latestNote.trim()
    ? `Not: ${conflict.latestNote.trim()}`
    : "Not yok";
  return `Sunucudaki son durum: ${status}. ${note}. Formdaki taslağınız korunuyor; karşılaştırdıktan sonra yeniden kaydedebilirsiniz.`;
}
