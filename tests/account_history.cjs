const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
test('private history snapshots stay hidden until server revalidation',()=>{
 const handlers={};let reloads=0;
 const document={documentElement:{style:{visibility:''}}};
 vm.runInNewContext(fs.readFileSync('app/static/account-history.js','utf8'),{
  document,window:{addEventListener:(name,fn)=>handlers[name]=fn,location:{reload(){reloads++}}}
 });
 handlers.pageshow({persisted:false});assert.equal(reloads,0);
 handlers.pagehide();assert.equal(document.documentElement.style.visibility,'hidden');
 handlers.pageshow({persisted:true});assert.equal(reloads,1);
 assert.equal(document.documentElement.style.visibility,'hidden');
 handlers.pageshow({persisted:false});assert.equal(document.documentElement.style.visibility,'');
});
