import {request} from './api';
export type Course={id:number;title:string;description?:string;material_count?:number};
export type Material={id:number;name:string;mime:string;size:number;index_status:string;url:string};
export type CourseCreateIntent={version:1|2;user:number;title:string;description:string;known_ids:number[];request_key?:string};
export type UploadIntent={version:1;user:number;course:number;name:string;uri:string;size:number|null;known_ids:number[]};
export function parseCourseCreateIntent(raw:string,user:number):CourseCreateIntent{
 const value=JSON.parse(raw);
 if((value?.version!==1&&value?.version!==2)||value.user!==user||typeof value.title!=='string'||value.title.trim().length<2||value.title.length>120||typeof value.description!=='string'||value.description.length>500||!Array.isArray(value.known_ids)||value.known_ids.some((id:unknown)=>!Number.isSafeInteger(id)||Number(id)<1)||(value.version===2&&(typeof value.request_key!=='string'||!/^[-_a-zA-Z0-9]{16,80}$/.test(value.request_key)))||(value.version===1&&value.request_key!==undefined))throw Error('Bekleyen ders oluşturma isteği doğrulanamadı.');
 return value as CourseCreateIntent;
}
export function findCreatedCourse(items:Course[],intent:CourseCreateIntent):Course|null{
 if(!Array.isArray(items)||!intent||!Array.isArray(intent.known_ids))return null;
 const prior=new Set(intent.known_ids);
 return items.find(item=>item&&Number.isSafeInteger(item.id)&&!prior.has(item.id)&&item.title===intent.title&&(item.description||'')===intent.description)||null;
}
export function findUploadedMaterial(items:Material[],name:string,knownIds:number[],size:number|null=null):Material|null{
 if(!Array.isArray(items)||typeof name!=='string'||!Array.isArray(knownIds)||(size!==null&&(!Number.isSafeInteger(size)||size<1)))return null;
 const prior=new Set(knownIds);
 return items.find(item=>item&&Number.isSafeInteger(item.id)&&!prior.has(item.id)&&item.name===name&&(size===null||item.size===size))||null;
}
export function parseUploadIntent(raw:string,user:number,course:number):UploadIntent{
 const value=JSON.parse(raw);
 if(value?.version!==1||value.user!==user||value.course!==course||typeof value.name!=='string'||!value.name||typeof value.uri!=='string'||!value.uri.startsWith('file://')||!Array.isArray(value.known_ids)||value.known_ids.some((id:unknown)=>!Number.isSafeInteger(id)||Number(id)<1)||(value.size!==null&&(!Number.isSafeInteger(value.size)||value.size<1)))throw Error('Bekleyen dosya aktarımı doğrulanamadı. Sunucudaki kaynakları kontrol edin.');
 return value as UploadIntent;
}
export type Workspace={course:Course;materials:Material[];max_file_bytes:number;max_upload_count:number;next_before:number|null};
export type Run={id:number;status:'QUEUED'|'RUNNING'|'DONE'|'FAILED'|'INTERRUPTED'|'CANCELLED';stage:string;question:string;partial?:string|null;error?:string|null};
export type Question={number:number;stem:string;options:string[];result:null|{selected:string;correct:boolean;correct_choice:string};rationale?:string;source?:string};
export type Quiz={message_id:number;questions:Question[]};
export type Message={id:number;role:string;content:string;created_at:string;quiz?:Quiz|null;artifact?:{name:string;url:string;files?:Array<{name:string;url:string}>}|null;sources:Array<{title?:string;display_name?:string;filename?:string;page?:number;quote?:string}>;vote?:string|null};
export type IndexStatus={ready:boolean;complete:boolean;state:string;completed:number;total:number;files:Array<{id:number;filename:string;state:'preparing'|'updating'|'ready'|'update_failed'|'failed';usable?:boolean;stage?:string;error_code?:string;message?:string}>};

const isRecord=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const safeId=(value:unknown):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>0;
const boundedText=(value:unknown,max:number,allowEmpty=true):value is string=>typeof value==='string'&&value.length<=max&&(allowEmpty||value.trim().length>0);
const validCursor=(value:unknown):value is number|null=>value===null||safeId(value);

function validateAcademicQuiz(value:unknown):Quiz{
 if(!isRecord(value)||!safeId(value.message_id)||!Array.isArray(value.questions)||value.questions.length<1||value.questions.length>20)throw Error('Akademik soru seti doğrulanamadı.');
 const numbers=new Set<number>();
 for(const q of value.questions){
  if(!isRecord(q)||!safeId(q.number)||numbers.has(q.number)||!boundedText(q.stem,8000,false)||!Array.isArray(q.options)||q.options.length<2||q.options.length>5||q.options.some(option=>!boundedText(option,2000,false)))throw Error('Akademik soru içeriği doğrulanamadı.');
  numbers.add(q.number);
  if(q.result!==null&&q.result!==undefined&&(!isRecord(q.result)||!['A','B','C','D','E'].includes(String(q.result.selected))||typeof q.result.correct!=='boolean'||!['A','B','C','D','E'].includes(String(q.result.correct_choice))))throw Error('Akademik cevap kaydı doğrulanamadı.');
  if(q.rationale!==undefined&&!boundedText(q.rationale,12000))throw Error('Akademik açıklama sınır dışında.');
  if(q.source!==undefined&&!boundedText(q.source,2000))throw Error('Akademik kaynak bilgisi sınır dışında.');
 }
 return value as unknown as Quiz;
}

function validateAcademicMessage(value:unknown,course:number):Message{
 if(!isRecord(value)||!safeId(value.id)||!['USER','ASSISTANT'].includes(String(value.role))||!boundedText(value.content,500000)||!boundedText(value.created_at,80,false)||!Number.isFinite(Date.parse(String(value.created_at)))||!Array.isArray(value.sources)||value.sources.length>100)throw Error('Akademik sohbet kaydı doğrulanamadı.');
 if(value.quiz!==null&&value.quiz!==undefined){const quiz=validateAcademicQuiz(value.quiz);if(quiz.message_id!==value.id)throw Error('Soru seti başka bir sohbet kaydına bağlı.');}
 if(value.quiz_stale!==undefined&&typeof value.quiz_stale!=='boolean')throw Error('Soru kaynağı durumu doğrulanamadı.');
 if(value.vote!==undefined&&value.vote!==null&&!['like','dislike','none'].includes(String(value.vote)))throw Error('Yanıt geri bildirimi doğrulanamadı.');
 for(const source of value.sources){
  if(!isRecord(source))throw Error('Akademik kaynak kaydı doğrulanamadı.');
  for(const key of ['title','display_name','filename','quote','label','url'] as const)if(source[key]!==undefined&&source[key]!==null&&!boundedText(source[key],12000))throw Error('Akademik kaynak metni sınır dışında.');
  for(const key of ['material_id','page','page_start','page_end'] as const)if(source[key]!==undefined&&source[key]!==null&&!safeId(source[key]))throw Error('Akademik kaynak sayfa kimliği doğrulanamadı.');
  if(source.page_start!==undefined&&source.page_start!==null&&source.page_end!==undefined&&source.page_end!==null&&Number(source.page_end)<Number(source.page_start))throw Error('Akademik kaynak sayfa aralığı geçersiz.');
 }
 if(value.artifact!==null&&value.artifact!==undefined){
  const artifact=value.artifact;
  if(!isRecord(artifact)||!boundedText(artifact.name,240,false)||!boundedText(artifact.url,600,false))throw Error('Akademik PDF kaydı doğrulanamadı.');
  academicFilePath(course,artifact.url);
  if(artifact.files!==undefined&&(!Array.isArray(artifact.files)||artifact.files.length>20||artifact.files.some(file=>!isRecord(file)||!boundedText(file.name,240,false)||!boundedText(file.url,600,false)||!safeAcademicFilePath(course,file.url))))throw Error('Akademik PDF parça listesi doğrulanamadı.');
 }
 return value as unknown as Message;
}
function safeAcademicFilePath(course:number,path:unknown):boolean{if(typeof path!=='string')return false;try{academicFilePath(course,path);return true}catch{return false}}

function validateCourse(value:unknown):Course{
 if(!isRecord(value)||!safeId(value.id)||!boundedText(value.title,120,false)||(value.description!==undefined&&value.description!==null&&!boundedText(value.description,500))||(value.material_count!==undefined&&(!Number.isSafeInteger(value.material_count)||Number(value.material_count)<0)))throw Error('Ders kaydı doğrulanamadı.');
 return value as unknown as Course;
}
function validateDescendingPage<T extends {id:number}>(items:T[],next:unknown,before?:number):void{
 if(items.length>50||!validCursor(next)||items.some((item,index)=>index>0&&item.id>=items[index-1].id)||(before!==undefined&&items.some(item=>item.id>=before)))throw Error('Akademik sayfalama doğrulanamadı.');
 if(next!==null&&(items.length!==50||next!==items[items.length-1].id||(before!==undefined&&next>=before)))throw Error('Akademik sayfa imleci doğrulanamadı.');
}
function validateWorkspace(value:unknown,expectedCourse?:number,before?:number):Workspace{
 if(!isRecord(value)||!isRecord(value.course)||!safeId(value.course.id)||(expectedCourse!==undefined&&value.course.id!==expectedCourse)||!Array.isArray(value.materials)||!Number.isSafeInteger(value.max_file_bytes)||Number(value.max_file_bytes)<1||Number(value.max_file_bytes)>150*1024*1024||!Number.isSafeInteger(value.max_upload_count)||Number(value.max_upload_count)<1||Number(value.max_upload_count)>12||!validCursor(value.next_before))throw Error('Ders kaynakları doğrulanamadı.');
 const course=validateCourse(value.course),materials=value.materials.map(item=>{
  if(!isRecord(item)||!safeId(item.id)||!boundedText(item.name,240,false)||!boundedText(item.mime,120,false)||!Number.isSafeInteger(item.size)||Number(item.size)<0||Number(item.size)>150*1024*1024||!boundedText(item.index_status,40,false)||!safeAcademicFilePath(course.id,item.url))throw Error('Ders kaynak dosyası doğrulanamadı.');
  return item as unknown as Material;
 });
 if(new Set(materials.map(item=>item.id)).size!==materials.length)throw Error('Ders kaynak listesinde yinelenen kayıt var.');
 validateDescendingPage(materials,value.next_before,before);
 return {...value,course,materials} as unknown as Workspace;
}
function validateLearning(value:unknown):{learning:Learning}{
 if(!isRecord(value)||!isRecord(value.learning))throw Error('Çalışma özeti doğrulanamadı.');
 const learning=value.learning;
 for(const key of ['practiced_facts','due_count','correct','wrong','weak_count'] as const)if(!Number.isSafeInteger(learning[key])||Number(learning[key])<0)throw Error('Çalışma özeti sayıları doğrulanamadı.');
 if(!Array.isArray(learning.review)||learning.review.length>6||learning.review.some(item=>!isRecord(item)||!boundedText(item.fact,5000,false)||!boundedText(item.source,2000,false)||typeof item.due!=='boolean'||typeof item.needs_practice!=='boolean'||!Number.isSafeInteger(item.correct)||Number(item.correct)<0||!Number.isSafeInteger(item.wrong)||Number(item.wrong)<0))throw Error('Tekrar listesi doğrulanamadı.');
 for(const key of ['next_due_at','last_practiced_at'] as const)if(learning[key]!==undefined&&learning[key]!==null&&(!boundedText(learning[key],80,false)||!Number.isFinite(Date.parse(String(learning[key])))))throw Error('Çalışma zamanı doğrulanamadı.');
 return value as unknown as {learning:Learning};
}
export type SourcePage={filename:string;page:number;status:string;ocr_text:string;chunks:Array<{id:number;title:string|null;text:string}>};
function validateSourcePage(value:unknown,requestedPage:number):SourcePage{
 if(!isRecord(value)||!boundedText(value.filename,240,false)||value.page!==requestedPage||!boundedText(value.status,40,false)||!boundedText(value.ocr_text,1000000)||!Array.isArray(value.chunks)||value.chunks.length>200)throw Error('İndekslenen kaynak sayfası doğrulanamadı.');
 const ids=new Set<number>();
 for(const chunk of value.chunks){
  if(!isRecord(chunk)||!safeId(chunk.id)||ids.has(chunk.id)||(chunk.title!==null&&!boundedText(chunk.title,500))||!boundedText(chunk.text,200000))throw Error('Kaynak metin parçası doğrulanamadı.');
  ids.add(chunk.id);
 }
 return value as unknown as SourcePage;
}
const id=(n:number)=>{if(!Number.isSafeInteger(n)||n<1)throw Error('Geçersiz ders veya kayıt kimliği.');return n};
export const coursePath=(course:number)=>`/academic/courses/${id(course)}`;
export async function library(token:string,q='',before?:number){const cursor=before===undefined?undefined:id(before);const v=await request<{items:Course[];next_before:number|null}>('/academic/library?q='+encodeURIComponent(q)+(cursor?'&before='+cursor:''),token);if(!v||!Array.isArray(v.items)||!validCursor(v.next_before))throw Error('Ders listesi doğrulanamadı.');const items=v.items.map(validateCourse);if(new Set(items.map(item=>item.id)).size!==items.length)throw Error('Ders listesinde yinelenen kayıt var.');validateDescendingPage(items,v.next_before,cursor);return {...v,items}}
export async function workspace(token:string,course:number,before?:number){const cursor=before===undefined?undefined:id(before);return validateWorkspace(await request<unknown>(coursePath(course)+'/workspace'+(cursor?'?before='+cursor:''),token),course,cursor)}
const write=<T>(token:string,path:string,method:string,payload?:unknown)=>request<T>(path,token,{method,...(payload===undefined?{}:{body:JSON.stringify(payload)})});
export const createCourse=async(t:string,title:string,description:string,request_key:string)=>{if(!/^[-_a-zA-Z0-9]{16,80}$/.test(request_key))throw Error('Geçersiz ders istek anahtarı.');return validateWorkspace(await write<unknown>(t,'/academic/library','POST',{title,description,request_key}))};
export async function courseCreateReceipt(t:string,requestKey:string):Promise<Workspace|null>{
 if(!/^[-_a-zA-Z0-9]{16,80}$/.test(requestKey))throw Error('Geçersiz ders istek anahtarı.');
 const v=await request<{workspace:unknown}>('/academic/library/receipt?request_key='+encodeURIComponent(requestKey),t);
 if(!v||!('workspace' in v))throw Error('Ders kayıt fişi doğrulanamadı.');
 return v.workspace===null?null:validateWorkspace(v.workspace);
}
export const renameCourse=async(t:string,c:number,title:string)=>validateWorkspace(await write<unknown>(t,coursePath(c),'PUT',{title}),c);
export const deleteCourse=(t:string,c:number)=>write<{ok:boolean}>(t,coursePath(c),'DELETE');
export const deleteMaterial=(t:string,c:number,m:number)=>write<{ok:boolean}>(t,coursePath(c)+`/materials/${id(m)}`,'DELETE');
export function validateIndexStatus(v:IndexStatus):IndexStatus{if(!v||typeof v.ready!=='boolean'||typeof v.complete!=='boolean'||!['ready','partial','preparing','failed'].includes(v.state)||!Number.isSafeInteger(v.completed)||v.completed<0||!Number.isSafeInteger(v.total)||v.total<0||!Array.isArray(v.files)||v.files.length!==v.total||v.files.some(f=>!f||!Number.isSafeInteger(f.id)||f.id<1||typeof f.filename!=='string'||!['preparing','updating','ready','update_failed','failed'].includes(f.state)))throw Error('Akademik indeks durumu doğrulanamadı.');return v}
export const indexNeedsPolling=(v:IndexStatus|null)=>!!v&&!v.complete&&v.files.some(f=>f.state==='preparing'||f.state==='updating');
export const indexStatus=async(t:string,c:number)=>validateIndexStatus(await request<IndexStatus>(coursePath(c)+'/index-status',t));
export async function timeline(t:string,c:number,before?:number){const cursor=before===undefined?undefined:id(before);const v=await request<{items:Message[];next_before:number|null}>(coursePath(c)+'/timeline'+(cursor?'?before='+cursor:''),t);if(!v||!Array.isArray(v.items)||v.items.length>50||!validCursor(v.next_before))throw Error('Çalışma geçmişi doğrulanamadı.');const items=v.items.map(item=>validateAcademicMessage(item,c));if(new Set(items.map(item=>item.id)).size!==items.length||items.some((item,index)=>index>0&&item.id<=items[index-1].id)||(cursor!==undefined&&items.some(item=>item.id>=cursor))||(v.next_before!==null&&(items.length!==50||v.next_before!==items[0].id||(cursor!==undefined&&v.next_before>=cursor)))||(items.length===0&&v.next_before!==null))throw Error('Akademik sohbet sayfalaması doğrulanamadı.');return {...v,items}}
export async function quizzes(t:string,c:number){const v=await request<{quizzes:unknown}>(coursePath(c)+'/quizzes',t);if(!v||!Array.isArray(v.quizzes)||v.quizzes.length>40)throw Error('Soru geçmişi doğrulanamadı.');const items=v.quizzes.map(validateAcademicQuiz);if(new Set(items.map(item=>item.message_id)).size!==items.length)throw Error('Soru geçmişinde yinelenen kayıt var.');return {quizzes:items}}
export function validateRun(v:{run:Run|null},nullable=false){if(v?.run===null&&nullable)return null;const r=v?.run;if(!r||!safeId(r.id)||!['QUEUED','RUNNING','DONE','FAILED','INTERRUPTED','CANCELLED'].includes(r.status)||!boundedText(r.question,8000,false)||!boundedText(r.stage,300,false)||(r.partial!==undefined&&r.partial!==null&&!boundedText(r.partial,500000))||(r.error!==undefined&&r.error!==null&&!boundedText(r.error,2000)))throw Error('Çalışma durumu doğrulanamadı.');return r}
export const busyRun=(r:Run|null)=>!!r&&['QUEUED','RUNNING'].includes(r.status);
export type RunIntent={user:number;course:number;request_key:string;message:string};
export function parseIntent(raw:string,user:number,course:number):RunIntent{const v=JSON.parse(raw);if(v.user!==user||v.course!==course||typeof v.message!=='string'||!v.message.trim()||v.message.length>8000||!/^[-_a-zA-Z0-9]{16,80}$/.test(v.request_key))throw Error('Bekleyen çalışma okunamadı. Sunucudaki geçmişi kontrol edin.');return v}
export const createRun=async(t:string,c:number,intent:RunIntent)=>validateRun(await write<{run:Run}>(t,coursePath(c)+'/runs','POST',{message:intent.message,request_key:intent.request_key}));
export const receipt=async(t:string,c:number,key:string)=>validateRun(await request<{run:Run|null}>(coursePath(c)+'/runs/receipt?request_key='+encodeURIComponent(key),t),true);
export const activeRun=async(t:string,c:number)=>validateRun(await request<{run:Run|null}>(coursePath(c)+'/runs/active',t),true);
export const runStatus=async(t:string,c:number,r:number)=>validateRun(await request<{run:Run}>(coursePath(c)+'/runs/'+id(r),t));
export const cancelRun=async(t:string,c:number,r:number)=>validateRun(await write<{run:Run}>(t,coursePath(c)+'/runs/'+id(r)+'/cancel','POST'));
export const answer=async(t:string,c:number,m:number,number:number,choice:string)=>{const v=await write<{quiz:unknown}>(t,coursePath(c)+`/quizzes/${id(m)}/answers`,'POST',{number,choice});return {...v,quiz:validateAcademicQuiz(v?.quiz)}};
export const feedback=(t:string,c:number,m:number,vote:string)=>write(t,coursePath(c)+`/messages/${id(m)}/feedback`,'POST',{vote});
export function academicFilePath(course:number,path:string){const base=coursePath(course),native='/api/mobile/v1'+base;if(new RegExp('^'+native+'/(?:materials/[1-9][0-9]*/file|messages/[1-9][0-9]*/pdf(?:\\?part=[0-9]+)?)$').test(path))return path;const match=new RegExp('^/notes/courses/'+id(course)+'/ai/messages/([1-9][0-9]*)/pdf(\\?part=[0-9]+)?$').exec(path);if(match)return native+'/messages/'+match[1]+'/pdf'+(match[2]||'');throw Error('Bu dosya dersin yetkili dosya yolu değil.');}

export type Learning={practiced_facts:number;due_count:number;correct:number;wrong:number;weak_count:number;review:Array<{fact:string;source:string;due:boolean;needs_practice:boolean}>};
export const learning=async(t:string,c:number)=>validateLearning(await request<unknown>(coursePath(c)+'/learning',t));
export const clearHistory=(t:string,c:number)=>write<{ok:boolean}>(t,coursePath(c)+'/timeline','DELETE');
export const sourcePage=async(t:string,c:number,m:number,page:number):Promise<SourcePage>=>{const requested=id(page);return validateSourcePage(await request<unknown>(coursePath(c)+`/materials/${id(m)}/pages/${requested}/text`,t),requested)};
