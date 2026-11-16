/** Stable server-enforced grouping for sequential native clinical-media uploads. */
export const CLINICAL_MEDIA_BATCH_ID_PATTERN = /^[A-Za-z0-9_-]{16,96}$/;

/**
 * Keep a valid persisted batch ID across retries. Older encrypted drafts have
 * no batch ID; they receive one once and the caller persists it before upload.
 */
export function ensureClinicalMediaBatchId(
  value: unknown,
  create: () => string,
): string {
  if (value !== undefined && value !== null && value !== "") {
    if (typeof value !== "string" || !CLINICAL_MEDIA_BATCH_ID_PATTERN.test(value)) {
      throw new Error("Klinik görüntü yükleme grubu doğrulanamadı.");
    }
    return value;
  }

  const generated = create();
  if (typeof generated !== "string" || !CLINICAL_MEDIA_BATCH_ID_PATTERN.test(generated)) {
    throw new Error("Güvenli klinik görüntü yükleme grubu oluşturulamadı.");
  }
  return generated;
}
