const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
class El{constructor(){this.handlers={};this.disabled=false;this.children=[];this.value=0;this.textContent=''}addEventListener(n,f){this.handlers[n]=f}replaceChildren(){this.children=[]}append(x){this.children.push(x)}}
(async()=>{
 const els=new Map(),events={},root=new El();let timer,lastNode,stopped=0,closed=0,resolvePermission;
 const get=s=>{if(!els.has(s))els.set(s,new El());return els.get(s)};root.querySelector=get;
 class Context{constructor(){this.audioWorklet={addModule:async()=>{}};this.destination={}}async resume(){}createMediaStreamSource(){return{connect(){},disconnect(){}}}async close(){closed++}}
 class Worklet{constructor(){lastNode=this;this.port={onmessage:null}}connect(){}disconnect(){}}
 const box={document:{getElementById:()=>root,createElement:()=>new El(),addEventListener:(n,f)=>events[n]=f,hidden:false},window:{isSecureContext:true,AudioContext:Context,AudioWorkletNode:Worklet,addEventListener:(n,f)=>events[n]=f},AudioContext:Context,AudioWorkletNode:Worklet,navigator:{mediaDevices:{getUserMedia:()=>new Promise(r=>resolvePermission=r)}},setTimeout:fn=>{timer=fn;return 1},clearTimeout(){},ArrayBuffer,Int16Array};
 vm.runInNewContext(fs.readFileSync('app/static/voice-device-check.js','utf8'),box);
 const pending=get('[data-device-start]').handlers.click();resolvePermission({getTracks:()=>[{stop(){stopped++}}]});await pending;
 lastNode.port.onmessage({data:new Int16Array([1200,2300,0]).buffer});timer();
 assert.equal(stopped,1);assert.equal(closed,1);assert.equal(get('[data-device-start]').disabled,false);
 assert.ok(get('[data-device-results]').children[0].textContent.includes('PCM16'));
 const late=get('[data-device-start]').handlers.click();get('[data-device-stop]').handlers.click();resolvePermission({getTracks:()=>[{stop(){stopped++}}]});await late;
 assert.equal(stopped,2,'Late permission must immediately stop its stream');
 events.pagehide();assert.equal(get('[data-device-results]').children.length,0);
 console.log('Local device check: PCM signal, timer shutdown, late permission cleanup and no provider transfer passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
