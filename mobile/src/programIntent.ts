import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const KEY_PREFIX='dai.program.create.v1.';
const REQUEST_KEY=/^[A-Za-z0-9_-]{16,96}$/;

function storageKey(userId:number,patientId?:number){
 if(!Number.isSafeInteger(userId)||userId<=0||patientId!==undefined&&(!Number.isSafeInteger(patientId)||patientId<=0))throw Error('Geçersiz Program hesap kapsamı.');
 return KEY_PREFIX+userId;
}

/**
 * Only one random request key is stored per account, across all appointment entry
 * points. Titles, notes, patient identifiers, tokens and payloads stay out of storage.
 */
export async function loadProgramRequestKey(userId:number,patientId?:number):Promise<string|null>{
 const value=await SecureStore.getItemAsync(storageKey(userId,patientId));
 if(value===null)return null;
 if(!REQUEST_KEY.test(value))throw Error('Bekleyen Program isteği kaydı bozuk; yeni istek başlatılmadı.');
 return value;
}

export async function getOrCreateProgramRequestKey(userId:number,patientId?:number):Promise<string>{
 const key=storageKey(userId,patientId);
 const existing=await loadProgramRequestKey(userId,patientId);
 if(existing)return existing;
 const created=Crypto.randomUUID().replace(/-/g,'');
 if(!REQUEST_KEY.test(created))throw Error('Güvenli Program istek anahtarı üretilemedi.');
 await SecureStore.setItemAsync(key,created);
 if(await SecureStore.getItemAsync(key)!==created)throw Error('Program istek anahtarı güvenli biçimde kaydedilemedi.');
 return created;
}

export async function clearProgramRequestKey(userId:number,patientId:number|undefined,requestKey:string):Promise<void>{
 const key=storageKey(userId,patientId);
 const current=await SecureStore.getItemAsync(key);
 if(current===requestKey)await SecureStore.deleteItemAsync(key);
}
