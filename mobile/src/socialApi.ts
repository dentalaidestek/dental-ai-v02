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
export type SocialPost = {
  id: number;
  author_id: number;
  author_name: string;
  author_photo?: string;
  author_specialty?: string;
  author_followed?: boolean;
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
    throw new ApiError(
      response.status || 502,
      "Sunucu yanıtı okunamadı. Taslağınız korundu.",
    );
  }
  if(response.status===401)await revalidateSession(token);
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof body.detail === "string"
        ? body.detail
        : "İşlem tamamlanamadı. Tekrar deneyin.",
    );
  return body as T;
  }finally{clearTimeout(timeout);externalSignal?.removeEventListener("abort",abort)}
}
export const getFeed = (
  t: string,
  mode: "discover" | "following",
  before?: number,
) =>
  socialRequest<SocialPage<SocialPost>>(
    t,
    `/feed/${mode}?limit=15&details=true${before ? "&before=" + before : ""}`,
  );
export const getExpertPosts = (t: string, id: number, before?: number) =>
  socialRequest<SocialPage<SocialPost>>(
    t,
    `/experts/${id}/posts?limit=15${before ? "&before=" + before : ""}`,
  );
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
  },
) =>
  socialRequest<SocialPost>(t, "/posts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
