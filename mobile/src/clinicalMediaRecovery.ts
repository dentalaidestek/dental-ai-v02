/** Classify native clinical-media upload failures without guessing whether a write committed. */
export type ClinicalMediaUploadFailure = "LOCAL" | "CONFIGURATION" | "REJECTED" | "UNCERTAIN";

const LOCAL_CODES = new Set([
  "SOURCE_MISSING", "VAULT_MISSING", "KEY_MISSING", "KEY_INVALID",
  "AUTH_FAILED", "INVALID_VAULT",
]);

export function classifyClinicalMediaUploadFailure(
  status?: number,
  code?: string,
  missingRoute = false,
): ClinicalMediaUploadFailure {
  if (typeof code === "string" && LOCAL_CODES.has(code)) return "LOCAL";
  // The receipt-key 503 and a bare 404 for the receipt route both stop the
  // upload before a file POST can be accepted. A patient-specific 404 remains
  // a normal ownership/resource rejection.
  if (status === 503 || (status === 404 && missingRoute)) return "CONFIGURATION";
  if (typeof status === "number" && [400, 403, 404, 413, 422].includes(status)) {
    return "REJECTED";
  }
  return "UNCERTAIN";
}
