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

export type ProgramActionIntent =
 | {version:1;action:'complete'|'delete';event_id:number}
 | {version:1;action:'copy';event_id:number;days:string[]};

const ACTION_KEY_PREFIX='dai.program.action.v1.';

function actionStorageKey(userId:number){
 if(!Number.isSafeInteger(userId)||userId<=0)throw Error('Geçersiz Program hesap kapsamı.');
 return ACTION_KEY_PREFIX+userId;
}

function validProgramDay(value:unknown):value is string{
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
 const parsed=Date.parse(value+'T00:00:00Z');
 return Number.isFinite(parsed)&&new Date(parsed).toISOString().slice(0,10)===value;
}

function parseProgramActionIntent(value:unknown):ProgramActionIntent|null{
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const item=value as Record<string,unknown>;
 if(item.version!==1||!Number.isSafeInteger(item.event_id)||(item.event_id as number)<=0)return null;
 if(item.action==='complete'||item.action==='delete'){
  if(Object.keys(item).sort().join(',')!=='action,event_id,version')return null;
  return {version:1,action:item.action,event_id:item.event_id as number};
 }
 if(item.action==='copy'){
  if(Object.keys(item).sort().join(',')!=='action,days,event_id,version'||!Array.isArray(item.days)||item.days.length<1||item.days.length>7)return null;
  const days=item.days;
  if(days.some(day=>!validProgramDay(day))||new Set(days).size!==days.length)return null;
  return {version:1,action:'copy',event_id:item.event_id as number,days:[...days] as string[]};
 }
 return null;
}

export async function loadProgramActionIntent(userId:number):Promise<ProgramActionIntent|null>{
 const raw=await SecureStore.getItemAsync(actionStorageKey(userId));
 if(raw===null)return null;
 let parsed:unknown;
 try{parsed=JSON.parse(raw)}catch{throw Error('Bekleyen Program işlemi kaydı bozuk; yeni işlem başlatılmadı.');}
 const intent=parseProgramActionIntent(parsed);
 if(!intent)throw Error('Bekleyen Program işlemi kaydı geçersiz; yeni işlem başlatılmadı.');
 return intent;
}

/** Persist only an event ID and action/date intent; never patient or appointment content. */
export async function saveProgramActionIntent(userId:number,intent:ProgramActionIntent):Promise<void>{
 const normalized=parseProgramActionIntent(intent);
 if(!normalized)throw Error('Program işlemi doğrulanamadı.');
 const key=actionStorageKey(userId);
 const existing=await loadProgramActionIntent(userId);
 if(existing&&JSON.stringify(existing)!==JSON.stringify(normalized))throw Error('Önceki Program işlemi sunucuda doğrulanmalı.');
 const serialized=JSON.stringify(normalized);
 await SecureStore.setItemAsync(key,serialized);
 if(await SecureStore.getItemAsync(key)!==serialized)throw Error('Program işlemi güvenli biçimde saklanamadı.');
}

export async function clearProgramActionIntent(userId:number,intent:ProgramActionIntent):Promise<void>{
 const key=actionStorageKey(userId);
 const raw=await SecureStore.getItemAsync(key);
 if(raw===null)return;
 let current:unknown;
 try{current=JSON.parse(raw)}catch{throw Error('Bekleyen Program işlemi kaydı bozuk; güvenli biçimde temizlenemedi.');}
 const normalized=parseProgramActionIntent(current);
 if(!normalized)throw Error('Bekleyen Program işlemi kaydı geçersiz; güvenli biçimde temizlenemedi.');
 if(JSON.stringify(normalized)===JSON.stringify(intent))await SecureStore.deleteItemAsync(key);
}

