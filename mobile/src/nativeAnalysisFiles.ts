import * as FS from 'expo-file-system/legacy';
import * as Crypto from 'expo-crypto';
import {normalizeAnalysisImages} from './analysisApi';
import {UploadImage} from './analysisUpload';
export async function cacheAnalysisImages(images:Array<{uri:string;name?:string;type?:string}>):Promise<UploadImage[]>{
 if(!FS.cacheDirectory)throw Error('Güvenli uygulama önbelleği kullanılamıyor.');const normalized=normalizeAnalysisImages(images),cached:UploadImage[]=[];
 try{for(const image of normalized){const info=await FS.getInfoAsync(image.uri);if(!info.exists||info.size<1||info.size>15*1024*1024)throw Error('Her klinik görüntü en fazla 15 MB olmalı.');const destination=FS.cacheDirectory+'dai-analysis-'+Crypto.randomUUID()+'.'+image.name.split('.').pop();await FS.copyAsync({from:image.uri,to:destination});cached.push({...image,uri:destination})}return cached}catch(e){await clearAnalysisImages(cached);throw e}
}
export async function clearAnalysisImages(images:UploadImage[]){if(!FS.cacheDirectory)return;await Promise.all(images.filter(i=>i.uri.startsWith(FS.cacheDirectory+'dai-analysis-')).map(i=>FS.deleteAsync(i.uri,{idempotent:true}).catch(()=>{})))}
export async function validateCachedAnalysisImages(images:UploadImage[]){for(const image of images){const info=await FS.getInfoAsync(image.uri);if(!info.exists||info.size<1||info.size>15*1024*1024)throw Error('Bekleyen görüntünün yerel dosyası bulunamadı. Analiz geçmişini kontrol edin.')}}
