const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
class El{constructor(){this.handlers={};this.hidden=false;this.checked=false;this.disabled=false;this.textContent=''}addEventListener(name,fn){this.handlers[name]=fn}}
(async()=>{
 const elements=new Map(),events={},emitted=[];let lastSocket,lastNode,stopped=0,closedContexts=0;
 const get=s=>{if(!elements.has(s))elements.set(s,new El());return elements.get(s)};
 const root=new El();root.dataset={patientId:'17'};root.querySelector=get;root.dispatchEvent=e=>emitted.push(e);
 const panel=get('[data-live-panel]');panel.querySelector=get;
 class Socket{
  static OPEN=1;
  constructor(url){assert.ok(url.endsWith('/patients/17/voice-exam/live'));assert.ok(!url.includes('key='));this.readyState=1;this.bufferedAmount=0;this.sent=[];lastSocket=this;setImmediate(()=>this.onopen?.())}
  send(body){this.sent.push(body);if(typeof body==='string'){const msg=JSON.parse(body);if(msg.type==='start')setImmediate(()=>this.message({type:'ready'}));if(msg.type==='finish'||msg.type==='pause')setImmediate(()=>this.message({type:'ended',flushed:true}))}}
  message(body){this.onmessage?.({data:JSON.stringify(body)})}
  close(){this.readyState=3;setImmediate(()=>this.onclose?.())}
 }
 class Context{constructor(){this.audioWorklet={addModule:async()=>{}};this.destination={}}async resume(){}createMediaStreamSource(){return{connect(){},disconnect(){}}}async close(){closedContexts++}}
 class Worklet{constructor(){lastNode=this;this.port={onmessage:null,postMessage:()=>setImmediate(()=>this.port.onmessage?.({data:{type:'flushed'}}))}}connect(){}disconnect(){}}
 const box={document:{getElementById:()=>root,addEventListener:()=>{}},window:{AudioContext:Context,AudioWorkletNode:Worklet,addEventListener:(n,fn)=>events[n]=fn},
  AudioContext:Context,AudioWorkletNode:Worklet,WebSocket:Socket,navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>stopped++}]})}},
  location:{protocol:'https:',host:'dentalai.tr'},CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail}},
  fetch:async()=>({json:async()=>({live_enabled:true})}),setTimeout,clearTimeout};
 vm.runInNewContext(fs.readFileSync('app/static/voice-exam-live.js','utf8'),box);
 await get('[data-live-start]').handlers.click();assert.equal(lastSocket,undefined,'No consent means no microphone/socket');
 get('[data-voice-consent]').checked=true;
 await get('[data-live-start]').handlers.click();await new Promise(setImmediate);await new Promise(setImmediate);
 assert.equal(get('[data-live-pause]').disabled,false);
 lastNode.port.onmessage({data:new ArrayBuffer(3200)});
 assert.ok(lastSocket.sent.some(x=>x instanceof ArrayBuffer));
 lastSocket.message({type:'interim',text:'Temporary sensitive preview'});
 assert.equal(get('[data-live-preview]').textContent,'Temporary sensitive preview');
 lastSocket.message({type:'final',text:'Soğuk içemiyorum.'});
 get('[data-live-finish]').handlers.click();await new Promise(r=>setTimeout(r,20));
 assert.ok(stopped>0&&closedContexts>0);
 assert.equal(get('[data-live-preview]').textContent,'');
 assert.ok(emitted.some(e=>e.type==='voice-live-segment'&&e.detail.text==='Soğuk içemiyorum.'));
 assert.ok(!emitted.some(e=>e.type==='voice-live-segment'&&e.detail.text.includes('sensitive')));
 events.pagehide();assert.equal(get('[data-live-preview]').textContent,'');
 console.log('Live controller: consent, continuous PCM, interim/final separation, finish flush and microphone cleanup passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
