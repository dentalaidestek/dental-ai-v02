type Listener={token:string;notify:()=>void;notified:boolean};
const listeners=new Set<Listener>();
export function subscribeSessionExpiry(token:string,notify:()=>void):()=>void{
 const listener={token,notify,notified:false};listeners.add(listener);
 return ()=>{listeners.delete(listener)};
}
export function reportSessionExpiry(token:string):void{
 for(const listener of listeners){if(listener.token!==token||listener.notified)continue;listener.notified=true;try{listener.notify()}catch{}}
}

export type SessionHealth="valid"|"expired"|"unavailable";
const probes=new Map<string,Promise<SessionHealth>>();
// Feature routes can reject an otherwise valid session. Only /me may end it.
// Share concurrent checks, never replay the failed clinical write, and never
// discard credentials because a connection or proxy failed.
export function revalidateSession(token:string):Promise<SessionHealth>{
 const pending=probes.get(token);if(pending)return pending;
 const controller=new AbortController();
 let timer:ReturnType<typeof setTimeout>;
 const deadline=new Promise<SessionHealth>(resolve=>{timer=setTimeout(()=>{controller.abort();resolve("unavailable")},10000)});
 const read=(async():Promise<SessionHealth>=>{
  try{
   const response=await fetch("https://dentalai.tr/api/mobile/v1/me",{headers:{Authorization:"Bearer "+token},credentials:"omit",signal:controller.signal});
   if(response.status===401)return "expired";
   if(!response.ok)return "unavailable";
   const body=JSON.parse(await response.text());
   return Number.isSafeInteger(body?.user?.id)&&body.user.id>0&&body.user.is_active!==false?"valid":"unavailable";
  }catch{return "unavailable"}
 })();
 const probe=Promise.race([read,deadline]).then(health=>{if(health==="expired")reportSessionExpiry(token);return health}).finally(()=>{clearTimeout(timer);probes.delete(token)});
 probes.set(token,probe);return probe;
}
