import * as FS from 'expo-file-system/legacy';
import {ApiError} from './api';
import {revalidateSession} from './sessionExpiry';
export type AcademicFile={uri:string;name:string;mimeType:string;size?:number};

function hasControl(value:string):boolean{
 for(const character of value){const code=character.charCodeAt(0);if(code<32||code===127)return true}
 return false;
}
function hasUnsafeUriCharacters(value:string):boolean{
 return value.includes('\\')||value.includes('?')||value.includes('#')||hasControl(value);
}
export function isPrivateAcademicCacheUri(uri:string):boolean{
 const root=FS.cacheDirectory;
 if(!root||typeof uri!=='string'||!uri.startsWith('file://')||hasUnsafeUriCharacters(uri))return false;
 try{
  const decoded=decodeURIComponent(uri),decodedRoot=decodeURIComponent(root);
  if(hasUnsafeUriCharacters(decoded))return false;
  const prefix=decodedRoot.endsWith('/')?decodedRoot:decodedRoot+'/';
  if(!decoded.startsWith(prefix))return false;
  const parts=decoded.slice(prefix.length).split('/');
  return parts.length>0&&parts.every(part=>part.length>0&&part!=='.'&&part!=='..');
 }catch{return false}
}


export async function removeAcademicCacheFile(uri:string):Promise<boolean>{
 if(!isPrivateAcademicCacheUri(uri))return false;
 try{await FS.deleteAsync(uri,{idempotent:true});return true}catch{return false}
}

function academicMime(name:string):string|null{
 const extension=name.split('.').pop()?.toLowerCase();
 if(extension==='pdf')return 'application/pdf';
 if(extension==='jpg'||extension==='jpeg')return 'image/jpeg';
 if(extension==='png')return 'image/png';
 if(extension==='webp')return 'image/webp';
 return null;
}

export async function uploadAcademic(token:string,course:number,file:AcademicFile,maxBytes:number,progress:(fraction:number)=>void,signal?:AbortSignal){
 if(!Number.isSafeInteger(course)||course<1||!isPrivateAcademicCacheUri(file.uri))throw Error('Yalnızca uygulamanın özel önbelleğine kopyalanmış dosyalar yüklenebilir.');
 if(typeof file.name!=='string'||file.name.length>240||file.name.trim()!==file.name||file.name.includes('/')||file.name.includes('\\')||hasControl(file.name))throw Error('Geçerli bir dosya adı kullanın.');
 const mime=academicMime(file.name);
 if(!mime)throw Error('PDF/JPG/PNG/WEBP dosyası seçin.');
 const supplied=(file.mimeType||'').trim().toLowerCase();
 if(supplied&&supplied!=='application/octet-stream'&&supplied!==mime)throw Error('Dosya uzantısı ile içerik türü eşleşmiyor.');
 const info=await FS.getInfoAsync(file.uri);
 if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>maxBytes)throw Error('Dosya okunamadı veya dersin dosya boyutu sınırı aşıldı.');
 const task=FS.createUploadTask(`https://dentalai.tr/api/mobile/v1/academic/courses/${course}/materials`,file.uri,{httpMethod:'POST',uploadType:FS.FileSystemUploadType.MULTIPART,fieldName:'files',mimeType:mime,parameters:{original_filename:file.name},headers:{Authorization:'Bearer '+token,Cookie:''}},p=>progress(p.totalBytesExpectedToSend>0?Math.min(1,p.totalBytesSent/p.totalBytesExpectedToSend):0));
 let rejectAbort:(error:Error)=>void=()=>{};
 const cancelled=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const cancel=()=>{void task.cancelAsync().catch(()=>{});rejectAbort(new ApiError(408,'Aktarımın sonucu belirsiz. Tekrar yüklemeden önce ders kaynaklarını kontrol edin.'))};
 const timer=setTimeout(cancel,600000);
 if(signal?.aborted){clearTimeout(timer);throw Error('Aktarım durduruldu.')}
 signal?.addEventListener('abort',cancel,{once:true});
 try{
  const result=await Promise.race([task.uploadAsync(),cancelled]);
  if(result?.status===401)await revalidateSession(token);
  let body:any;try{body=JSON.parse(result?.body||'')}catch{throw Error('Aktarım sonucu doğrulanamadı. Ders kaynaklarını kontrol edin.')}
  if(!result||result.status>=400||body.ok!==true)throw new ApiError(result?.status||502,typeof body.detail==='string'?body.detail:'Dosya kaydı doğrulanamadı. Ders kaynaklarını kontrol edin.');
  // Delete only after the server has explicitly acknowledged the stored material.
  // A timeout or lost response keeps the local copy for receipt reconciliation.
  await removeAcademicCacheFile(file.uri);
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel)}
}
