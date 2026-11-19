export type ToothSurfaceOptionCode =
  | "OCCLUSAL"
  | "INCISAL"
  | "MESIAL"
  | "DISTAL"
  | "BUCCAL"
  | "LINGUAL";

export type ToothSurfaceOption = readonly [ToothSurfaceOptionCode, string];

const COMMON_SURFACES = [
  ["MESIAL", "Mesial"],
  ["DISTAL", "Distal"],
  ["BUCCAL", "Bukkal / Vestibül"],
  ["LINGUAL", "Lingual / Palatinal"],
] as const satisfies readonly ToothSurfaceOption[];

const ANTERIOR_SURFACES: readonly ToothSurfaceOption[] = [
  ["INCISAL", "İnsizal"],
  ...COMMON_SURFACES,
];

const POSTERIOR_SURFACES: readonly ToothSurfaceOption[] = [
  ["OCCLUSAL", "Oklüzal"],
  ...COMMON_SURFACES,
];

/** Return only anatomically applicable FDI surfaces for a permanent or primary tooth. */
export function toothSurfaceOptionsForTooth(toothNumber: string): readonly ToothSurfaceOption[] {
  if (typeof toothNumber !== "string" || !/^(?:[1-4][1-8]|[5-8][1-5])$/.test(toothNumber)) {
    return [];
  }
  const unit = Number(toothNumber[1]);
  return unit <= 3 ? ANTERIOR_SURFACES : POSTERIOR_SURFACES;
}
