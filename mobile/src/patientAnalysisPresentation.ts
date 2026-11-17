export type PatientAnalysisAssetSummary = {
  id: number;
  image_type: string;
};

export type PatientAnalysisAssetGroups = {
  clinical: PatientAnalysisAssetSummary[];
  radiographs: PatientAnalysisAssetSummary[];
};

/**
 * Mirrors patient_detail.html: every non-RADIOGRAPH asset belongs to the
 * clinical-image group; RADIOGRAPH assets are rendered separately.
 */
export function groupPatientAnalysisAssets(
  assets: readonly PatientAnalysisAssetSummary[] | null | undefined,
): PatientAnalysisAssetGroups {
  const rows = assets ? Array.from(assets) : [];
  return {
    clinical: rows.filter(asset => asset.image_type !== "RADIOGRAPH"),
    radiographs: rows.filter(asset => asset.image_type === "RADIOGRAPH"),
  };
}

/**
 * The web profile uses Analysis.radiograph_path only when no ImageAsset
 * marked RADIOGRAPH exists. Keep that fallback explicit and fail closed.
 */
export function shouldShowLegacyPatientRadiograph(
  available: boolean | undefined,
  assets: readonly PatientAnalysisAssetSummary[] | null | undefined,
): boolean {
  return available === true && groupPatientAnalysisAssets(assets).radiographs.length === 0;
}
