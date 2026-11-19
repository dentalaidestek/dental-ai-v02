import { ApiError } from "./api";
import {revalidateSession} from './sessionExpiry';
const BASE = "https://dentalai.tr";
export const socialUrl = (path: string) =>
  path.startsWith("/")
    ? BASE +
      path.replace(
        /^\/profile-photo\/(\d+)/,
        "/api/expert-social/experts/$1/photo",
      )
    : path;
// Never forward a session bearer token to an externally hosted image URL.
export function socialImageSource(path: string, token: string): {
  uri: string;
  headers?: { Authorization: string };
} {
  const uri = socialUrl(path);
  const firstParty =
    uri === BASE ||
    uri.startsWith(BASE + "/") ||
    uri.startsWith(BASE + "?");
  return firstParty
    ? { uri, headers: { Authorization: "Bearer " + token } }
    : { uri };
}
export type SocialModeration = {
  job_id: number | null;
  registered: boolean;
  content_version: number;
  revision: number;
  state: "WAITING_HUMAN" | "WAITING_OWNER" | "FAILED" | "RUNNING" | "AUTO_DONE" | "HUMAN_DONE";
  wait_type: string;
  reasons: string[];
  reason: string;
  created_at?: string;
  updated_at?: string;
  waiting_since?: string | null;
  age_seconds?: number;
  retryable: boolean;
  next_attempt_at?: string | null;
  last_decision?: {
    status: string;
    source: string;
    reason: string;
    at: string | null;
  };
};

export type SocialPost = {
  id: number;
  author_id: number;
  author_name: string;
  author_photo?: string;
  author_specialty?: string;
  author_followed?: boolean;
  author_support_available?: boolean;
  cover_media_id?: number | null;
  preview?: SocialLinkPreviewData | null;
  text: string;
  status: string;
  version: number;
  owned: boolean;
  pinned: boolean;
  comments_closed: boolean;
  liked: boolean;
  like_count: number;
  comment_count: number;
  link_url?: string;
  media: Array<{ id: number; url: string }>;
  created_at: string;
  moderation?: SocialModeration;
};
export type SocialModerationStatus = {
  target_type: "POST";
  target_id: number;
  status: "PUBLISHED" | "PENDING" | "REJECTED";
  version: number;
  moderation: SocialModeration;
};
export type SocialAdminStepUp = {
  token: string;
  expires_in: number;
  scope: "SOCIAL_MODERATION";
};
const SOCIAL_ADMIN_STEP_UP_TOKEN = /^[A-Za-z0-9_-]{43}$/;
export type SocialComment = {
  id: number;
  author_id: number;
  author_name: string;
  author_verified?: boolean;
  text: string;
  status: string;
  version: number;
  owned: boolean;
  liked: boolean;
  like_count: number;
  reply_count: number;
  parent_id: number | null;
};
export type SocialPage<T> = { items: T[]; next_cursor: number | null };
export type SocialFeedPage = SocialPage<SocialPost> & { specialties: string[] };
export type SocialLinkPreviewData = {
  url?: string;
  domain?: string;
  site_name?: string;
  title?: string;
  description?: string;
};
export type SocialLinkPreview = SocialLinkPreviewData & {
  available: boolean;
  id?: number;
  message?: string;
  cover?: { id: number; url: string } | null;
};
const SOCIAL_SPECIALTY_FALLBACK = [
  "Endodonti",
  "Ortodonti",
  "Pedodonti",
  "Periodontoloji",
  "Protetik Diş Tedavisi",
  "Restoratif Diş Tedavisi",
  "Ağız, Diş ve Çene Cerrahisi",
  "Ağız, Diş ve Çene Radyolojisi",
];
function normalizeSocialSpecialties(value: unknown): string[] {
  if (value === undefined) return [...SOCIAL_SPECIALTY_FALLBACK];
  if (
    !Array.isArray(value) ||
    value.length > 16 ||
    value.some(
      (item) =>
        typeof item !== "string" ||
        !item.trim() ||
        item !== item.trim() ||
        item.length > 80,
    ) ||
    new Set(value).size !== value.length
  ) {
    throw new ApiError(502, "Dental Akış branş listesi doğrulanamadı.");
  }
  return [...value] as string[];
}
export async function socialRequest<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),init.body instanceof FormData?90000:45000);
  const externalSignal=init.signal;
  const abort=()=>controller.abort();
  if(externalSignal?.aborted)controller.abort();
  else externalSignal?.addEventListener("abort",abort,{once:true});
  try {
  const response = await fetch(BASE + "/api/expert-social" + path, {
    ...init,
    signal:controller.signal,
    credentials: "omit",
    headers: {
      Authorization: "Bearer " + token,
      "X-Dental-Social": "1",
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  const raw = await response.text();
  let body: any;
  try {
    body = raw ? JSON.parse(raw) : {};
  } catch {
    // A gateway may return HTML for an expired session. Preserve the existing
    // session probe even when the response body is not JSON.
    if (response.status === 401) await revalidateSession(token);
    throw new ApiError(
      response.ok ? 502 : response.status,
      "Sunucu yanıtı okunamadı. Taslağınız korundu.",
    );
  }
  // An incorrect second-factor code is a 401 for the OTP, not for the
  // already-authenticated Bearer session. Avoid an unnecessary /me probe.
  if (
    response.status === 401 &&
    body?.code !== "SOCIAL_ADMIN_OTP_INVALID"
  ) {
    await revalidateSession(token);
  }
  if(response.ok&&(!raw.trim()||!body||typeof body!=="object"||Array.isArray(body)))throw new ApiError(502,"Dental Akış sunucusu geçersiz yanıt gönderdi. Tekrar deneyin.");
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof body.detail === "string"
        ? body.detail
        : "İşlem tamamlanamadı. Tekrar deneyin.",
    );
  return body as T;
  }catch(error){
    if(controller.signal.aborted&&!externalSignal?.aborted)throw new ApiError(408,"Dental Akış yanıt vermedi. Bağlantınızı kontrol edip tekrar deneyin.");
    if(error instanceof TypeError)throw new ApiError(503,"Dental Akış sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin.");
    throw error;
  }finally{clearTimeout(timeout);externalSignal?.removeEventListener("abort",abort)}
}
export function normalizeSocialFeedPost(value: unknown): SocialPost {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(502, "Dental Akış gönderi yanıtı doğrulanamadı.");
  }
  const post = value as Record<string, unknown>;
  const validId = (item: unknown) => Number.isSafeInteger(item) && (item as number) > 0;
  const validCount = (item: unknown) => Number.isSafeInteger(item) && (item as number) >= 0;
  if (
    !validId(post.id) ||
    !validId(post.author_id) ||
    typeof post.author_name !== "string" ||
    !post.author_name.trim() ||
    post.author_name.length > 160 ||
    typeof post.text !== "string" ||
    post.text.length > 5000 ||
    !["PUBLISHED", "PENDING", "REJECTED"].includes(String(post.status)) ||
    !validId(post.version) ||
    typeof post.owned !== "boolean" ||
    typeof post.pinned !== "boolean" ||
    typeof post.comments_closed !== "boolean" ||
    typeof post.liked !== "boolean" ||
    !validCount(post.like_count) ||
    !validCount(post.comment_count) ||
    !Array.isArray(post.media) ||
    post.media.length > 4 ||
    post.media.some((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return true;
      const media = item as Record<string, unknown>;
      return !validId(media.id) ||
        typeof media.url !== "string" ||
        media.url !== `/api/expert-social/media/${media.id}`;
    }) ||
    typeof post.created_at !== "string" ||
    !Number.isFinite(Date.parse(post.created_at)) ||
    (post.author_photo !== undefined && post.author_photo !== null && typeof post.author_photo !== "string") ||
    (post.author_specialty !== undefined && post.author_specialty !== null && typeof post.author_specialty !== "string") ||
    (post.author_followed !== undefined && typeof post.author_followed !== "boolean") ||
    (post.author_support_available !== undefined && typeof post.author_support_available !== "boolean") ||
    (post.link_url !== undefined && post.link_url !== null && typeof post.link_url !== "string") ||
    (post.cover_media_id !== undefined && post.cover_media_id !== null && !validId(post.cover_media_id))
  ) {
    throw new ApiError(502, "Dental Akış gönderi alanları doğrulanamadı.");
  }
  if (post.status !== "PUBLISHED" && post.owned !== true) {
    throw new ApiError(502, "Yayınlanmamış gönderinin sahibi doğrulanamadı.");
  }
  if (post.moderation !== undefined && post.moderation !== null) {
    const moderation = post.moderation as Record<string, unknown>;
    const states = ["WAITING_HUMAN", "WAITING_OWNER", "FAILED", "RUNNING", "AUTO_DONE", "HUMAN_DONE"];
    if (
      typeof moderation !== "object" ||
      Array.isArray(moderation) ||
      typeof moderation.reason !== "string" ||
      moderation.reason.length > 500 ||
      !Array.isArray(moderation.reasons) ||
      moderation.reasons.length > 12 ||
      moderation.reasons.some((reason) => typeof reason !== "string" || reason.length > 80) ||
      !states.includes(String(moderation.state)) ||
      typeof moderation.wait_type !== "string" ||
      typeof moderation.retryable !== "boolean" ||
      typeof moderation.registered !== "boolean" ||
      !validId(moderation.content_version) ||
      !validId(moderation.revision) ||
      (moderation.job_id !== null && moderation.job_id !== undefined && !validId(moderation.job_id))
    ) {
      throw new ApiError(502, "Dental Akış inceleme bilgisi doğrulanamadı.");
    }
  }
  return value as SocialPost;
}

export const getFeed = async (
  t: string,
  mode: "discover" | "following",
  before?: number,
  specialty = "",
): Promise<SocialFeedPage> => {
  if (
    typeof specialty !== "string" ||
    specialty !== specialty.trim() ||
    specialty.length > 80
  ) {
    throw new Error("Geçersiz branş filtresi.");
  }
  const params = ["limit=15", "details=true"];
  if (before) params.push("before=" + before);
  if (specialty) params.push("specialty=" + encodeURIComponent(specialty));
  const page = await socialRequest<
    SocialPage<SocialPost> & { specialties?: unknown }
  >(t, `/feed/${mode}?${params.join("&")}`);
  if (
    !page ||
    !Array.isArray(page.items) ||
    page.items.length > 15 ||
    (page.next_cursor !== null &&
      (!Number.isSafeInteger(page.next_cursor) || page.next_cursor < 1)) ||
    new Set(page.items.map((item) => (item as any)?.id)).size !== page.items.length
  ) {
    throw new ApiError(502, "Dental Akış sayfası doğrulanamadı.");
  }
  const specialties = normalizeSocialSpecialties(page.specialties);
  if (
    specialty &&
    page.specialties !== undefined &&
    !specialties.includes(specialty)
  ) {
    throw new ApiError(
      422,
      "Seçilen branş artık mevcut değil. Tümü filtresini seçin.",
    );
  }
  return { ...page, items: page.items.map(normalizeSocialFeedPost), specialties };
};
export async function getLinkPreview(
  token: string,
  url: string,
): Promise<SocialLinkPreview> {
  if (typeof url !== "string" || url !== url.trim() || url.length > 2048) {
    throw new Error("Geçerli bir HTTPS bağlantısı girin.");
  }
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("Geçerli bir HTTPS bağlantısı girin.");
  }
  if (parsed.protocol !== "https:" || !parsed.hostname) {
    throw new Error("Bağlantı önizlemesi yalnızca HTTPS adresleri için kullanılabilir.");
  }
  const result = await socialRequest<SocialLinkPreview>(token, "/preview", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  if (
    !result ||
    typeof result.available !== "boolean" ||
    typeof result.url !== "string"
  ) {
    throw new ApiError(502, "Bağlantı önizlemesi yanıtı doğrulanamadı.");
  }
  try {
    const resolved = new URL(result.url);
    if (resolved.protocol !== "https:" || !resolved.hostname) throw new Error();
  } catch {
    throw new ApiError(502, "Bağlantı önizlemesi güvenli bir adres döndürmedi.");
  }
  if (
    result.available &&
    (!Number.isSafeInteger(result.id) || (result.id as number) < 1)
  ) {
    throw new ApiError(502, "Bağlantı önizlemesi kimliği doğrulanamadı.");
  }
  if (
    result.cover !== undefined &&
    result.cover !== null &&
    (!Number.isSafeInteger(result.cover.id) ||
      result.cover.id < 1 ||
      typeof result.cover.url !== "string" ||
      result.cover.url !== `/api/expert-social/media/${result.cover.id}`
    )
  ) {
    throw new ApiError(502, "Bağlantı görseli doğrulanamadı.");
  }
  return result;
}

export function socialPostUrl(authorId: number, postId: number): string {
  if (
    !Number.isSafeInteger(authorId) ||
    authorId < 1 ||
    !Number.isSafeInteger(postId) ||
    postId < 1
  ) {
    throw new Error("Geçersiz gönderi bağlantısı.");
  }
  return `${BASE}/expert-support/expert/${authorId}?post=${postId}`;
}
export const getExpertPosts = (t: string, id: number, before?: number) =>
  socialRequest<SocialPage<SocialPost>>(
    t,
    `/experts/${id}/posts?limit=15${before ? "&before=" + before : ""}`,
  );

export async function getPost(t: string, id: number): Promise<SocialPost> {
  if (!Number.isSafeInteger(id) || id < 1) {
    throw new Error("Geçersiz gönderi kimliği.");
  }
  const value = await socialRequest<unknown>(t, `/posts/${id}`);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(502, "Gönderi yanıtı doğrulanamadı.");
  }
  const post = value as Record<string, unknown>;
  if (
    post.id !== id ||
    !Number.isSafeInteger(post.author_id) ||
    (post.author_id as number) < 1 ||
    typeof post.author_name !== "string" ||
    typeof post.text !== "string" ||
    !["PUBLISHED", "PENDING", "REJECTED"].includes(String(post.status)) ||
    !Number.isSafeInteger(post.version) ||
    (post.version as number) < 1 ||
    typeof post.owned !== "boolean" ||
    typeof post.pinned !== "boolean" ||
    typeof post.comments_closed !== "boolean" ||
    typeof post.liked !== "boolean" ||
    !Number.isSafeInteger(post.like_count) ||
    (post.like_count as number) < 0 ||
    !Number.isSafeInteger(post.comment_count) ||
    (post.comment_count as number) < 0 ||
    !Array.isArray(post.media) ||
    post.media.length > 4 ||
    post.media.some((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return true;
      const media = item as Record<string, unknown>;
      return (
        !Number.isSafeInteger(media.id) ||
        (media.id as number) < 1 ||
        typeof media.url !== "string" ||
        media.url !== `/api/expert-social/media/${media.id}`
      );
    }) ||
    typeof post.created_at !== "string"
  ) {
    throw new ApiError(502, "Gönderi alanları doğrulanamadı.");
  }
  if (post.status !== "PUBLISHED" && post.owned !== true) {
    throw new ApiError(502, "Yayınlanmamış gönderi sahibi doğrulanamadı.");
  }
  if (post.moderation !== undefined && post.moderation !== null) {
    const moderation = post.moderation as Record<string, unknown>;
    const states = ["WAITING_HUMAN", "WAITING_OWNER", "FAILED", "RUNNING", "AUTO_DONE", "HUMAN_DONE"];
    if (
      typeof moderation !== "object" ||
      Array.isArray(moderation) ||
      typeof moderation.registered !== "boolean" ||
      !states.includes(String(moderation.state)) ||
      typeof moderation.wait_type !== "string" ||
      typeof moderation.reason !== "string" ||
      moderation.reason.length > 1000 ||
      !Array.isArray(moderation.reasons) ||
      moderation.reasons.length > 12 ||
      moderation.reasons.some((reason) => typeof reason !== "string" || reason.length > 80) ||
      typeof moderation.retryable !== "boolean"
    ) {
      throw new ApiError(502, "Yayın inceleme durumu doğrulanamadı.");
    }
  }
  return post as unknown as SocialPost;
}
export async function getPostModerationStatus(
  t: string,
  id: number,
): Promise<SocialModerationStatus> {
  if (!Number.isSafeInteger(id) || id < 1) {
    throw new Error("Geçersiz gönderi kimliği.");
  }
  const value = await socialRequest<unknown>(
    t,
    `/moderation-status/POST/${id}`,
  );
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(502, "Yayın inceleme yanıtı doğrulanamadı.");
  }
  const result = value as Record<string, unknown>;
  const moderation = result.moderation as Record<string, unknown> | null;
  const states = [
    "WAITING_HUMAN",
    "WAITING_OWNER",
    "FAILED",
    "RUNNING",
    "AUTO_DONE",
    "HUMAN_DONE",
  ];
  if (
    result.target_type !== "POST" ||
    result.target_id !== id ||
    !["PUBLISHED", "PENDING", "REJECTED"].includes(String(result.status)) ||
    !Number.isSafeInteger(result.version) ||
    (result.version as number) < 1 ||
    !moderation ||
    typeof moderation !== "object" ||
    Array.isArray(moderation) ||
    typeof moderation.registered !== "boolean" ||
    !states.includes(String(moderation.state)) ||
    typeof moderation.wait_type !== "string" ||
    moderation.wait_type.length > 80 ||
    typeof moderation.reason !== "string" ||
    moderation.reason.length > 1000 ||
    !Array.isArray(moderation.reasons) ||
    moderation.reasons.length > 12 ||
    moderation.reasons.some(
      (reason) => typeof reason !== "string" || reason.length > 80,
    ) ||
    typeof moderation.retryable !== "boolean"
  ) {
    throw new ApiError(502, "Yayın inceleme alanları doğrulanamadı.");
  }
  return {
    target_type: "POST",
    target_id: id,
    status: result.status as SocialModerationStatus["status"],
    version: result.version as number,
    moderation: moderation as unknown as SocialModeration,
  };
}

export async function beginSocialAdminStepUp(token: string): Promise<{ expires_in: 600 }> {
  const value = await socialRequest<unknown>(token, "/admin/step-up", {
    method: "POST",
  });
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    (value as Record<string, unknown>).ok !== true ||
    (value as Record<string, unknown>).expires_in !== 600 ||
    (value as Record<string, unknown>).delivery !== "fixed_mailbox"
  ) {
    throw new ApiError(502, "Yönetici doğrulama isteği doğrulanamadı.");
  }
  return { expires_in: 600 };
}

export async function verifySocialAdminStepUp(
  token: string,
  code: string,
): Promise<SocialAdminStepUp> {
  if (typeof code !== "string" || !/^[0-9]{6}$/.test(code)) {
    throw new Error("Altı haneli yönetici doğrulama kodunu girin.");
  }
  const value = await socialRequest<unknown>(token, "/admin/step-up/verify", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(502, "Yönetici yetki yanıtı doğrulanamadı.");
  }
  const result = value as Record<string, unknown>;
  if (
    result.ok !== true ||
    typeof result.token !== "string" ||
    !SOCIAL_ADMIN_STEP_UP_TOKEN.test(result.token) ||
    result.expires_in !== 300 ||
    result.scope !== "SOCIAL_MODERATION"
  ) {
    throw new ApiError(502, "Yönetici yetki kapsamı doğrulanamadı.");
  }
  return { token: result.token, expires_in: 300, scope: "SOCIAL_MODERATION" };
}

export async function revokeSocialAdminStepUp(
  token: string,
  stepUpToken: string,
): Promise<void> {
  if (typeof stepUpToken !== "string" || !SOCIAL_ADMIN_STEP_UP_TOKEN.test(stepUpToken)) {
    throw new Error("Geçersiz yönetici yetki anahtarı.");
  }
  const value = await socialRequest<unknown>(token, "/admin/step-up/revoke", {
    method: "POST",
    headers: { "X-Dental-Social-Admin-Step-Up": stepUpToken },
  });
  if (!value || typeof value !== "object" || Array.isArray(value) || (value as Record<string, unknown>).ok !== true) {
    throw new ApiError(502, "Yönetici yetkisi kapatılamadı.");
  }
}

export type SocialAdminKind = "POST" | "COMMENT" | "PUBLICATION";
export type SocialAdminStatus = "PENDING" | "PUBLISHED" | "REJECTED";
export type SocialAdminQueueItem = Record<string, unknown> & {
  id: number;
  version: number;
  status: SocialAdminStatus;
};
export type SocialAdminQueuePage = {
  items: SocialAdminQueueItem[];
  next_cursor: string | number | null;
  aging?: Record<string, number>;
};
export type SocialAdminReport = Record<string, unknown> & {
  id: number;
  target_type: "POST" | "COMMENT";
  target_id: number;
  reason: string;
};
export type SocialAdminDetail = {
  item: Record<string, unknown>;
  history: Record<string, unknown>[];
  moderation_history: Record<string, unknown>[];
};

function socialAdminStepUpHeaders(stepUpToken: string): Record<string, string> {
  if (
    typeof stepUpToken !== "string" ||
    !SOCIAL_ADMIN_STEP_UP_TOKEN.test(stepUpToken)
  ) {
    throw new Error("Yönetici doğrulaması gerekiyor.");
  }
  return { "X-Dental-Social-Admin-Step-Up": stepUpToken };
}

function socialAdminRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

async function socialAdminRequest<T>(
  token: string,
  stepUpToken: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return socialRequest<T>(token, path, {
    ...init,
    headers: {
      ...init.headers,
      ...socialAdminStepUpHeaders(stepUpToken),
    },
  });
}

export async function getSocialAdminQueue(
  token: string,
  stepUpToken: string,
  kind: SocialAdminKind,
  status: SocialAdminStatus,
  before?: string | number | null,
): Promise<SocialAdminQueuePage> {
  if (!["POST", "COMMENT", "PUBLICATION"].includes(kind) ||
      !["PENDING", "PUBLISHED", "REJECTED"].includes(status)) {
    throw new Error("Geçersiz moderasyon filtresi.");
  }
  const params = new URLSearchParams({ kind, status });
  if (before !== undefined && before !== null) {
    const cursor = String(before);
    const validCursor = status === "PENDING"
      ? /^(?:[1-9][0-9]{0,18}|m1_[A-Za-z0-9_-]{1,180})$/.test(cursor)
      : /^[1-9][0-9]{0,18}$/.test(cursor);
    if (!validCursor || cursor.length > 192) {
      throw new Error("İnceleme sayfasını yeniden açın.");
    }
    params.set("before", cursor);
  }
  const value = await socialAdminRequest<unknown>(
    token,
    stepUpToken,
    "/moderation?" + params.toString(),
  );
  if (!socialAdminRecord(value) ||
      !Array.isArray(value.items) ||
      value.items.length > 30 ||
      !(value.next_cursor === null ||
        (typeof value.next_cursor === "number" && Number.isSafeInteger(value.next_cursor) && value.next_cursor > 0) ||
        (typeof value.next_cursor === "string" && status === "PENDING" && value.next_cursor.length <= 192 && /^m1_[A-Za-z0-9_-]+$/.test(value.next_cursor)))) {
    throw new ApiError(502, "Yönetici inceleme listesi doğrulanamadı.");
  }
  const items: SocialAdminQueueItem[] = [];
  for (const item of value.items) {
    if (!socialAdminRecord(item) ||
        !Number.isSafeInteger(item.id) || (item.id as number) < 1 ||
        !Number.isSafeInteger(item.version) || (item.version as number) < 1 ||
        item.status !== status) {
      throw new ApiError(502, "İnceleme kaydı doğrulanamadı.");
    }
    if (item.media !== undefined &&
        (!Array.isArray(item.media) || item.media.length > 4 ||
         item.media.some((media) => !socialAdminRecord(media) ||
           !Number.isSafeInteger(media.id) || (media.id as number) < 1 ||
           typeof media.url !== "string" || media.url.length > 2048))) {
      throw new ApiError(502, "İnceleme medyası doğrulanamadı.");
    }
    items.push(item as SocialAdminQueueItem);
  }
  let aging: Record<string, number> | undefined;
  if (value.aging !== undefined) {
    if (!socialAdminRecord(value.aging) ||
        Object.values(value.aging).some((n) => !Number.isSafeInteger(n) || (n as number) < 0)) {
      throw new ApiError(502, "İnceleme bekleme özeti doğrulanamadı.");
    }
    aging = value.aging as Record<string, number>;
  }
  return { items, next_cursor: value.next_cursor as string | number | null, aging };
}

export async function getSocialAdminReports(
  token: string,
  stepUpToken: string,
  before?: number | null,
): Promise<{ items: SocialAdminReport[]; next_cursor: number | null }> {
  if (before !== undefined && before !== null &&
      (!Number.isSafeInteger(before) || before < 1)) {
    throw new Error("Şikâyet sayfasını yeniden açın.");
  }
  const query = before ? "?before=" + before : "";
  const value = await socialAdminRequest<unknown>(
    token,
    stepUpToken,
    "/reports" + query,
  );
  if (!socialAdminRecord(value) || !Array.isArray(value.items) ||
      value.items.length > 30 ||
      !(value.next_cursor === null ||
        (Number.isSafeInteger(value.next_cursor) && (value.next_cursor as number) > 0))) {
    throw new ApiError(502, "Şikâyet listesi doğrulanamadı.");
  }
  const items: SocialAdminReport[] = [];
  for (const item of value.items) {
    if (!socialAdminRecord(item) ||
        !Number.isSafeInteger(item.id) || (item.id as number) < 1 ||
        !["POST", "COMMENT"].includes(String(item.target_type)) ||
        !Number.isSafeInteger(item.target_id) || (item.target_id as number) < 1 ||
        typeof item.reason !== "string" || item.reason.length > 80) {
      throw new ApiError(502, "Şikâyet kaydı doğrulanamadı.");
    }
    items.push(item as SocialAdminReport);
  }
  return { items, next_cursor: value.next_cursor as number | null };
}

export async function getSocialAdminDetail(
  token: string,
  stepUpToken: string,
  kind: SocialAdminKind,
  id: number,
): Promise<SocialAdminDetail> {
  if (!["POST", "COMMENT", "PUBLICATION"].includes(kind) ||
      !Number.isSafeInteger(id) || id < 1) {
    throw new Error("Geçersiz inceleme kaydı.");
  }
  const value = await socialAdminRequest<unknown>(
    token,
    stepUpToken,
    "/moderation/" + kind + "/" + id,
  );
  if (!socialAdminRecord(value) ||
      !socialAdminRecord(value.item) ||
      value.item.id !== id ||
      !Array.isArray(value.history) || value.history.length > 50 ||
      !Array.isArray(value.moderation_history) || value.moderation_history.length > 50 ||
      value.history.some((row) => !socialAdminRecord(row)) ||
      value.moderation_history.some((row) => !socialAdminRecord(row))) {
    throw new ApiError(502, "İnceleme ayrıntısı doğrulanamadı.");
  }
  return {
    item: value.item,
    history: value.history as Record<string, unknown>[],
    moderation_history: value.moderation_history as Record<string, unknown>[],
  };
}

export async function decideSocialAdminModeration(
  token: string,
  stepUpToken: string,
  kind: SocialAdminKind,
  id: number,
  status: SocialAdminStatus,
  version: number,
  reason: string,
): Promise<{ ok: true; status: SocialAdminStatus; version: number }> {
  if (!["POST", "COMMENT", "PUBLICATION"].includes(kind) ||
      !Number.isSafeInteger(id) || id < 1 ||
      !["PENDING", "PUBLISHED", "REJECTED"].includes(status) ||
      !Number.isSafeInteger(version) || version < 1 ||
      typeof reason !== "string" || reason.trim().length < 3 || reason.trim().length > 300) {
    throw new Error("Karar bilgilerini kontrol edin.");
  }
  const value = await socialAdminRequest<unknown>(
    token,
    stepUpToken,
    "/moderation/" + kind + "/" + id,
    {
      method: "POST",
      body: JSON.stringify({ status, version, reason: reason.trim() }),
    },
  );
  if (!socialAdminRecord(value) ||
      value.ok !== true ||
      value.status !== status ||
      !Number.isSafeInteger(value.version) || (value.version as number) <= version) {
    throw new ApiError(502, "Moderasyon kararı doğrulanamadı.");
  }
  return { ok: true, status, version: value.version as number };
}

export const getSocialStats = (t: string, id: number) =>
  socialRequest<{
    followers: number;
    following: number;
    posts: number;
    publications: number;
    following_by_viewer: boolean;
  }>(t, `/experts/${id}/stats`);
export const setFollow = (t: string, id: number, followed: boolean) =>
  socialRequest<{ following_by_viewer: boolean }>(t, `/experts/${id}/follow`, {
    method: "PUT",
    body: JSON.stringify({ followed }),
  });
export const setPostLike = (t: string, id: number, liked: boolean) =>
  socialRequest<{ liked: boolean; like_count: number }>(
    t,
    `/posts/${id}/like`,
    { method: "PUT", body: JSON.stringify({ liked }) },
  );
export const patchPost = (
  t: string,
  p: SocialPost,
  patch: { text?: string; pinned?: boolean; comments_closed?: boolean },
) =>
  socialRequest<SocialPost>(t, `/posts/${p.id}`, {
    method: "PATCH",
    body: JSON.stringify({ version: p.version, ...patch }),
  });
export const deletePost = (t: string, id: number) =>
  socialRequest(t, `/posts/${id}`, { method: "DELETE" });
export const createPost = (
  t: string,
  payload: {
    text: string;
    link_url?: string;
    preview_id?: number;
    media_ids: number[];
    idempotency_key: string;
    cover_media_id?: number;
  },
) => {
  if (
    payload.cover_media_id !== undefined &&
    (!Number.isSafeInteger(payload.cover_media_id) ||
      payload.cover_media_id < 1 ||
      !payload.media_ids.includes(payload.cover_media_id))
  ) {
    throw new Error("Bağlantı kapağı gönderi görsellerinden biri olmalı.");
  }
  return socialRequest<SocialPost>(t, "/posts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
};
export const uploadSocialImage = (
  t: string,
  file: { uri: string; name: string; type: string },
) => {
  const body = new FormData();
  body.append("file", file as any);
  return socialRequest<{ id: number }>(t, "/media", { method: "POST", body });
};
export const getComments = (
  t: string,
  id: number,
  after = 0,
  parent?: number,
) =>
  socialRequest<SocialPage<SocialComment>>(
    t,
    `/posts/${id}/comments?threaded=true&limit=30&after=${after}${parent ? "&parent_id=" + parent : ""}`,
  );
export const createComment = (
  t: string,
  id: number,
  text: string,
  key: string,
  parent_id?: number,
) =>
  socialRequest<SocialComment>(t, `/posts/${id}/comments`, {
    method: "POST",
    body: JSON.stringify({
      text,
      idempotency_key: key,
      ...(parent_id ? { parent_id } : {}),
    }),
  });
export const setCommentLike = (t: string, id: number, liked: boolean) =>
  socialRequest<{ liked: boolean; like_count: number }>(
    t,
    `/comments/${id}/like`,
    { method: "PUT", body: JSON.stringify({ liked }) },
  );
export const patchComment = (t: string, c: SocialComment, text: string) =>
  socialRequest<SocialComment>(t, `/comments/${c.id}`, {
    method: "PATCH",
    body: JSON.stringify({ text, version: c.version }),
  });
export const deleteComment = (t: string, id: number) =>
  socialRequest(t, `/comments/${id}`, { method: "DELETE" });
export const reportSocial = (
  t: string,
  target_type: "POST" | "COMMENT",
  target_id: number,
  reason = "OTHER",
) =>
  socialRequest(t, "/reports", {
    method: "POST",
    body: JSON.stringify({ target_type, target_id, reason }),
  });

export type SocialRelationship={id:number;user_id:number;name:string;photo:string|null;is_expert:boolean;specialty:string|null;following_by_viewer:boolean};
export async function getSocialRelationships(token:string,ownerId:number,kind:'followers'|'following',before?:number){
 if(!Number.isSafeInteger(ownerId)||ownerId<1||!['followers','following'].includes(kind)||before!==undefined&&(!Number.isSafeInteger(before)||before<1))throw Error('Geçersiz takip listesi.');
 const r=await socialRequest<{items:SocialRelationship[];next_cursor:number|null}>(token,`/experts/${ownerId}/${kind}?limit=15`+(before?'&before='+before:''));
 if(!Array.isArray(r.items)||r.items.length>15||r.items.some(m=>!m||!Number.isSafeInteger(m.user_id)||m.user_id<1||typeof m.name!=='string'||typeof m.is_expert!=='boolean'||typeof m.following_by_viewer!=='boolean'||before!==undefined&&m.user_id>=before)||new Set(r.items.map(m=>m.user_id)).size!==r.items.length||r.next_cursor!==null&&(!Number.isSafeInteger(r.next_cursor)||r.next_cursor<1||!r.items.some(m=>m.user_id===r.next_cursor)||before!==undefined&&r.next_cursor>=before))throw Error('Takip listesi yanıtı doğrulanamadı. Yeniden deneyin.');
 return{items:r.items.map(m=>({...m,id:m.user_id})),next_before:r.next_cursor};
}
