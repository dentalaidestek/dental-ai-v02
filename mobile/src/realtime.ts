import React,{createContext,useCallback,useContext,useEffect,useMemo,useState}from"react";
import * as SecureStore from"expo-secure-store";
import {RealtimeCursor} from './realtimeCursor';
export type RealtimeEvent={id?:number;event_id?:number;event_type?:string;entity_type?:string;entity_id?:number|string;payload?:any;replay?:boolean;type?:string;[k:string]:any};
type Ctx={lastEvent:RealtimeEvent|null;connected:boolean;lastEventId:number;invalidate:(types?:string[])=>void};
const Context=createContext<Ctx>({lastEvent:null,connected:false,lastEventId:0,invalidate:()=>{}});
export function RealtimeProvider({token,userId,children}:{token:string;userId:number;children:React.ReactNode}){
 const[lastEvent,setLastEvent]=useState<RealtimeEvent|null>(null),[connected,setConnected]=useState(false),[lastEventId,setLastEventId]=useState(0);
 useEffect(()=>{
  let active=true, socket:WebSocket|null=null, timer:ReturnType<typeof setTimeout>|undefined;
  let cursor=new RealtimeCursor(), queue=Promise.resolve();
  const key='dai.realtime.last_id.'+userId;
  setLastEvent(null);setLastEventId(0);setConnected(false);
  const connect=()=>{
   if(!active||!token)return;
   const ws=new (WebSocket as any)('wss://dentalai.tr/ws/sync',undefined,{headers:{Authorization:'Bearer '+token}}) as WebSocket;
   socket=ws;
   const current=()=>active&&socket===ws;
   const resume=(after:number)=>{if(current()&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'resume',after_id:after}));};
   ws.onopen=()=>{if(!current())return;setConnected(true);ws.send(JSON.stringify({type:'visibility',visible:true}));resume(cursor.resumeAfter());};
   ws.onmessage=e=>{
    queue=queue.then(async()=>{
     if(!current())return;
     let evt:RealtimeEvent;try{evt=JSON.parse(e.data)}catch{return;}
     if(evt.type==='ready'||evt.type==='pong')return;
     if(evt.type==='resume_complete'){
      const page=Number(evt.last_event_id);
      if(evt.has_more&&Number.isSafeInteger(page)&&page>=0)resume(page);
      return;
     }
     if(evt.type==='resync'){resume(cursor.resumeAfter());return;}
     if(!cursor.accept(evt))return;
     setLastEventId(cursor.current);setLastEvent(evt);
     // Serialize writes; an older callback cannot overwrite a newer cursor.
     try{await SecureStore.setItemAsync(key,String(cursor.current));}catch{}
    }).catch(()=>{});
   };
   ws.onerror=()=>{if(current())try{ws.close()}catch{}};
   ws.onclose=()=>{if(!current())return;socket=null;setConnected(false);timer=setTimeout(connect,1000+Math.random()*2500);};
  };
  void(async()=>{
   let saved:string|null=null;try{saved=await SecureStore.getItemAsync(key)}catch{}
   if(!active)return;
   cursor=new RealtimeCursor(saved);setLastEventId(cursor.current);connect();
  })();
  return()=>{active=false;clearTimeout(timer);const ws=socket;socket=null;try{ws?.send(JSON.stringify({type:'visibility',visible:false}));ws?.close()}catch{}};
 },[token,userId]);
 const invalidate=useCallback((types?:string[])=>setLastEvent({type:'invalidate',event_type:types?.[0]}),[]);
 return React.createElement(Context.Provider,{value:useMemo(()=>({lastEvent,connected,lastEventId,invalidate}),[lastEvent,connected,lastEventId,invalidate])},children);
}
export function useRealtime(){return useContext(Context);}
