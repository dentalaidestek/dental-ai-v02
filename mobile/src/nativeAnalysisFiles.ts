import * as FS from 'expo-file-system/legacy';
import {normalizeAnalysisImages} from './analysisApi';
import {UploadImage} from './analysisUpload';
import {cleanupStaleClinicalMediaTemps,deleteClinicalMediaTemp,deleteClinicalMediaVaultFile,decryptClinicalMediaFile,encryptClinicalMediaFile,validateClinicalMediaVaultFile} from './clinicalMediaVault';

const MAX_ANALYSIS_IMAGE_BYTES=15*1024*1024;
export async function cacheAnalysisImages(images:Array<{uri:string;name?:string;type?:string}>,userId:number,patientId:number):Promise<UploadImage[]>{
  const normalized=normalizeAnalysisImages(images),cached:UploadImage[]=[];
  try{
    await cleanupStaleClinicalMediaTemps();
    for(const image of normalized){
      const info=await FS.getInfoAsync(image.uri);
      if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>MAX_ANALYSIS_IMAGE_BYTES)
        throw Error('Her klinik görüntü en fazla 15 MB olmalı.');
      const encryptedUri=await encryptClinicalMediaFile(image.uri,userId,patientId,MAX_ANALYSIS_IMAGE_BYTES);
      cached.push({...image,uri:encryptedUri,encryptedUri,previewUri:image.uri});
    }
    return cached;
  }catch(error){await clearAnalysisImages(cached);throw error;}
}
export async function ensureEncryptedAnalysisImages(images:UploadImage[],userId:number,patientId:number):Promise<UploadImage[]>{
  const migrated:UploadImage[]=[];
  try{
    for(const image of images){
      if(image.encryptedUri){
        await validateClinicalMediaVaultFile(image.encryptedUri,userId,patientId,MAX_ANALYSIS_IMAGE_BYTES);
        migrated.push({...image,uri:image.encryptedUri,encryptedUri:image.encryptedUri});
      }else{
        const info=await FS.getInfoAsync(image.uri);
        if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>MAX_ANALYSIS_IMAGE_BYTES)
          throw Error('Önceki analiz taslağındaki geçici görüntü artık bulunmuyor. Hasta analiz geçmişini kontrol edin.');
        const encryptedUri=await encryptClinicalMediaFile(image.uri,userId,patientId,MAX_ANALYSIS_IMAGE_BYTES);
        if(FS.cacheDirectory&&image.uri.startsWith(FS.cacheDirectory+'dai-analysis-'))await FS.deleteAsync(image.uri,{idempotent:true}).catch(()=>{});
        migrated.push({uri:encryptedUri,encryptedUri,name:image.name,type:image.type});
      }
    }
    return migrated;
  }catch(error){await clearAnalysisImages(migrated);throw error;}
}
export async function prepareAnalysisUploadImages(images:UploadImage[],userId:number,patientId:number):Promise<{images:UploadImage[];cleanup:()=>Promise<void>}>{
  const prepared:UploadImage[]=[],temporary:string[]=[];
  const cleanup=async()=>{await Promise.all(temporary.map(uri=>deleteClinicalMediaTemp(uri).catch(()=>{})));};
  try{
    for(const image of images){
      if(image.encryptedUri){
        const uri=await decryptClinicalMediaFile(image.encryptedUri,userId,patientId,image.name);
        temporary.push(uri);prepared.push({uri,name:image.name,type:image.type});
      }else{
        const info=await FS.getInfoAsync(image.uri);
        if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>MAX_ANALYSIS_IMAGE_BYTES)
          throw Error('Bekleyen analiz görüntüsünün yerel dosyası bulunamadı. Analiz geçmişini kontrol edin.');
        prepared.push({uri:image.uri,name:image.name,type:image.type});
      }
    }
    return {images:prepared,cleanup};
  }catch(error){await cleanup();throw error;}
}
export async function clearAnalysisImages(images:UploadImage[]){
  await Promise.all(images.map(async image=>{
    if(image.encryptedUri){await deleteClinicalMediaVaultFile(image.encryptedUri).catch(()=>{});return;}
    if(FS.cacheDirectory&&image.uri.startsWith(FS.cacheDirectory+'dai-analysis-'))
      await FS.deleteAsync(image.uri,{idempotent:true}).catch(()=>{});
  }));
}
export async function validateCachedAnalysisImages(images:UploadImage[],userId:number,patientId:number){
  for(const image of images){
    if(image.encryptedUri){
      await validateClinicalMediaVaultFile(image.encryptedUri,userId,patientId,MAX_ANALYSIS_IMAGE_BYTES);
      continue;
    }
    const info=await FS.getInfoAsync(image.uri);
    if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>MAX_ANALYSIS_IMAGE_BYTES)
      throw Error('Bekleyen görüntünün yerel dosyası bulunamadı. Analiz geçmişini kontrol edin.');
  }
}
