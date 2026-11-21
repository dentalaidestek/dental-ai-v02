import {useEffect} from "react";
import {AppState} from "react-native";
import {revalidateSession} from "./sessionExpiry";

export function useSessionHealth(token:string|undefined):void{
 useEffect(()=>{
  if(!token)return;
  const subscription=AppState.addEventListener("change",state=>{
   if(state==="active")void revalidateSession(token);
  });
  return()=>subscription.remove();
 },[token]);
}
