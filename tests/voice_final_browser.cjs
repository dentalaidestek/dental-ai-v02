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
 let resolveText,failFinal=true,finalCount=0;
 const final={summary:[],questions:[],contradictions:[],clinical_items:[],references:[],unavailable:[],notice:'Limited'};
 const fetch=async(url,options={})=>{
  calls.push({url,options});let body;
  if(url.includes('capabilities'))body={ok:true,enabled:true};
  else if(url.endsWith('/text')){await new Promise(r=>resolveText=r);body={ok:true,revision:'a'.repeat(64),review:{transcript:'Soğuk içemiyorum.',fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}},teeth:[],communication:[{quote:'Korkuyorum.',observation:'Korku beyanı',suggestion:'Açıkla'}],follow_up_questions:[]}}}
  else if(url.endsWith('/finalize')){finalCount++;body=failFinal?{ok:false,error:'Synthetic final failure'}:{ok:true,revision:'a'.repeat(64),final}}
  else if(url.endsWith('/apply'))body={ok:true,patient_url:'/patients/1'};
  else throw Error('Unexpected endpoint');
  return {ok:body.ok,json:async()=>body};
 };
 const box={document:{getElementById:()=>root,createElement:t=>new El(t),createTextNode:text=>({text})},window:{addEventListener:(n,fn)=>events[n]=fn},fetch,navigator:{},location:{hash:'',assign(){}},CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail}},crypto:require('node:crypto').webcrypto,TextEncoder,AbortController,Uint8Array,Blob,btoa,setInterval,clearInterval,setTimeout,clearTimeout,confirm:()=>true};
 vm.runInNewContext(fs.readFileSync('app/static/voice-exam.js','utf8'),box);
 await tick();get('[data-voice-consent]').checked=true;
 root.dispatchEvent({type:'voice-live-segment',detail:{text:'Soğuk içemiyorum.'}});
 root.dispatchEvent({type:'voice-live-ended',detail:{finished:true,flushed:true}});
 assert.equal(finalCount,0,'Final must wait for pending extraction');
 resolveText();await tick();await tick();
 assert.equal(calls.some(c=>c.url.endsWith('/clinical')),false,'Finish must be the only automatic whole-review call');
 assert.equal(finalCount,1);assert.equal(get('[data-voice-save]').disabled,true,'Failed final must block save');
 await tick();assert.equal(finalCount,1,'No automatic paid retry');
 failFinal=false;await get('[data-voice-finalize]').handlers.click();
 assert.equal(get('[data-voice-save]').disabled,false);
 assert.equal(get('[data-voice-stage]').textContent,'Hekim onayı ve kayıt');
 const cachedCount=finalCount;await get('[data-voice-finalize]').handlers.click();assert.equal(finalCount,cachedCount,'Same final review must not be paid twice');
 const field=get('[data-voice-fields]').children[0].querySelector('textarea');field.value='Hekimin düzeltmesi';
 root.dispatchEvent({type:'input',target:{closest:()=>true}});
 assert.equal(get('[data-voice-save]').disabled,true,'Edited fields invalidate completed review');
 await get('[data-voice-finalize]').handlers.click();
 assert.equal(get('[data-voice-save]').disabled,false);
 get('[data-voice-transcript]').value='İşlenmemiş yeni bölüm';get('[data-voice-transcript]').handlers.input();
 await get('[data-voice-finalize]').handlers.click();assert.equal(finalCount,3,'Unprocessed text blocks final');
 events.pagehide();assert.equal(get('[data-voice-transcript]').value,'');assert.equal(get('[data-voice-final-results]').children.length,0);
 assert.equal(get('[data-voice-communication]').children.length,0);
 console.log('Final lifecycle: extraction drain, failure/retry, edit invalidation, unprocessed text and private cleanup passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
