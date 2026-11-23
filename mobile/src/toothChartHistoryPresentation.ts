import type { ToothStatusCode, ToothSurfaceCode } from "./api";

const SURFACE_LABELS: Readonly<Record<ToothSurfaceCode, string>> = Object.freeze({
  OCCLUSAL: "Oklüzal",
  INCISAL: "İnsizal",
  MESIAL: "Mesial",
  DISTAL: "Distal",
  BUCCAL: "Bukkal / Vestibül",
  LINGUAL: "Lingual / Palatinal",
});

const STATUS_LABELS: Readonly<Record<ToothStatusCode, string>> = Object.freeze({
  HEALTHY: "Sağlıklı",
  CARIES: "Çürük",
  FILLING: "Dolgu",
  CROWN: "Kron",
  ROOT_CANAL: "Kanal Tedavisi",
  EXTRACTED: "Çekilmiş",
  IMPLANT: "İmplant",
  OTHER: "Diğer",
});

/** Localize persisted FDI surface codes while preserving unknown future values. */
export function toothChartHistorySurfaceLabel(value: string): string {
  return SURFACE_LABELS[value as ToothSurfaceCode] ?? value;
}

/** Localize persisted clinical status codes without dropping forward-compatible values. */
export function toothChartHistoryStatusLabel(value: string): string {
  return STATUS_LABELS[value as ToothStatusCode] ?? value;
}
