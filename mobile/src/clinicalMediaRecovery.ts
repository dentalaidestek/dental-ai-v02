/** Classify native clinical-media upload failures without guessing whether a write committed. */
export type ClinicalMediaUploadFailure = "LOCAL" | "CONFIGURATION" | "REJECTED" | "UNCERTAIN";

const LOCAL_CODES = new Set([
  "SOURCE_MISSING", "VAULT_MISSING", "KEY_MISSING", "KEY_INVALID",
  "AUTH_FAILED", "INVALID_VAULT",
]);

export function classifyClinicalMediaUploadFailure(
  status?: number,
  code?: string,
): ClinicalMediaUploadFailure {
  if (typeof code === "string" && LOCAL_CODES.has(code)) return "LOCAL";
  // The mobile upload route returns 503 for a missing receipt key before it
  // reads/persists the uploaded file. This is a known non-commit, not ambiguity.
  if (status === 503) return "CONFIGURATION";
  if (typeof status === "number" && [400, 403, 404, 413, 422].includes(status)) {
    return "REJECTED";
  }
  return "UNCERTAIN";
}
