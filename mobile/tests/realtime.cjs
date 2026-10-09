const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness(store) {
 const sockets=[], cleanups=[], states=[], timers=[];
 class Socket {
  static OPEN=1;
  readyState=1;
  sent=[];
  constructor(url,protocol,options){this.options=options;sockets.push(this);}
  send(value){this.sent.push(JSON.parse(value));}
  close(){this.onclose?.();}
 }
 const react={createContext:()=>({Provider:'Provider'}),useCallback:f=>f,useContext:()=>{},useEffect:f=>cleanups.push(f()),useMemo:f=>f(),useState:()=>[null,value=>states.push(value)],createElement:()=>{}};
 react.default=react;
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/realtime.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const cursorCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/realtimeCursor.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const cursorModule={exports:{}};
 vm.runInNewContext(cursorCode,{exports:cursorModule.exports});
 const exports={};
 vm.runInNewContext(code,{exports,WebSocket:Socket,require:name=>name==='react'?react:name==='expo-secure-store'?store:cursorModule.exports,setTimeout:f=>{timers.push(f);return timers.length},clearTimeout:()=>{}});
 return {render:(token,userId)=>exports.RealtimeProvider({token,userId,children:null}),sockets,cleanups,states,timers};
}
test('session replacement cancels delayed storage restore and stale socket reconnect',async()=>{
 const readers=[];
 const h=harness({getItemAsync:key=>new Promise(resolve=>readers.push({key,resolve})),setItemAsync:async()=>{}});
 h.render('old-token',1);h.cleanups[0]();h.render('new-token',2);
 readers[0].resolve('900');await tick();assert.equal(h.sockets.length,0);
 readers[1].resolve('1000');await tick();assert.equal(h.sockets.length,1);
 const ws=h.sockets[0];assert.equal(ws.options.headers.Authorization,'Bearer new-token');
 ws.onopen();assert.equal(ws.sent.find(x=>x.type==='resume').after_id,500);
 h.cleanups[1]();ws.onclose();ws.onmessage({data:JSON.stringify({type:'event',event_id:1001})});await tick();
 assert.equal(h.timers.length,0);
 assert.equal(h.states.filter(x=>x?.event_id===1001).length,0);
});
test('server event_id is applied once and cursor writes are serialized',async()=>{
 const writes=[], finish=[];
 const h=harness({getItemAsync:async()=> '900',setItemAsync:(key,value)=>new Promise(resolve=>{writes.push([key,value]);finish.push(resolve)})});
 h.render('token',7);await tick();const ws=h.sockets[0];ws.onopen();
 for(const id of [1001,1002,1002,950])ws.onmessage({data:JSON.stringify({type:'event',event_id:id,event_type:'MESSAGE_CREATED'})});
 await tick();assert.deepEqual(writes,[['dai.realtime.last_id.7','1001']]);
 finish[0]();await tick();assert.equal(writes[1][1],'1002');
 finish[1]();await tick();assert.equal(writes[2][1],'1002');
 finish[2]();await tick();
 assert.deepEqual(h.states.filter(x=>x?.event_id).map(x=>x.event_id),[1001,1002,950]);
 // Replay pagination uses its own page cursor, not a newer live event cursor.
 ws.onmessage({data:JSON.stringify({type:'resume_complete',has_more:true,last_event_id:975})});await tick();
 assert.equal(ws.sent.at(-1).after_id,975);h.cleanups[0]();
});
