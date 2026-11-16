import * as FS from 'expo-file-system/legacy';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {xchacha20poly1305} from '@noble/ciphers/chacha.js';
import {bytesToHex,hexToBytes,randomBytes} from '@noble/ciphers/utils.js';

const VAULT_ROOT='dai-clinical-vault/';
const STAGE_PREFIX='dai-clinical-stage-';
const UPLOAD_PREFIX='dai-clinical-upload-';
const KEY_PREFIX='dai.clinical-media.vault.v1.';
const BASE64='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export class ClinicalMediaVaultError extends Error {
  readonly code:string;
  constructor(code:string,message:string){super(message);this.name='ClinicalMediaVaultError';this.code=code;}
}
function validScope(userId:number,patientId:number){
  if(!Number.isSafeInteger(userId)||userId<1||!Number.isSafeInteger(patientId)||patientId<1)
    throw new ClinicalMediaVaultError('INVALID_SCOPE','Klinik görüntü güvenli depolama kapsamı geçersiz.');
}
function documentRoot(){if(!FS.documentDirectory)throw new ClinicalMediaVaultError('STORAGE_UNAVAILABLE','Uygulamanın kalıcı özel dosya alanı kullanılamıyor.');return FS.documentDirectory+VAULT_ROOT;}
function cacheRoot(){if(!FS.cacheDirectory)throw new ClinicalMediaVaultError('STORAGE_UNAVAILABLE','Uygulamanın geçici dosya alanı kullanılamıyor.');return FS.cacheDirectory;}
function keyName(userId:number,patientId:number){return KEY_PREFIX+userId+'.'+patientId;}
function decodeBase64(value:string):Uint8Array{
  const clean=value.replace(/[^A-Za-z0-9+/=]/g,'').replace(/=+$/,'');
  const output=new Uint8Array(Math.floor(clean.length*3/4));
  let accumulator=0,bits=0,index=0;
  for(let i=0;i<clean.length;i++){
    const digit=BASE64.indexOf(clean[i]);if(digit<0)continue;
    accumulator=(accumulator<<6)|digit;bits+=6;
    if(bits>=8){bits-=8;output[index++]=(accumulator>>bits)&255;}
  }
  return output.slice(0,index);
}
function encodeBase64(bytes:Uint8Array):string{
  const chunks:string[]=[];
  const chunkSize=12288;
  for(let start=0;start<bytes.length;start+=chunkSize){
    const end=Math.min(bytes.length,start+chunkSize),parts:string[]=[];
    for(let i=start;i<end;i+=3){
      const a=bytes[i],hasB=i+1<end,hasC=i+2<end,b=hasB?bytes[i+1]:0,c=hasC?bytes[i+2]:0;
      const n=(a<<16)|(b<<8)|c;
      parts.push(BASE64[(n>>18)&63]+BASE64[(n>>12)&63]+(hasB?BASE64[(n>>6)&63]:'=')+(hasC?BASE64[n&63]:'='));
    }
    chunks.push(parts.join(''));
  }
  return chunks.join('');
}
async function loadKey(userId:number,patientId:number,create:boolean):Promise<Uint8Array>{
  const name=keyName(userId,patientId),stored=await SecureStore.getItemAsync(name);
  if(stored){
    try{const key=hexToBytes(stored);if(key.length===32)return key;}catch{}
    throw new ClinicalMediaVaultError('KEY_INVALID','Klinik görüntü şifreleme anahtarı doğrulanamadı.');
  }
  if(!create)throw new ClinicalMediaVaultError('KEY_MISSING','Klinik görüntünün güvenli anahtarı bulunamadı. Görseli yeniden seçin.');
  const key=randomBytes(32);
  await SecureStore.setItemAsync(name,bytesToHex(key),{keychainAccessible:SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY});
  return key;
}
export function isClinicalMediaVaultUri(uri:string,userId?:number,patientId?:number):boolean{
  if(typeof uri!=='string'||!FS.documentDirectory)return false;
  const root=FS.documentDirectory+VAULT_ROOT;
  if(!uri.startsWith(root)||uri.includes('..')||!uri.endsWith('.dai'))return false;
  const relative=uri.slice(root.length).split('/');
  if(relative.length!==3||!/^\d+$/.test(relative[0])||!/^\d+$/.test(relative[1])||!/^[A-Za-z0-9_-]{16,96}\.dai$/.test(relative[2]))return false;
  return (userId===undefined||Number(relative[0])===userId)&&(patientId===undefined||Number(relative[1])===patientId);
}
export async function encryptClinicalMediaFile(sourceUri:string,userId:number,patientId:number,maxBytes:number):Promise<string>{
  validScope(userId,patientId);
  if(typeof sourceUri!=='string'||!sourceUri||!Number.isSafeInteger(maxBytes)||maxBytes<1)
    throw new ClinicalMediaVaultError('INVALID_SOURCE','Klinik görüntü kaynağı geçersiz.');
  const cache=cacheRoot(),document=documentRoot();
  const stageUri=cache+STAGE_PREFIX+Crypto.randomUUID()+'.bin';
  let destination='';
  try{
    // Reject known oversized picker sources before copying plaintext into cache.
    // Some Android content providers cannot stat opaque URIs; those fall back
    // to the staged-file check below, which remains authoritative.
    try{
      const sourceInfo=await FS.getInfoAsync(sourceUri);
      if(sourceInfo.exists&&Number.isFinite(sourceInfo.size)){
        if(sourceInfo.size<1)throw new ClinicalMediaVaultError('SOURCE_MISSING','Seçilen klinik görüntü artık cihazda bulunmuyor. Yeniden seçin.');
        if(sourceInfo.size>maxBytes)throw new ClinicalMediaVaultError('TOO_LARGE','Klinik görüntü dosyası izin verilen boyutu aşıyor.');
      }
    }catch(error){
      if(error instanceof ClinicalMediaVaultError)throw error;
    }
    try{await FS.copyAsync({from:sourceUri,to:stageUri});}catch{throw new ClinicalMediaVaultError('SOURCE_MISSING','Seçilen klinik görüntü artık cihazda bulunmuyor. Bekleyen taslağı sunucu fişleriyle kontrol edip görseli yeniden seçin.');}
    const info=await FS.getInfoAsync(stageUri);
    if(!info.exists||!Number.isFinite(info.size)||info.size<1)
      throw new ClinicalMediaVaultError('SOURCE_MISSING','Seçilen klinik görüntü artık cihazda bulunmuyor. Yeniden seçin.');
    if(info.size>maxBytes)
      throw new ClinicalMediaVaultError('TOO_LARGE','Klinik görüntü dosyası izin verilen boyutu aşıyor.');
    const encoded=await FS.readAsStringAsync(stageUri,{encoding:'base64'} as any);
    const plaintext=decodeBase64(encoded);
    if(!plaintext.length||plaintext.length>maxBytes)
      throw new ClinicalMediaVaultError('INVALID_SOURCE','Klinik görüntü dosyası okunamadı veya boyut sınırını aşıyor.');
    const key=await loadKey(userId,patientId,true),nonce=randomBytes(24);
    const ciphertext=xchacha20poly1305(key,nonce).encrypt(plaintext);
    const packed=new Uint8Array(nonce.length+ciphertext.length);packed.set(nonce);packed.set(ciphertext,nonce.length);
    const directory=document+userId+'/'+patientId+'/';
    await FS.makeDirectoryAsync(directory,{intermediates:true});
    destination=directory+Crypto.randomUUID()+'.dai';
    await FS.writeAsStringAsync(destination,encodeBase64(packed),{encoding:'base64'} as any);
    return destination;
  }catch(error){
    if(destination)await FS.deleteAsync(destination,{idempotent:true}).catch(()=>{});
    throw error;
  }finally{
    await FS.deleteAsync(stageUri,{idempotent:true}).catch(()=>{});
  }
}
export async function validateClinicalMediaVaultFile(uri:string,userId:number,patientId:number,maxBytes:number):Promise<void>{
  validScope(userId,patientId);
  if(!isClinicalMediaVaultUri(uri,userId,patientId))
    throw new ClinicalMediaVaultError('INVALID_VAULT','Klinik görüntü güvenli dosya yolu doğrulanamadı.');
  const info=await FS.getInfoAsync(uri);
  if(!info.exists||!Number.isFinite(info.size)||info.size<41||info.size>maxBytes+40)
    throw new ClinicalMediaVaultError('VAULT_MISSING','Şifreli klinik görüntü bulunamadı veya bozuk. Taslağı doğrulayın.');
  await loadKey(userId,patientId,false);
}
export async function decryptClinicalMediaFile(uri:string,userId:number,patientId:number,name:string):Promise<string>{
  validScope(userId,patientId);
  if(!isClinicalMediaVaultUri(uri,userId,patientId))
    throw new ClinicalMediaVaultError('INVALID_VAULT','Klinik görüntü güvenli dosya yolu doğrulanamadı.');
  const info=await FS.getInfoAsync(uri);
  if(!info.exists||!Number.isFinite(info.size)||info.size<41)
    throw new ClinicalMediaVaultError('VAULT_MISSING','Şifreli klinik görüntü bulunamadı. Görseli yeniden seçin.');
  const packedBase64=await FS.readAsStringAsync(uri,{encoding:'base64'} as any);
  const packed=decodeBase64(packedBase64);
  if(packed.length<41)throw new ClinicalMediaVaultError('INVALID_VAULT','Şifreli klinik görüntü dosyası eksik.');
  const key=await loadKey(userId,patientId,false);
  let plaintext:Uint8Array;
  try{plaintext=xchacha20poly1305(key,packed.slice(0,24)).decrypt(packed.slice(24));}
  catch{throw new ClinicalMediaVaultError('AUTH_FAILED','Klinik görüntü şifresi doğrulanamadı. Güvenli taslak korunuyor.');}
  const extension=(name.match(/\.([A-Za-z0-9]{1,8})$/)?.[1]||'jpg').toLowerCase();
  const tempUri=cacheRoot()+UPLOAD_PREFIX+Crypto.randomUUID()+'.'+extension;
  await FS.writeAsStringAsync(tempUri,encodeBase64(plaintext),{encoding:'base64'} as any);
  return tempUri;
}
export async function deleteClinicalMediaVaultFile(uri:string):Promise<void>{
  if(!isClinicalMediaVaultUri(uri))throw new ClinicalMediaVaultError('INVALID_VAULT','Yalnızca Dental AI güvenli klinik dosyaları silinebilir.');
  await FS.deleteAsync(uri,{idempotent:true});
}
export async function deleteClinicalMediaTemp(uri:string):Promise<void>{
  const cache=cacheRoot();
  if(!uri.startsWith(cache)||uri.includes('..'))throw new ClinicalMediaVaultError('INVALID_TEMP','Yalnızca geçici klinik aktarım dosyaları silinebilir.');
  const name=uri.slice(cache.length);
  if(!name.startsWith(STAGE_PREFIX)&&!name.startsWith(UPLOAD_PREFIX))throw new ClinicalMediaVaultError('INVALID_TEMP','Geçici klinik dosya adı doğrulanamadı.');
  await FS.deleteAsync(uri,{idempotent:true});
}
/** Remove crash-orphaned encrypted files for one user/patient scope.
 * The caller passes every encrypted URI still referenced by its durable
 * pending upload intent. Invalid retained paths fail closed; directory-listing
 * failures leave all files untouched.
 */
export async function cleanupOrphanedClinicalMediaVaultFiles(
  userId:number,
  patientId:number,
  retainedUris:readonly string[],
):Promise<number>{
  validScope(userId,patientId);
  if(!Array.isArray(retainedUris))
    throw new ClinicalMediaVaultError('INVALID_VAULT','Bekleyen klinik görüntü listesi doğrulanamadı.');
  const retained=new Set<string>();
  for(const uri of retainedUris){
    if(!isClinicalMediaVaultUri(uri,userId,patientId))
      throw new ClinicalMediaVaultError('INVALID_VAULT','Bekleyen klinik görüntü kapsamı doğrulanamadı.');
    retained.add(uri);
  }
  const directory=documentRoot()+userId+'/'+patientId+'/';
  let names:string[];
  try{names=await FS.readDirectoryAsync(directory);}catch{return 0;}
  let deleted=0;
  for(const name of names){
    if(!/^[A-Za-z0-9_-]{16,96}\.dai$/.test(name))continue;
    const uri=directory+name;
    if(retained.has(uri))continue;
    try{await FS.deleteAsync(uri,{idempotent:true});deleted++;}catch{}
  }
  return deleted;
}

export async function cleanupStaleClinicalMediaTemps(maxAgeMs=60*60*1000):Promise<void>{
  if(!FS.cacheDirectory)return;
  let names:string[]=[];try{names=await FS.readDirectoryAsync(FS.cacheDirectory);}catch{return;}
  for(const name of names){
    if(!name.startsWith(STAGE_PREFIX)&&!name.startsWith(UPLOAD_PREFIX))continue;
    const uri=FS.cacheDirectory+name;
    try{
      const info=await FS.getInfoAsync(uri);if(!info.exists)continue;
      const raw=Number(info.modificationTime||0),modifiedMs=raw>1e12?raw:raw*1000;
      if(modifiedMs>0&&Date.now()-modifiedMs>maxAgeMs)await FS.deleteAsync(uri,{idempotent:true});
    }catch{}
  }
}
