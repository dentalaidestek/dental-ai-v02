import React,{createContext,useCallback,useContext,useEffect,useMemo,useRef,useState}from"react";
import * as SecureStore from"expo-secure-store";
export type RealtimeEvent={id?:number;event_type?:string;entity_type?:string;entity_id?:number|string;payload?:any;replay?:boolean;type?:string;[k:string]:any};
type Ctx={lastEvent:RealtimeEvent|null;connected:boolean;lastEventId:number;invalidate:(types?:string[])=>void};
const Context=createContext<Ctx>({lastEvent:null,connected:false,lastEventId:0,invalidate:()=>{}});
export function RealtimeProvider({token,userId,children}:{token:string;userId:number;children:React.ReactNode}){
 const[lastEvent,setLastEvent]=useState<RealtimeEvent|null>(null),[connected,setConnected]=useState(false),[lastEventId,setLastEventId]=useState(0);
 const socket=useRef<WebSocket|null>(null),timer=useRef<any>(null),closed=useRef(false),eventId=useRef(0),seenIds=useRef<Set<number>>(new Set());
 const connect=useCallback(()=>{
  if(closed.current||!token||socket.current&&(socket.current.readyState===WebSocket.OPEN||socket.current.readyState===WebSocket.CONNECTING))return;
  const ws=new WebSocket("wss://dentalai.tr/ws/sync?access_token="+encodeURIComponent(token));socket.current=ws;
  ws.onopen=async()=>{if(closed.current||socket.current!==ws)return;setConnected(true);clearTimeout(timer.current);let after=eventId.current;try{after=Math.max(after,Number(await SecureStore.getItemAsync("dai.realtime.last_id."+userId)||0))}catch{}eventId.current=after;ws.send(JSON.stringify({type:"visibility",visible:true}));ws.send(JSON.stringify({type:"resume",after_id:after}))};
  ws.onmessage=async e=>{let evt:RealtimeEvent;try{evt=JSON.parse(e.data)}catch{return}if(evt.type==="ready"||evt.type==="pong")return;if(evt.type==="resume_complete"){if(evt.has_more)ws.send(JSON.stringify({type:"resume",after_id:Number(evt.last_event_id||eventId.current)}));return}if(evt.type==="resync"){ws.send(JSON.stringify({type:"resume",after_id:eventId.current}));return}if(typeof evt.id==="number"){if(seenIds.current.has(evt.id))return;seenIds.current.add(evt.id);if(seenIds.current.size>2000){const oldest=seenIds.current.values().next().value;if(typeof oldest==="number")seenIds.current.delete(oldest)}eventId.current=Math.max(eventId.current,evt.id);setLastEventId(eventId.current);try{await SecureStore.setItemAsync("dai.realtime.last_id."+userId,String(eventId.current))}catch{}}setLastEvent(evt)};
  ws.onerror=()=>{try{ws.close()}catch{}};
  ws.onclose=()=>{if(socket.current===ws)socket.current=null;setConnected(false);if(!closed.current){clearTimeout(timer.current);timer.current=setTimeout(connect,Math.min(15000,1000+Math.random()*2500))}};
 },[token,userId]);
 useEffect(()=>{closed.current=false;eventId.current=0;seenIds.current.clear();connect();return()=>{closed.current=true;clearTimeout(timer.current);try{socket.current?.send(JSON.stringify({type:"visibility",visible:false}));socket.current?.close()}catch{}socket.current=null}},[connect]);
 const invalidate=useCallback((types?:string[])=>setLastEvent({type:"invalidate",event_type:types?.[0]}),[]);
 return React.createElement(Context.Provider,{value:useMemo(()=>({lastEvent,connected,lastEventId,invalidate}),[lastEvent,connected,lastEventId,invalidate])},children);
}
export function useRealtime(){return useContext(Context);}
