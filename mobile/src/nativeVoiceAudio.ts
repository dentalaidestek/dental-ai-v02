import * as FileSystem from 'expo-file-system/legacy';
import {ApiError} from './api';
import {revalidateSession} from './sessionExpiry';
export async function transcribeNativeRecording(token:string,patientId:number,uri:string,signal?:AbortSignal){
 if(!Number.isSafeInteger(patientId)||patientId<=0||!uri.startsWith('file://'))throw Error('Ses kaydı veya hasta kimliği geçersiz.');
 const info=await FileSystem.getInfoAsync(uri);
 if(!info.exists||!Number.isFinite(info.size)||info.size<100||info.size>8*1024*1024)throw Error('Ses kaydı okunamadı veya 8 MB sınırını aşıyor. Yerel kaydı kontrol edin.');
 const task=FileSystem.createUploadTask(`https://dentalai.tr/api/mobile/v1/patients/${patientId}/voice-exam/audio`,uri,{httpMethod:'POST',uploadType:FileSystem.FileSystemUploadType.BINARY_CONTENT,headers:{Authorization:'Bearer '+token,Cookie:'','Content-Type':'audio/mp4','X-Voice-Consent':'yes'}});
 let timedOut=false,rejectAbort:(error:Error)=>void=()=>{};const cancelled=new Promise<never>((_,reject)=>{rejectAbort=reject}),cancel=()=>{void task.cancelAsync().catch(()=>{});rejectAbort(new ApiError(408,'Ses aktarımı durduruldu; yerel kayıt korundu.'))},timer=setTimeout(()=>{timedOut=true;cancel()},150000);
 if(signal?.aborted){clearTimeout(timer);throw Error('Ses aktarımı durduruldu; yerel kayıt korundu.');}signal?.addEventListener('abort',cancel,{once:true});
 try{const response=await Promise.race([task.uploadAsync(),cancelled]);if(!response||timedOut||signal?.aborted)throw new ApiError(408,'Ses aktarımı doğrulanamadı; yerel kayıt korundu.');if(response.status===401)await revalidateSession(token);let body:any;try{body=JSON.parse(response.body)}catch{throw new ApiError(502,'Ses aktarımından geçersiz yanıt alındı; yerel kayıt korundu.');}
 if(response.status>=400||body?.ok!==true)throw new ApiError(response.status>=400?response.status:502,typeof body?.detail==='string'?body.detail:'Konuşma metni alınamadı; yerel kayıt korundu.');
 if(typeof body.transcript!=='string'||!body.transcript.trim()||body.transcript.length>18000||typeof body.revision!=='string'||!body.revision)throw new ApiError(502,'Konuşma metni yanıtı eksik; yerel kayıt korundu.');return{transcript:body.transcript,revision:body.revision};
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel)}
}
