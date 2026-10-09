import {ApiError} from './api';
import type {User} from './api';

type TokenStore = {
 getItemAsync(key:string):Promise<string|null>;
 deleteItemAsync(key:string):Promise<void>;
};

export async function restoreStoredSession(store:TokenStore,validate:(token:string)=>Promise<{user:User}>):Promise<{token:string;user:User}|null>{
 const token=await store.getItemAsync('dentalai_token');
 if(!token)return null;
 try{
  const result=await validate(token);
  return {token,user:result.user};
 }catch(error){
  if(error instanceof ApiError&&error.status===401){
   await store.deleteItemAsync('dentalai_token');
   return null;
  }
  throw error;
 }
}
