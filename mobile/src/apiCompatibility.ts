/**
 * A bare FastAPI 404 ("Not Found") means the requested route is not mounted.
 * A resource-level 404 carries a specific detail and must remain a normal
 * not-found response instead of being misreported as a server-version gap.
 */
export const MISSING_API_ROUTE_MESSAGE =
  "Sunucuda istenen API rotası bulunamadı (404). Uygulama güncel olsa bile sunucu API sürümü geride olabilir; güvenli taslakları koruyun ve sunucu güncellenene kadar aynı işlemi yeni bir anahtarla göndermeyin.";

export function isMissingApiRoute404(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as { status?: unknown; message?: unknown };
  return value.status === 404 &&
    typeof value.message === "string" &&
    value.message.includes("istenen API rotası bulunamadı (404)");
}
