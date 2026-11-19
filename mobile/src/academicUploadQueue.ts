import type {UploadIntent} from './academicApi';
import {parseUploadIntent} from './academicApi';

export type AcademicUploadQueue={version:1;user:number;course:number;items:UploadIntent[]};
export const MAX_ACADEMIC_UPLOAD_QUEUE_ITEMS=12;

function validateItems(items:unknown,user:number,course:number):UploadIntent[]{
 if(!Number.isSafeInteger(user)||user<1||!Number.isSafeInteger(course)||course<1||!Array.isArray(items)||items.length<1||items.length>MAX_ACADEMIC_UPLOAD_QUEUE_ITEMS)throw Error('Akademik dosya kuyruğu sınır dışında.');
 const parsed=items.map(item=>{
  const encoded=JSON.stringify(item);
  if(typeof encoded!=='string')throw Error('Akademik dosya kuyruğu kaydı serileştirilemedi.');
  return parseUploadIntent(encoded,user,course);
 });
 const keys=new Set<string>(),uris=new Set<string>(),names=new Set<string>();
 for(const item of parsed){
  if(keys.has(item.request_key)||uris.has(item.uri)||names.has(item.name))throw Error('Akademik dosya kuyruğunda yinelenen aktarım var.');
  keys.add(item.request_key);uris.add(item.uri);names.add(item.name);
 }
 return parsed;
}

export function createAcademicUploadQueue(user:number,course:number,items:unknown):AcademicUploadQueue{
 return {version:1,user,course,items:validateItems(items,user,course)};
}

export function parseAcademicUploadQueue(raw:string,user:number,course:number):AcademicUploadQueue{
 let value:unknown;
 try{value=JSON.parse(raw)}catch{throw Error('Bekleyen Akademik dosya kuyruğu okunamadı.')}
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Bekleyen Akademik dosya kuyruğu doğrulanamadı.');
 const queue=value as Record<string,unknown>;
 if(queue.version!==1||queue.user!==user||queue.course!==course)throw Error('Bekleyen Akademik dosya kuyruğu başka hesap veya derse ait.');
 return createAcademicUploadQueue(user,course,queue.items);
}

function sameAcademicUploadIdentity(a:UploadIntent,b:UploadIntent):boolean{
 return a.user===b.user&&a.course===b.course&&a.request_key===b.request_key&&a.name===b.name&&a.mime===b.mime&&a.uri===b.uri;
}

export function replaceAcademicUploadIntent(queue:AcademicUploadQueue,item:UploadIntent):AcademicUploadQueue{
 const current=queue.items.findIndex(value=>value.request_key===item.request_key);
 const next=[...queue.items];
 if(current<0){
  if(next.length>=MAX_ACADEMIC_UPLOAD_QUEUE_ITEMS)throw Error('Akademik dosya kuyruğu en fazla 12 dosya içerebilir.');
  next.push(item);
 }else{
  const previous=next[current];
  if(!sameAcademicUploadIdentity(previous,item)||(previous.size!==null&&previous.size!==item.size)||(previous.version===3&&(item.version!==3||previous.content_sha256!==item.content_sha256)))throw Error('Akademik aktarım anahtarının dosya kimliği değiştirilemez.');
  next[current]=item;
 }
 return createAcademicUploadQueue(queue.user,queue.course,next);
}

export function mergeAcademicUploadIntent(queue:AcademicUploadQueue,item:UploadIntent):AcademicUploadQueue{
 const existing=queue.items.find(value=>value.request_key===item.request_key);
 if(!existing)return replaceAcademicUploadIntent(queue,item);
 if(!sameAcademicUploadIdentity(existing,item)||(existing.size!==null&&item.size!==null&&existing.size!==item.size))throw Error('Eski ve yeni Akademik aktarım fişleri çelişiyor.');
 if(existing.version===3&&item.version===2)return queue;
 if(existing.version===3&&item.version===3&&existing.content_sha256!==item.content_sha256)throw Error('Aynı Akademik aktarım anahtarı farklı içerik özetleri taşıyor.');
 if(existing.version===2&&item.version===3)return replaceAcademicUploadIntent(queue,item);
 if(existing.version===2&&item.version===2&&existing.size===null&&item.size!==null)return replaceAcademicUploadIntent(queue,item);
 return queue;
}

export function removeAcademicUploadIntent(queue:AcademicUploadQueue,requestKey:string):AcademicUploadQueue|null{
 const next=queue.items.filter(item=>item.request_key!==requestKey);
 return next.length?createAcademicUploadQueue(queue.user,queue.course,next):null;
}

export function serializeAcademicUploadQueue(queue:AcademicUploadQueue):string{
 return JSON.stringify(createAcademicUploadQueue(queue.user,queue.course,queue.items));
}
