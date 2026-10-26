const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
class El{
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.checked=false;this.hidden=false;this.disabled=false;this.handlers={};this.classList={toggle(){}};this.textContent=''}
 append(...items){this.children.push(...items)}replaceChildren(...items){this.children=items;this.textContent=''}
 dispatchEvent(e){this.handlers[e.type]?.(e)}addEventListener(n,fn){this.handlers[n]=fn}setAttribute(){}
 querySelector(tag){for(const child of this.children){if(child?.tag===tag)return child;const next=child?.querySelector?.(tag);if(next)return next}return null}
}
const tick=()=>new Promise(setImmediate);
(async()=>{
 const root=new El(),elements=new Map(),events={},calls=[];root.dataset.patientId='1';
 const get=s=>{if(!elements.has(s))elements.set(s,new El());return elements.get(s)};
 root.querySelector=get;root.querySelectorAll=s=>s==='[data-field-row]'?get('[data-voice-fields]').children:[];
 let resolveText,failFinal=true,finalCount=0,duration=60,audioCalls=0;
 const final={summary:[],questions:[],contradictions:[],clinical_items:[],references:[],unavailable:[],notice:'Limited'};
 const fetch=async(url,options={})=>{
  calls.push({url,options});let body;
  if(url.includes('capabilities'))body={ok:true,enabled:true};
  else if(url.endsWith('/text')){await new Promise(r=>resolveText=r);body={ok:true,revision:'a'.repeat(64),review:{transcript:'Soğuk içemiyorum.',fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}},teeth:[],communication:[{quote:'Korkuyorum.',observation:'Korku beyanı',suggestion:'Açıkla'}],follow_up_questions:[]}}}
  else if(url.endsWith('/audio')){audioCalls++;const bytes=new Uint8Array(await options.body.arrayBuffer());const size=new DataView(bytes.buffer).getUint32(0,false);assert.deepEqual(JSON.parse(new TextDecoder().decode(bytes.slice(4,4+size))).fields,{});assert.equal(bytes.length-4-size,500);body={ok:true,revision:'a'.repeat(64),review:{transcript:'Soğuk içemiyorum.',fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}},teeth:[]}}}
  else if(url.endsWith('/finalize')){finalCount++;body=failFinal?{ok:false,error:'Synthetic final failure'}:{ok:true,revision:'a'.repeat(64),final}}
  else if(url.endsWith('/apply'))body={ok:true,patient_url:'/patients/1'};
  else throw Error('Unexpected endpoint');
  return {ok:body.ok,json:async()=>body};
 };
 const box={document:{getElementById:()=>root,createElement:t=>new El(t),createTextNode:text=>({text})},window:{addEventListener:(n,fn)=>events[n]=fn},fetch,navigator:{},location:{hash:'',assign(){}},CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail}},crypto:require('node:crypto').webcrypto,TextEncoder,TextDecoder,DataView,URL:{createObjectURL:()=> 'blob:synthetic',revokeObjectURL(){}},Audio:class{get duration(){return duration}set src(value){queueMicrotask(()=>this.onloadedmetadata?.())}removeAttribute(){}load(){}},AbortController,Uint8Array,Blob,btoa,setInterval,clearInterval,setTimeout,clearTimeout,confirm:()=>true};
 vm.runInNewContext(fs.readFileSync('app/static/voice-finish-draft.js','utf8'),box);
 vm.runInNewContext(fs.readFileSync('app/static/voice-exam.js','utf8'),box);
 await tick();const input=get('[data-voice-audio-file]');
 const file=new Blob([new Uint8Array(500)],{type:'audio/mpeg'});input.files=[file];
 await input.handlers.change();assert.equal(audioCalls,0,'No upload without consent');
 get('[data-voice-consent]').checked=true;duration=100;input.files=[file];
 await input.handlers.change();assert.equal(audioCalls,0,'Oversized duration must not upload');
 duration=60;input.files=[file];await input.handlers.change();assert.equal(audioCalls,1);
 assert.equal(input.value,'','Clear selected file after processing');
 assert.equal(get('[data-voice-fields]').children.length,1);
 assert.equal(calls.filter(x=>x.url.endsWith('/audio'))[0].options.headers['X-Voice-Mime'],'audio/mpeg');
 assert.equal(calls.filter(x=>x.url.endsWith('/audio'))[0].options.headers['X-Voice-Consent'],'yes');
 events.pagehide();console.log('Audio import: consent, duration, binary context packet, extraction and cleanup passed.');
})().catch(e=>{console.error(e);process.exitCode=1});

