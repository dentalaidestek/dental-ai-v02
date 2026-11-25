// Foto Fikir mobil istemcisi: /api/foto-fikir uçları /api/mobile/v1 dışında
// olduğundan socialApi.ts'teki kendi istek yardımcısı deseni izlenir.
import { ApiError } from "./api";
import { revalidateSession } from './sessionExpiry';

const FF_SITE = "https://dentalai.tr";
const FF_BASE = FF_SITE + "/api/foto-fikir";

export type FFStyle = { id: string; name: string; hint: string };
export type FFIdea = { title: string; angle: string; hook: string };
export type FFSlide = { headline: string; body: string; note?: string | null; role?: string | null };
export type FFStyleRecommendation = { style_id: string; reason: string };
export type FFCreativeAudit = { score: number; level?: string };
export type FFMevzuatResult = { index: number; text: string; level: string; reason: string; suggestion: string; creative_alternative?: string };
export type FFJob = { id: number; kind: string; label: string; topic: string; created_at: string; image_url?: string | null; status: string };
export type FFQuota = { used: number; limit: number; period: string };
export type FFBootstrap = {
  profile: { display_name: string; unvan?: string | null; specialty?: string | null };
  styles: FFStyle[];
  quota: FFQuota;
  brand_kit: { exists: boolean; photos_count: number; photos: string[] };
  recent: FFJob[];
  mock?: boolean;
  uyari?: string;
};
export type FFIdeasResult = { ideas: FFIdea[]; creative_audit?: unknown; tips?: string[]; mock?: boolean; uyari?: string };
export type FFSlidesResult = { slides: FFSlide[]; mock?: boolean; uyari?: string };
export type FFMevzuatCheckResult = { results: FFMevzuatResult[]; disclaimer: string };
export type FFGenerateResult = { job_id: string; image_url?: string | null; images: string[]; style: string; quota: FFQuota; style_recommendation?: FFStyleRecommendation; suggestion?: FFStyleRecommendation; tips?: string[]; uretim_ms?: number; skipped?: number; uyari?: string; mock?: boolean; creative_audit?: FFCreativeAudit };
export type FFBrandKitResult = { exists: boolean; photos_count: number; photos: string[]; saved: number; mock?: boolean; uyari?: string };
export type FFBrandGenerateResult = { job_id: string; image_url: string; scene: string; reason: string; uretim_ms?: number; quota: FFQuota; mock?: boolean; uyari?: string };
export type FFIgProfile = { bio: string; highlights: string[]; grid_plan: Array<{ idea: string; format: string }>; mock?: boolean; uyari?: string };
export type FFReelsShot = { plan?: string; kamera?: string; hareket?: string; isik?: string; overlay?: string; ses_ritim?: string };
export type FFReelsPlan = { hooks: string[]; senaryo: Array<{ aralik: string; metin: string; shot?: FFReelsShot }>; capcut_adimlari: string[]; tips?: string[]; mock?: boolean; uyari?: string };
export type FFHistory = { jobs: FFJob[] };

const ffCount = (v: unknown) => Number.isSafeInteger(v) && (v as number) >= 0;
async function ffRequest<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  // Görsel üretimi ve marka sahne üretimi dakikalar sürebilir; yükleme kısa sınırda kalır.
  const deadlineMs = /\/generate-image$|\/brand-kit\/generate$/.test(path) ? 600000
    : /\/brand-kit$/.test(path) ? 120000 : 30000;
  const timeout = setTimeout(() => controller.abort(), deadlineMs);
  const externalSignal = init.signal;
  const abort = () => controller.abort();
  if (externalSignal?.aborted) controller.abort();
  else externalSignal?.addEventListener("abort", abort, { once: true });
  try {
    const response = await fetch(FF_BASE + path, {
      ...init,
      signal: controller.signal,
      credentials: "omit",
      headers: {
        Authorization: "Bearer " + token,
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
      },
    });
    const raw = await response.text();
    let body: any;
    try { body = raw ? JSON.parse(raw) : {}; } catch {
      if (response.status === 401) await revalidateSession(token);
      throw new ApiError(response.ok ? 502 : response.status, "Sunucu yanıtı okunamadı. Tekrar deneyin.");
    }
    if (response.status === 401) await revalidateSession(token);
    if (response.ok && (!raw.trim() || !body || typeof body !== "object" || Array.isArray(body)))
      throw new ApiError(502, "Foto Fikir sunucusu geçersiz yanıt gönderdi. Tekrar deneyin.");
    if (!response.ok)
      throw new ApiError(response.status, typeof body?.detail === "string" ? body.detail : "İşlem tamamlanamadı. Tekrar deneyin.");
    return body as T;
  } catch (error) {
    if (controller.signal.aborted && !externalSignal?.aborted)
      throw new ApiError(408, "Foto Fikir yanıt vermedi. Bağlantınızı kontrol edip tekrar deneyin.");
    if (error instanceof TypeError) throw new ApiError(503, "Foto Fikir sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin.");
    throw error;
  } finally {
    clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abort);
  }
}

// Görsel adresi yalnızca birinci taraf /uploads/foto_fikir/ yollarında yetkili
// başlıkla açılır; başka hiçbir adrese oturum belirteci gönderilmez.
export function ffImageSource(token: string, path: string): { uri: string; headers?: { Authorization: string } } {
  if (typeof path !== "string" || !path.startsWith("/uploads/foto_fikir/")) return { uri: path };
  return { uri: FF_SITE + path, headers: { Authorization: "Bearer " + token } };
}

export const getFFBootstrap = async (t: string): Promise<FFBootstrap> => {
  const r = await ffRequest<FFBootstrap>(t, "");
  if (!r?.profile || typeof r.profile.display_name !== "string" ||
    !Array.isArray(r.styles) || r.styles.some(s => !s || typeof s.id !== "string" || typeof s.name !== "string") ||
    !r.quota || !ffCount(r.quota.used) || !ffCount(r.quota.limit) ||
    !r.brand_kit || !Array.isArray(r.brand_kit.photos) || !Array.isArray(r.recent))
    throw new ApiError(502, "Foto Fikir açılış bilgileri doğrulanamadı.");
  return r;
};
export const suggestFFIdeas = (t: string, topicHint: string) => {
  const topic = String(topicHint ?? "").trim();
  if (topic.length > 200) throw new ApiError(400, "Konu ipucu en fazla 200 karakter olabilir.");
  return ffRequest<FFIdeasResult>(t, "/ideas", { method: "POST", body: JSON.stringify({ topic_hint: topic }) });
};
export const prepareFFSlides = (t: string, topic: string, slideCount = 5, tone = "bilgilendirici") => {
  const cleanTopic = String(topic ?? "").trim(), cleanTone = String(tone ?? "").trim();
  if (cleanTopic.length > 200 || cleanTone.length > 40) throw new ApiError(400, "Konu veya ton çok uzun.");
  if (!Number.isSafeInteger(slideCount) || slideCount < 3 || slideCount > 8)
    throw new ApiError(400, "Slayt sayısı 3 ile 8 arasında olmalı.");
  return ffRequest<FFSlidesResult>(t, "/slides", { method: "POST", body: JSON.stringify({ topic: cleanTopic, slide_count: slideCount, tone: cleanTone || "bilgilendirici" }) });
};
export const checkFFMevzuat = (t: string, texts: string[]) => {
  const clean = (Array.isArray(texts) ? texts : []).map(v => String(v ?? "").trim()).filter(Boolean);
  if (!clean.length || clean.length > 12) throw new ApiError(400, "Mevzuat kontrolü için 1 ile 12 arası metin gönderin.");
  if (clean.some(v => v.length > 300)) throw new ApiError(400, "Kontrol metinleri en fazla 300 karakter olabilir.");
  return ffRequest<FFMevzuatCheckResult>(t, "/mevzuat-check", { method: "POST", body: JSON.stringify({ texts: clean }) });
};
export const generateFFImages = async (t: string, payload: { topic: string; styleId: string; slides: FFSlide[]; includeName: boolean }) => {
  const topic = String(payload?.topic ?? "").trim();
  const slides = (Array.isArray(payload?.slides) ? payload.slides : [])
    .map(s => ({ headline: String(s?.headline ?? "").trim().slice(0, 120), body: String(s?.body ?? "").trim().slice(0, 220) }))
    .filter(s => s.headline || s.body);
  if (!topic && !slides.length) throw new ApiError(400, "Konu ve en az bir slayt metni gerekli.");
  if (slides.length > 8) throw new ApiError(400, "En fazla 8 slayt gönderilebilir.");
  if (String(payload?.styleId ?? "").length > 60) throw new ApiError(400, "Geçerli bir görsel stili seçin.");
  const r = await ffRequest<FFGenerateResult>(t, "/generate-image", {
    method: "POST",
    body: JSON.stringify({ topic, style_id: String(payload?.styleId ?? ""), slides, include_name: payload?.includeName === true }),
  });
  if (!Array.isArray(r?.images) || !r.job_id || !r.quota || !ffCount(r.quota.used) || !ffCount(r.quota.limit))
    throw new ApiError(502, "Görsel üretim yanıtı doğrulanamadı.");
  return r;
};
export const uploadFFBrandKit = (t: string, files: Array<{ uri: string; name: string; type: string }>) => {
  if (!Array.isArray(files) || !files.length || files.length > 3) throw new ApiError(400, "En fazla 3 fotoğraf yükleyin.");
  if (files.some(f => !f?.uri || !/^image\/(png|jpeg)$/.test(String(f.type || ""))))
    throw new ApiError(400, "Yalnızca PNG veya JPEG fotoğraf yükleyin.");
  const body = new FormData();
  for (const file of files) body.append("files", file as any);
  return ffRequest<FFBrandKitResult>(t, "/brand-kit", { method: "POST", body });
};
export const generateFFBrandScene = (t: string, scene: string) => {
  const clean = String(scene ?? "").trim();
  if (!clean || clean.length > 80) throw new ApiError(400, "Geçerli bir sahne seçin.");
  return ffRequest<FFBrandGenerateResult>(t, "/brand-kit/generate", { method: "POST", body: JSON.stringify({ scene: clean }) });
};
export const getFFIgProfile = (t: string) =>
  ffRequest<FFIgProfile>(t, "/ig-profile", { method: "POST", body: JSON.stringify({}) });
export const getFFReelsPlan = (t: string, topic: string) => {
  const clean = String(topic ?? "").trim();
  if (!clean || clean.length > 200) throw new ApiError(400, "Reels konusu gerekli.");
  return ffRequest<FFReelsPlan>(t, "/reels", { method: "POST", body: JSON.stringify({ topic: clean }) });
};
export const getFFHistory = async (t: string): Promise<FFHistory> => {
  const r = await ffRequest<FFHistory>(t, "/history");
  if (!r || !Array.isArray(r.jobs)) throw new ApiError(502, "Son işlemler listesi doğrulanamadı.");
  return r;
};
