const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
test('private history snapshots stay hidden until server revalidation',()=>{
 const handlers={};let reloads=0;
 const document={documentElement:{style:{visibility:''}},addEventListener(){}};
 vm.runInNewContext(fs.readFileSync('app/static/account-history.js','utf8'),{
  document,window:{addEventListener:(name,fn)=>handlers[name]=fn,location:{reload(){reloads++}}}
 });
 handlers.pageshow({persisted:false});assert.equal(reloads,0);
 handlers.pagehide();assert.equal(document.documentElement.style.visibility,'hidden');
 handlers.pageshow({persisted:true});assert.equal(reloads,1);
 assert.equal(document.documentElement.style.visibility,'hidden');
 handlers.pageshow({persisted:false});assert.equal(document.documentElement.style.visibility,'');
});
test('same-origin logout stops private writers before clearing scoped drafts',()=>{
 const handlers={},events=[],storage={'dai:voice-draft:v1:7:1':'voice','dai-social-v1:7':'social',theme:'dark'};
 Object.defineProperty(storage,'removeItem',{value:key=>{assert.deepEqual(events,['dai:session-ending']);delete storage[key]}});
 class Form{constructor(action){this.action=action}}
 vm.runInNewContext(fs.readFileSync('app/static/account-history.js','utf8'),{
  document:{addEventListener:(name,fn,capture)=>{handlers[name]=fn;assert.equal(capture,true)}},
  window:{addEventListener(){},dispatchEvent:event=>events.push(event.type)},
  location:{href:'https://dental.test/account',origin:'https://dental.test'},URL,HTMLFormElement:Form,
  CustomEvent:class{constructor(type){this.type=type}},sessionStorage:storage
 });
 for(const target of [{},new Form('https://other.test/logout'),new Form('https://dental.test/account')])handlers.submit({target});
 assert.deepEqual(events,[]);assert.equal(Object.keys(storage).length,3,'Other form submissions retain drafts');
 handlers.submit({target:new Form('https://dental.test/logout')});
 assert.deepEqual(events,['dai:session-ending']);assert.deepEqual(Object.keys(storage),['theme']);assert.equal(storage.theme,'dark');
});
test('logout still stops private writers when browser storage is unavailable',()=>{
 const handlers={},events=[];class Form{constructor(){this.action='https://dental.test/logout'}}
 vm.runInNewContext(fs.readFileSync('app/static/account-history.js','utf8'),{
  document:{addEventListener:(name,fn)=>handlers[name]=fn},window:{addEventListener(){},dispatchEvent:event=>events.push(event.type)},
  location:{href:'https://dental.test/account',origin:'https://dental.test'},URL,HTMLFormElement:Form,
  CustomEvent:class{constructor(type){this.type=type}},sessionStorage:new Proxy({},{ownKeys(){throw Error('Storage blocked')}})
 });
 assert.doesNotThrow(()=>handlers.submit({target:new Form()}));assert.deepEqual(events,['dai:session-ending']);
});
