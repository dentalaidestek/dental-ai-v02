import React,{createContext,useContext,useEffect,useRef,useState}from"react";
import*as SecureStore from"expo-secure-store";
type EventPayload={type?:string;event_type?:string;event_id?:number;[key:string]:any};
const C=createContext({tick:0,lastEvent:null as EventPayload|null});
export function RealtimeProvider({token,children}:{token:string;children:React.ReactNode}){
 const[tick,setTick]=useState(0);const[lastEvent,setLastEvent]=useState<EventPayload|null>(null);const ws=useRef<WebSocket|null>(null);
 useEffect(()=>{let dead=false;let timer:any;let backoff=1000;
  const connect=()=>{if(dead)return;const url="wss://dentalai.tr/ws/sync?access_token="+encodeURIComponent(token);const socket=new WebSocket(url);ws.current=socket;
   socket.onopen=async()=>{backoff=1000;const raw=await SecureStore.getItemAsync("dentalai_last_event_id");socket.send(JSON.stringify({type:"resume",after_id:Number(raw||0)}));};
   socket.onmessage=async e=>{try{const data=JSON.parse(e.data) as EventPayload;if(data.event_id){await SecureStore.setItemAsync("dentalai_last_event_id",String(data.event_id));}if(data.type!=="ready"&&data.type!=="resume_complete"&&data.type!=="pong"){setLastEvent(data);setTick(v=>v+1);}}catch{}};
   socket.onclose=()=>{if(dead)return;timer=setTimeout(connect,backoff);backoff=Math.min(backoff*2,15000);};
   socket.onerror=()=>{try{socket.close()}catch{}};
  };connect();return()=>{dead=true;clearTimeout(timer);try{ws.current?.close()}catch{}};
 },[token]);
 return <C.Provider value={{tick,lastEvent}}>{children}</C.Provider>;
}
export const useRealtime=()=>useContext(C);