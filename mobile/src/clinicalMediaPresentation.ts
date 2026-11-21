import {API_BASE} from './api';

export type ClinicalMediaImageVariant='thumbnail'|'original'|'analysis';

const API_ROOT=API_BASE.replace(/\/+$/,'');
const MEDIA_PATH=/^\/patients\/([1-9]\d*)\/media\/([1-9]\d*)\/(file|thumbnail)$/;

/** A media image must be remounted when the authenticated owner/session scope changes. */
export function clinicalMediaImageKey(owner:string,mediaId:number,variant:ClinicalMediaImageVariant):string{
 if(typeof owner!=='string'||!owner||owner.length>8192||
    !Number.isSafeInteger(mediaId)||mediaId<=0||
    !['thumbnail','original','analysis'].includes(variant))
  throw Error('Klinik görsel görüntü kapsamı doğrulanamadı.');
 return 'clinical-media:'+owner+':'+variant+':'+mediaId;
}

/** Build a non-secret React identity for private analysis images. Never put a bearer token in a key or test identifier. */
export function clinicalAnalysisImageKey(scope:string,analysisId:number,assetId:number,revision:number):string{
 if(typeof scope!=='string'||!scope||scope.length>128||/\\s/.test(scope)||
    !Number.isSafeInteger(analysisId)||analysisId<=0||
    !Number.isSafeInteger(assetId)||assetId<=0||
    !Number.isSafeInteger(revision)||revision<0)
  throw Error('Klinik analiz görsel kapsamı doğrulanamadı.');
 return 'clinical-analysis:'+scope+':'+analysisId+':'+assetId+':'+revision;
}

/** Force the native image pipeline to revalidate the owner-authorized private URL. */
export function clinicalMediaImageSource(uri:string,token:string){
 if(typeof token!=='string'||!token.trim()||/\s/.test(token)||token.length>8192||
    typeof uri!=='string'||!uri.startsWith(API_ROOT+'/')||
    !MEDIA_PATH.test(uri.slice(API_ROOT.length)))
  throw Error('Klinik görsel adresi veya oturumu doğrulanamadı.');
 return {
  uri,
  headers:{Authorization:'Bearer '+token},
  cache:'reload' as const,
 };
}
