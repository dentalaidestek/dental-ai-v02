type Listener={token:string;notify:()=>void;notified:boolean};
const listeners=new Set<Listener>();
export function subscribeSessionExpiry(token:string,notify:()=>void):()=>void{
 const listener={token,notify,notified:false};listeners.add(listener);
 return ()=>{listeners.delete(listener)};
}
export function reportSessionExpiry(token:string):void{
 for(const listener of listeners){if(listener.token!==token||listener.notified)continue;listener.notified=true;try{listener.notify()}catch{}}
}
