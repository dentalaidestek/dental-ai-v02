import * as FS from 'expo-file-system/legacy';
import {ApiError} from './api';
import {revalidateSession} from './sessionExpiry';
export type AcademicFile={uri:string;name:string;mimeType:string;size?:number};
export async function uploadAcademic(token:string,course:number,file:AcademicFile,maxBytes:number,progress:(fraction:number)=>void,signal?:AbortSignal){
 if(!Number.isSafeInteger(course)||course<1||!file.uri.startsWith('file://')||!/^.{1,240}\.(pdf|jpe?g|png|webp)$/i.test(file.name))throw Error('PDF/JPG/PNG/WEBP dosyası seçin.');
 const info=await FS.getInfoAsync(file.uri);if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>maxBytes)throw Error('Dosya okunamadı veya dersin dosya boyutu sınırı aşıldı.');
 const task=FS.createUploadTask(`https://dentalai.tr/api/mobile/v1/academic/courses/${course}/materials`,file.uri,{httpMethod:'POST',uploadType:FS.FileSystemUploadType.MULTIPART,fieldName:'files',mimeType:file.mimeType,parameters:{original_filename:file.name},headers:{Authorization:'Bearer '+token,Cookie:''}},p=>progress(p.totalBytesExpectedToSend>0?Math.min(1,p.totalBytesSent/p.totalBytesExpectedToSend):0));
 let rejectAbort:(error:Error)=>void=()=>{};const cancelled=new Promise<never>((_,reject)=>{rejectAbort=reject});const cancel=()=>{void task.cancelAsync().catch(()=>{});rejectAbort(new ApiError(408,'Aktarımın sonucu belirsiz. Tekrar yüklemeden önce ders kaynaklarını kontrol edin.'))};const timer=setTimeout(cancel,600000);
 if(signal?.aborted){clearTimeout(timer);throw Error('Aktarım durduruldu.')}signal?.addEventListener('abort',cancel,{once:true});
 try{const result=await Promise.race([task.uploadAsync(),cancelled]);if(result?.status===401)await revalidateSession(token);let body:any;try{body=JSON.parse(result?.body||'')}catch{throw Error('Aktarım sonucu doğrulanamadı. Ders kaynaklarını kontrol edin.')}if(!result||result.status>=400||body.ok!==true)throw new ApiError(result?.status||502,typeof body.detail==='string'?body.detail:'Dosya kaydı doğrulanamadı. Ders kaynaklarını kontrol edin.');}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel)}
}
