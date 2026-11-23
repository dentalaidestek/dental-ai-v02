import {File} from 'expo-file-system';
import * as LegacyFS from 'expo-file-system/legacy';
import {sha256} from '@noble/hashes/sha2.js';

const MAX_ACADEMIC_FILE_BYTES=150*1024*1024;
const HASH_CHUNK_BYTES=1024*1024;

function hasControl(value:string):boolean{
 for(const character of value){const code=character.charCodeAt(0);if(code<32||code===127)return true}
 return false;
}
function hasUnsafeUriCharacters(value:string):boolean{
 return value.includes('\\')||value.includes('?')||value.includes('#')||hasControl(value);
}

export function isPrivateAcademicCacheUri(uri:string):boolean{
 const root=LegacyFS.cacheDirectory;
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

export type AcademicFileDigest={size:number;content_sha256:string};

/**
 * Hash a private Academic upload in bounded chunks. Never materializes the
 * complete PDF/image as a JS string or ArrayBuffer (uploads may reach 150 MB).
 * A missing file is null so a durable server receipt can still finish cleanup
 * after the successful upload already removed its local temporary copy.
 */
export async function hashAcademicCacheFile(uri:string,maxBytes=MAX_ACADEMIC_FILE_BYTES):Promise<AcademicFileDigest|null>{
 if(!isPrivateAcademicCacheUri(uri))throw Error('Yalnızca uygulamanın özel dosya önbelleği doğrulanabilir.');
 if(!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>MAX_ACADEMIC_FILE_BYTES)throw Error('Akademik dosya boyutu sınırı doğrulanamadı.');
 const info=await LegacyFS.getInfoAsync(uri);
 if(!info.exists)return null;
 const expectedSize=info.size;
 if(typeof expectedSize!=='number'||!Number.isSafeInteger(expectedSize)||expectedSize<1||expectedSize>maxBytes)throw Error('Dosya okunamadı veya dersin dosya boyutu sınırı aşıldı.');
 const handle=new File(uri).open();
 try{
  const openedSize=handle.size;
  if(typeof openedSize!=='number'||!Number.isSafeInteger(openedSize)||openedSize!==expectedSize)throw Error('Akademik dosya aktarım öncesinde değişti.');
  const digest=sha256.create();
  let total=0;
  while(total<expectedSize){
   const remaining=expectedSize-total;
   const bytes=await handle.readBytes(Math.min(HASH_CHUNK_BYTES,remaining));
   if(!(bytes instanceof Uint8Array)||bytes.length<1||bytes.length>remaining)throw Error('Akademik dosya güvenli biçimde okunamadı.');
   digest.update(bytes);
   total+=bytes.length;
  }
  if(total!==expectedSize||handle.size!==expectedSize)throw Error('Akademik dosya okunurken boyutu değişti.');
  const hex=Array.from(digest.digest(),byte=>byte.toString(16).padStart(2,'0')).join('');
  if(!/^[a-f0-9]{64}$/.test(hex))throw Error('Akademik dosya özeti üretilemedi.');
  return {size:total,content_sha256:hex};
 }finally{
  handle.close();
 }
}
