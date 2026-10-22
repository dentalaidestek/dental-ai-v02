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
  fetch:async()=>({json:async()=>({live_enabled:true})}),setTimeout,clearTimeout,setInterval,clearInterval};
 vm.runInNewContext(fs.readFileSync('app/static/voice-exam-live.js','utf8'),box);
 await get('[data-live-start]').handlers.click();assert.equal(lastSocket,undefined,'No consent means no microphone/socket');
 get('[data-voice-consent]').checked=true;
 await get('[data-live-start]').handlers.click();await new Promise(setImmediate);await new Promise(setImmediate);
 assert.equal(get('[data-live-pause]').disabled,false);
 assert.equal(get('[data-live-title]').textContent,'Dinleniyor');
 assert.equal(root.dataset.liveState,'listening');
 assert.equal(get('[data-live-subtitle]').textContent,'Mikrofon açık');
 assert.equal(get('[data-live-start]').hidden,true);
 assert.equal(get('[data-live-pause]').hidden,false);
 lastNode.port.onmessage({data:new ArrayBuffer(3200)});
 assert.ok(lastSocket.sent.some(x=>x instanceof ArrayBuffer));
 lastSocket.message({type:'interim',text:'Temporary sensitive preview'});
 assert.equal(get('[data-live-preview]').textContent,'Temporary sensitive preview');
 lastSocket.message({type:'final',text:'Soğuk içemiyorum.'});
 await get('[data-live-pause]').handlers.click();await new Promise(r=>setTimeout(r,20));
 assert.equal(root.dataset.liveState,'paused');assert.equal(get('[data-live-subtitle]').textContent,'Mikrofon kapalı');
 const pausedEnds=emitted.filter(e=>e.type==='voice-live-ended').length;
 root.handlers['voice-live-stop']();await new Promise(setImmediate);
 assert.equal(root.dataset.liveState,'paused');assert.equal(emitted.filter(e=>e.type==='voice-live-ended').length,pausedEnds);
 assert.equal(root.dataset.showReview,'true','Extraction error reveals preserved text');
 await get('[data-live-start]').handlers.click();await new Promise(setImmediate);await new Promise(setImmediate);
 assert.equal(root.dataset.liveState,'listening');assert.equal(root.dataset.showReview,'false');
 get('[data-live-finish]').handlers.click();await new Promise(r=>setTimeout(r,20));
 assert.ok(stopped>0&&closedContexts>0);
 assert.equal(get('[data-live-title]').textContent,'Dinleme tamamlandı');
 assert.equal(root.dataset.liveState,'idle');
 assert.equal(get('[data-live-subtitle]').textContent,'Mikrofon kapalı');
 assert.equal(get('[data-live-review]').hidden,false);
 get('[data-live-review]').handlers.click();assert.equal(root.dataset.showReview,'true');
 const before=emitted.filter(e=>e.type==='voice-live-ended').length;
 root.handlers['voice-live-stop']?.();assert.equal(emitted.filter(e=>e.type==='voice-live-ended').length,before,'Stopping an idle microphone must not finalize again');
 assert.equal(get('[data-live-preview]').textContent,'');
 assert.ok(emitted.some(e=>e.type==='voice-live-segment'&&e.detail.text==='Soğuk içemiyorum.'));
 assert.ok(!emitted.some(e=>e.type==='voice-live-segment'&&e.detail.text.includes('sensitive')));
 events.pagehide();assert.equal(get('[data-live-preview]').textContent,'');
 const previousSocket=lastSocket;
 box.navigator.mediaDevices.getUserMedia=async()=>{const e=new Error('denied');e.name='NotAllowedError';throw e};
 await get('[data-live-start]').handlers.click();
 assert.equal(lastSocket,previousSocket,'Permission denial must not open provider socket');
 assert.equal(root.dataset.hasListened,'false');assert.equal(get('[data-live-title]').textContent,'Mikrofon açılamadı');
 assert.equal(get('[data-live-finish]').hidden,true);assert.equal(get('[data-live-start]').textContent,'Tekrar dene');
 assert.ok(get('[data-live-status]').textContent.includes('Chrome'));
 assert.ok(!get('[data-live-status]').textContent.includes('Son konuşma bölümü'));
 events.pagehide();
 console.log('Live controller: consent, continuous PCM, interim/final separation, finish flush and microphone cleanup passed.');
})().catch(error=>{console.error(error);process.exitCode=1});

