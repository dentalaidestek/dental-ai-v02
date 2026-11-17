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
  // Session invalidation must run even when a gateway returns HTML for 401.
  if(response.status===401)await revalidateSession(token);
  const raw = await response.text();
  let body: any;
  try {
    body = raw ? JSON.parse(raw) : {};
  } catch {
    throw new ApiError(
      response.ok ? 502 : response.status,
      "Sunucu yanıtı okunamadı. Taslağınız korundu.",
    );
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
  return { ...page, specialties };
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
    !Array.isArray(post.media) ||
    typeof post.created_at !== "string"
  ) {
    throw new ApiError(502, "Gönderi alanları doğrulanamadı.");
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
