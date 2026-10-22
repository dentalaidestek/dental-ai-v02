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
 let resolveText,failFinal=true,finalCount=0,textCount=0;
 const final={summary:[],questions:[],contradictions:[],clinical_items:[],references:[],unavailable:[],notice:'Limited'};
 const fetch=async(url,options={})=>{
  calls.push({url,options});let body;
  if(url.includes('capabilities'))body={ok:true,enabled:true};
  else if(url.endsWith('/text')){textCount++;if(textCount===1)return {ok:false,json:async()=>({ok:false,error:'Synthetic extraction failure'})};body={ok:true,revision:'a'.repeat(64),review:{transcript:'Soğuk içemiyorum.',fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}},teeth:[],communication:[{quote:'Korkuyorum.',observation:'Korku beyanı',suggestion:'Açıkla'}],follow_up_questions:[]}}}
  else if(url.endsWith('/finalize')){finalCount++;body=failFinal?{ok:false,error:'Synthetic final failure'}:{ok:true,revision:'a'.repeat(64),final}}
  else if(url.endsWith('/apply'))body={ok:true,patient_url:'/patients/1'};
  else throw Error('Unexpected endpoint');
  return {ok:body.ok,json:async()=>body};
 };
 const box={document:{getElementById:()=>root,createElement:t=>new El(t),createTextNode:text=>({text})},window:{addEventListener:(n,fn)=>events[n]=fn},fetch,navigator:{},location:{hash:'',assign(){}},CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail}},crypto:require('node:crypto').webcrypto,TextEncoder,AbortController,Uint8Array,Blob,btoa,setInterval,clearInterval,setTimeout,clearTimeout,confirm:()=>true};
 vm.runInNewContext(fs.readFileSync('app/static/voice-exam.js','utf8'),box);
 await tick();get('[data-voice-consent]').checked=true;
 root.dispatchEvent({type:'voice-live-state',detail:{active:true}});
 let stops=0;root.addEventListener('voice-live-stop',()=>stops++);
 root.dispatchEvent({type:'voice-live-segment',detail:{text:'İlk işlenemeyen bölüm.'}});await tick();await tick();
 assert.equal(stops,0,'One extraction failure must not stop the microphone');
 assert.equal(get('[data-voice-transcript]').value,'İlk işlenemeyen bölüm.');
 root.dispatchEvent({type:'voice-live-segment',detail:{text:'Yeni bölüm.'}});await tick();await tick();
 assert.equal(textCount,2,'No automatic paid retry of failed text');
 assert.equal(get('[data-voice-transcript]').value,'İlk işlenemeyen bölüm.','Later success must preserve failed speech');
 root.dispatchEvent({type:'voice-live-state',detail:{active:false}});
 assert.equal(get('[data-voice-finalize]').disabled,true,'Unprocessed speech blocks finalization');
 await get('[data-voice-text]').handlers.click();assert.equal(textCount,3);
 assert.equal(get('[data-voice-finalize]').disabled,false,'Explicit retry resolves pending speech');
 console.log('Extraction recovery: continued listening, preserved failed text, explicit retry and final gate passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
