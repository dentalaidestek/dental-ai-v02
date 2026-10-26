// Execute the actual browser controller with a small DOM harness. No real PHI/provider.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
class El{
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.checked=false;this.hidden=false;this.handlers={};this.classList={toggle(){}};this.textContent=''}
 append(...items){this.children.push(...items)} replaceChildren(...items){this.children=items;this.textContent=''}
 dispatchEvent(event){this.handlers[event.type]?.(event)}
 setAttribute(){} addEventListener(name,fn){this.handlers[name]=fn}
 querySelector(tag){for(const child of this.children){if(child?.tag===tag)return child;const next=child?.querySelector?.(tag);if(next)return next}return null}
}
(async()=>{
 const elements=new Map(),events={},calls=[],root=new El();root.dataset.patientId='1';
 const get=selector=>{if(!elements.has(selector))elements.set(selector,new El());return elements.get(selector)};
 root.querySelector=get;
 root.querySelectorAll=selector=>selector==='[data-field-row]'?get('[data-voice-fields]').children:[];
 let n=0;
 const fetch=async(url,options={})=>{
  calls.push({url,options});let body;
  if(url.includes('capabilities'))body={ok:true,enabled:true};
  else if(url.endsWith('/text')){n++;body={ok:true,revision:'a'.repeat(64),review:{transcript:'Muayene bölümü '+n,fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'},...(n===2?{medical_history:{value:'Diyabet beyanı',quote:'Şekerim var.'}}:{})},teeth:[],uncertain:'',communication:[{observation:n===1?'Açıklama ihtiyacı':'Tereddüt',quote:n===1?'Anlamadım.':'Çekiniyorum.',suggestion:'Sadeleştir'}]}}}
  else if(url.endsWith('/finalize'))body={ok:true,revision:'a'.repeat(64),final:{summary:[{field:'chief_complaint',quote:'Soğukta',text:'Soğukta ağrı'}],questions:[],contradictions:[],clinical_items:[],references:[],unavailable:[],notice:'Sınırlı kapsam'}};
  else if(url.endsWith('/apply'))body={ok:true,patient_url:'/patients/1'};
  else throw Error('Unexpected request');
  return {ok:true,json:async()=>body};
 };
 const box={document:{getElementById:()=>root,createElement:tag=>new El(tag),createTextNode:text=>({text})},
  window:{addEventListener:(name,fn)=>events[name]=fn},fetch,navigator:{},location:{hash:'',assign:()=>{}},
  CustomEvent:class{constructor(type,options={}){this.type=type;this.detail=options.detail}},crypto:require('node:crypto').webcrypto,TextEncoder,AbortController,Uint8Array,Blob,btoa,
  setInterval,clearInterval,setTimeout,clearTimeout,confirm:()=>true};
 vm.runInNewContext(fs.readFileSync('app/static/voice-finish-draft.js','utf8'),box);
 vm.runInNewContext(fs.readFileSync('app/static/voice-exam.js','utf8'),box);
 await new Promise(setImmediate);
 get('[data-voice-consent]').checked=true;get('[data-voice-transcript]').value='Özel hayat metni. Soğuk içemiyorum.';
 await get('[data-voice-text]').handlers.click();
 assert.equal(get('[data-voice-fields]').children.length,1);
 assert.equal(get('[data-voice-fields]').children[0].querySelector('input').checked,false);
 get('[data-voice-fields]').children[0].querySelector('textarea').value='Hekimin koruduğu şikâyet';
 root.dispatchEvent({type:'input',target:{closest:()=>true}});
 get('[data-voice-transcript]').value+=' Şekerim var.';
 await get('[data-voice-text]').handlers.click();
 const second=JSON.parse(calls.filter(c=>c.url.endsWith('/text'))[1].options.body);
 assert.equal(second.context.fields.chief_complaint.value,'Hekimin koruduğu şikâyet');
 assert.equal('transcript' in second.context,false);
 assert.equal('communication' in second.context,false);
 assert.equal(get('[data-voice-communication]').children.length,1); // Keep distinct earlier observations through the whole examination.
 get('[data-voice-fields]').children[0].querySelector('input').checked=true;
 get('[data-voice-confirm]').checked=false;
 await get('[data-voice-save]').handlers.click();
 assert.equal(calls.some(c=>c.url.endsWith('/apply')),false,'Cannot save without confirmation');
 await get('[data-voice-finalize]').handlers.click();
 assert.equal(calls.some(c=>c.url.endsWith('/clinical')),false,'No automatic parallel clinical call');
 assert.equal(get('[data-voice-save]').disabled,false);
 get('[data-voice-confirm]').checked=true;
 await get('[data-voice-save]').handlers.click();
 const saved=JSON.parse(calls.find(c=>c.url.endsWith('/apply')).options.body);
 assert.deepEqual(Object.keys(saved.fields),['chief_complaint']);
 assert.equal('transcript' in saved,false);assert.equal('communication' in saved,false);
 assert.equal(get('[data-voice-transcript]').value,'');assert.equal(get('[data-voice-communication]').children.length,0);
 assert.equal(get('[data-voice-consent]').checked,false);
 get('[data-voice-transcript]').value='Temporary sensitive input';events.pagehide();
 assert.equal(get('[data-voice-transcript]').value,'');
 console.log('Browser controller: final review gate, cumulative context, explicit selection, minimal save and cleanup passed.');
})().catch(error=>{console.error(error);process.exitCode=1});


