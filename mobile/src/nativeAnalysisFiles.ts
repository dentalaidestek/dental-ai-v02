import * as FS from 'expo-file-system/legacy';
import {normalizeAnalysisImages} from './analysisApi';
import {UploadImage} from './analysisUpload';
import {ANALYSIS_MAX_IMAGE_BYTES,ANALYSIS_MAX_BATCH_BYTES} from './uploadLimits';
const LEGACY_ANALYSIS_PREFIX='dai-analysis-';
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
  const createdEncryptedUris:string[]=[];
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
        createdEncryptedUris.push(encryptedUri);
        const legacyUri=FS.cacheDirectory&&image.uri.startsWith(FS.cacheDirectory+LEGACY_ANALYSIS_PREFIX)?image.uri:undefined;
        migrated.push({...image,uri:encryptedUri,encryptedUri,...(legacyUri?{legacyUri}:{})});
      }
    }
    return migrated;
  }catch(error){
    await Promise.all(createdEncryptedUris.map(uri=>deleteClinicalMediaVaultFile(uri)));
    throw error;
  }
}
async function deleteLegacyAnalysisSource(uri:string):Promise<void>{
  if(!FS.cacheDirectory||!uri.startsWith(FS.cacheDirectory+LEGACY_ANALYSIS_PREFIX)||uri.includes('..'))
    throw Error('Eski klinik görüntü önbellek yolu doğrulanamadı.');
  const name=uri.slice(FS.cacheDirectory.length);
  const dot=name.lastIndexOf('.'),stem=name.slice(0,dot),extension=name.slice(dot+1);
  if(dot<1||!stem.startsWith(LEGACY_ANALYSIS_PREFIX)||! /^[A-Za-z0-9_-]{8,160}$/.test(stem.slice(LEGACY_ANALYSIS_PREFIX.length))||! /^[A-Za-z0-9]{1,8}$/.test(extension))
    throw Error('Eski klinik görüntü dosya adı doğrulanamadı.');
  await FS.deleteAsync(uri,{idempotent:true});
  const remaining=await FS.getInfoAsync(uri);
  if(remaining.exists)throw Error('Eski klinik görüntünün şifresiz önbellek kopyası silinemedi. Bekleyen yükleme korundu.');
}
export async function clearLegacyAnalysisSources(images:UploadImage[]):Promise<void>{
  const sources=images.flatMap(image=>image.legacyUri?[image.legacyUri]:[]);
  await Promise.all(sources.map(deleteLegacyAnalysisSource));
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
export async function clearAnalysisImages(images:UploadImage[]):Promise<void>{
  await Promise.all(images.map(async image=>{
    const deletions:Promise<void>[]=[];
    if(image.encryptedUri)deletions.push(deleteClinicalMediaVaultFile(image.encryptedUri));
    if(image.legacyUri)deletions.push(deleteLegacyAnalysisSource(image.legacyUri));
    else if(!image.encryptedUri&&FS.cacheDirectory&&image.uri.startsWith(FS.cacheDirectory+LEGACY_ANALYSIS_PREFIX))
      deletions.push(deleteLegacyAnalysisSource(image.uri));
    await Promise.all(deletions);
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
