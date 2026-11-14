import {request} from './api';
export type Course={id:number;title:string;description?:string;material_count?:number};
export type Material={id:number;name:string;mime:string;size:number;index_status:string;url:string};
export type Workspace={course:Course;materials:Material[];max_file_bytes:number;max_upload_count:number;next_before:number|null};
export type Run={id:number;status:'QUEUED'|'RUNNING'|'DONE'|'FAILED'|'INTERRUPTED'|'CANCELLED';stage:string;question:string;partial?:string;error?:string};
export type Question={number:number;stem:string;options:string[];result:null|{selected:string;correct:boolean;correct_choice:string};rationale?:string;source?:string};
export type Quiz={message_id:number;questions:Question[]};
export type Message={id:number;role:string;content:string;created_at:string;quiz?:Quiz|null;artifact?:{name:string;url:string;files?:Array<{name:string;url:string}>}|null;sources:Array<{title?:string;display_name?:string;filename?:string;page?:number;quote?:string}>;vote?:string|null};
export type IndexStatus={ready:boolean;state:string;completed:number;total:number;files:Array<{id:number;filename:string;state:string;message?:string}>};
const id=(n:number)=>{if(!Number.isSafeInteger(n)||n<1)throw Error('Geçersiz ders veya kayıt kimliği.');return n};
export const coursePath=(course:number)=>`/academic/courses/${id(course)}`;
export async function library(token:string,q='',before?:number){const v=await request<{items:Course[];next_before:number|null}>('/academic/library?q='+encodeURIComponent(q)+(before?'&before='+id(before):''),token);if(!Array.isArray(v.items)||v.items.some(c=>!c||!Number.isSafeInteger(c.id)||c.id<1||typeof c.title!=='string'))throw Error('Ders listesi doğrulanamadı.');return v}
export async function workspace(token:string,course:number,before?:number){const v=await request<Workspace>(coursePath(course)+'/workspace'+(before?'?before='+id(before):''),token);if(v.course?.id!==course||!Array.isArray(v.materials)||!Number.isSafeInteger(v.max_file_bytes)||v.max_file_bytes<1||!Number.isSafeInteger(v.max_upload_count)||v.max_upload_count<1)throw Error('Ders kaynakları doğrulanamadı.');return v}
const write=<T>(token:string,path:string,method:string,payload?:unknown)=>request<T>(path,token,{method,...(payload===undefined?{}:{body:JSON.stringify(payload)})});
export const createCourse=(t:string,title:string,description:string)=>write<Workspace>(t,'/academic/library','POST',{title,description});
export const renameCourse=(t:string,c:number,title:string)=>write<Workspace>(t,coursePath(c),'PUT',{title});
export const deleteCourse=(t:string,c:number)=>write<{ok:boolean}>(t,coursePath(c),'DELETE');
export const deleteMaterial=(t:string,c:number,m:number)=>write<{ok:boolean}>(t,coursePath(c)+`/materials/${id(m)}`,'DELETE');
export const indexStatus=(t:string,c:number)=>request<IndexStatus>(coursePath(c)+'/index-status',t);
export async function timeline(t:string,c:number,before?:number){const v=await request<{items:Message[];next_before:number|null}>(coursePath(c)+'/timeline'+(before?'?before='+id(before):''),t);if(!Array.isArray(v.items))throw Error('Çalışma geçmişi doğrulanamadı.');return v}
export const quizzes=(t:string,c:number)=>request<{quizzes:Quiz[]}>(coursePath(c)+'/quizzes',t);
export function validateRun(v:{run:Run|null},nullable=false){if(v.run===null&&nullable)return null;const r=v.run;if(!r||!Number.isSafeInteger(r.id)||r.id<1||!['QUEUED','RUNNING','DONE','FAILED','INTERRUPTED','CANCELLED'].includes(r.status)||typeof r.question!=='string'||typeof r.stage!=='string')throw Error('Çalışma durumu doğrulanamadı.');return r}
export const busyRun=(r:Run|null)=>!!r&&['QUEUED','RUNNING'].includes(r.status);
export type RunIntent={user:number;course:number;request_key:string;message:string};
export function parseIntent(raw:string,user:number,course:number):RunIntent{const v=JSON.parse(raw);if(v.user!==user||v.course!==course||typeof v.message!=='string'||!v.message.trim()||v.message.length>8000||!/^[-_a-zA-Z0-9]{16,80}$/.test(v.request_key))throw Error('Bekleyen çalışma okunamadı. Sunucudaki geçmişi kontrol edin.');return v}
export const createRun=async(t:string,c:number,intent:RunIntent)=>validateRun(await write<{run:Run}>(t,coursePath(c)+'/runs','POST',{message:intent.message,request_key:intent.request_key}));
export const receipt=async(t:string,c:number,key:string)=>validateRun(await request<{run:Run|null}>(coursePath(c)+'/runs/receipt?request_key='+encodeURIComponent(key),t),true);
export const activeRun=async(t:string,c:number)=>validateRun(await request<{run:Run|null}>(coursePath(c)+'/runs/active',t),true);
export const runStatus=async(t:string,c:number,r:number)=>validateRun(await request<{run:Run}>(coursePath(c)+'/runs/'+id(r),t));
export const answer=(t:string,c:number,m:number,number:number,choice:string)=>write<{quiz:Quiz}>(t,coursePath(c)+`/quizzes/${id(m)}/answers`,'POST',{number,choice});
export const feedback=(t:string,c:number,m:number,vote:string)=>write(t,coursePath(c)+`/messages/${id(m)}/feedback`,'POST',{vote});
export function academicFilePath(course:number,path:string){const base=coursePath(course),native='/api/mobile/v1'+base;if(new RegExp('^'+native+'/(?:materials/[1-9][0-9]*/file|messages/[1-9][0-9]*/pdf(?:\\?part=[0-9]+)?)$').test(path))return path;const match=new RegExp('^/notes/courses/'+id(course)+'/ai/messages/([1-9][0-9]*)/pdf(\\?part=[0-9]+)?$').exec(path);if(match)return native+'/messages/'+match[1]+'/pdf'+(match[2]||'');throw Error('Bu dosya dersin yetkili dosya yolu değil.');}

export type Learning={practiced_facts:number;due_count:number;correct:number;wrong:number;weak_count:number;review:Array<{fact:string;source:string;due:boolean;needs_practice:boolean}>};
export const learning=(t:string,c:number)=>request<{learning:Learning}>(coursePath(c)+'/learning',t);
export const clearHistory=(t:string,c:number)=>write<{ok:boolean}>(t,coursePath(c)+'/timeline','DELETE');
export const sourcePage=(t:string,c:number,m:number,page:number)=>request<{filename:string;page:number;status:string;ocr_text:string;chunks:Array<{id:number;title:string;text:string}>}>(coursePath(c)+`/materials/${id(m)}/pages/${id(page)}/text`,t);
