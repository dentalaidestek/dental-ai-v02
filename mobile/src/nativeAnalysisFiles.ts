import * as FS from 'expo-file-system/legacy';
import {normalizeAnalysisImages} from './analysisApi';
import {UploadImage} from './analysisUpload';
import {ANALYSIS_MAX_IMAGE_BYTES,ANALYSIS_MAX_BATCH_BYTES} from './uploadLimits';
import {cleanupStaleClinicalMediaTemps,deleteClinicalMediaTemp,deleteClinicalMediaVaultFile,decryptClinicalMediaFile,encryptClinicalMediaFile,validateClinicalMediaVaultFile} from './clinicalMediaVault';

export async function cacheAnalysisImages(images:Array<{uri:string;name?:string;type?:string}>,userId:number,patientId:number):Promise<UploadImage[]>{
  const normalized=normalizeAnalysisImages(images),cached:UploadImage[]=[];
  try{
    await cleanupStaleClinicalMediaTemps();
    let totalBytes=0;
    for(const image of normalized){
      const info=await FS.getInfoAsync(image.uri);
      if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>ANALYSIS_MAX_IMAGE_BYTES)
        throw Error('Her klinik görüntü en fazla 15 MiB olmalı.');
      totalBytes+=info.size;
      if(totalBytes>ANALYSIS_MAX_BATCH_BYTES)throw Error('Bir analizde yeni görüntülerin toplamı en fazla 48 MiB olabilir.');
      const encryptedUri=await encryptClinicalMediaFile(image.uri,userId,patientId,ANALYSIS_MAX_IMAGE_BYTES,'analysis');
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
        await validateClinicalMediaVaultFile(image.encryptedUri,userId,patientId,ANALYSIS_MAX_IMAGE_BYTES,'analysis');
        migrated.push({...image,uri:image.encryptedUri,encryptedUri:image.encryptedUri});
      }else{
        const info=await FS.getInfoAsync(image.uri);
        if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>ANALYSIS_MAX_IMAGE_BYTES)
          throw Error('Önceki analiz taslağındaki geçici görüntü artık bulunmuyor. Hasta analiz geçmişini kontrol edin.');
        const encryptedUri=await encryptClinicalMediaFile(image.uri,userId,patientId,ANALYSIS_MAX_IMAGE_BYTES,'analysis');
        if(FS.cacheDirectory&&image.uri.startsWith(FS.cacheDirectory+'dai-analysis-'))await FS.deleteAsync(image.uri,{idempotent:true}).catch(()=>{});
        migrated.push({uri:encryptedUri,encryptedUri,name:image.name,type:image.type});
      }
    }
    return migrated;
  }catch(error){await clearAnalysisImages(migrated);throw error;}
}
export async function prepareAnalysisUploadImages(images:UploadImage[],userId:number,patientId:number):Promise<{images:UploadImage[];cleanup:()=>Promise<void>}>{
  const prepared:UploadImage[]=[],temporary:string[]=[];
  let totalBytes=0;
  const cleanup=async()=>{await Promise.all(temporary.map(uri=>deleteClinicalMediaTemp(uri).catch(()=>{})));};
  try{
    for(const image of images){
      let uri=image.uri;
      if(image.encryptedUri){
        uri=await decryptClinicalMediaFile(image.encryptedUri,userId,patientId,image.name,'analysis');
        temporary.push(uri);
      }
      const info=await FS.getInfoAsync(uri);
      if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>ANALYSIS_MAX_IMAGE_BYTES)
        throw Error('Bekleyen analiz görüntüsünün gerçek boyutu geçersiz veya 15 MiB sınırını aşıyor.');
      totalBytes+=info.size;
      if(totalBytes>ANALYSIS_MAX_BATCH_BYTES)
        throw Error('Bir analizde görüntülerin toplamı en fazla 48 MiB olabilir.');
      prepared.push({uri,name:image.name,type:image.type});
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
      await validateClinicalMediaVaultFile(image.encryptedUri,userId,patientId,ANALYSIS_MAX_IMAGE_BYTES,'analysis');
      continue;
    }
    const info=await FS.getInfoAsync(image.uri);
    if(!info.exists||!Number.isFinite(info.size)||info.size<1||info.size>ANALYSIS_MAX_IMAGE_BYTES)
      throw Error('Bekleyen görüntünün yerel dosyası bulunamadı. Analiz geçmişini kontrol edin.');
  }
}
