const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');

function moduleFor(store,uuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'){
 const exports={};let generated=0;
 const source=fs.readFileSync(require.resolve('../src/programIntent.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>name==='expo-crypto'?{randomUUID:()=>{generated++;return uuid}}:name==='expo-secure-store'?{
  getItemAsync:async key=>store.has(key)?store.get(key):null,
  setItemAsync:async(key,value)=>{store.set(key,value)},
  deleteItemAsync:async key=>{store.delete(key)}
 }:{}});
 return {api:exports,generated:()=>generated};
}

test('Program request keys are random, persisted before use and scoped by account/patient',async()=>{
 const store=new Map(),m=moduleFor(store);
 const first=await m.api.getOrCreateProgramRequestKey(7,42);
 assert.equal(first,'aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa');
 assert.equal(store.get('dai.program.create.v1.7.42'),first);
 assert.equal(await m.api.loadProgramRequestKey(7,42),first);
 assert.equal(await m.api.loadProgramRequestKey(8,42),null);
 assert.equal(await m.api.loadProgramRequestKey(7,43),null);
 assert.equal(m.generated(),1);
});

test('restored Program request key is reused instead of rotated after process death',async()=>{
 const store=new Map([['dai.program.create.v1.7.0','existing_request_key_123456']]);
 const m=moduleFor(store);
 assert.equal(await m.api.getOrCreateProgramRequestKey(7), 'existing_request_key_123456');
 assert.equal(m.generated(),0);
});

test('corrupt SecureStore intent fails closed and never creates a replacement key',async()=>{
 const store=new Map([['dai.program.create.v1.7.42','not a valid key']]);
 const m=moduleFor(store);
 await assert.rejects(()=>m.api.getOrCreateProgramRequestKey(7,42),/bozuk/);
 assert.equal(m.generated(),0);
});

test('clear removes only the matching request key and preserves a newer intent',async()=>{
 const store=new Map([['dai.program.create.v1.7.42','newer_request_key_123456']]);
 const m=moduleFor(store);
 await m.api.clearProgramRequestKey(7,42,'older_request_key_123456');
 assert.equal(store.get('dai.program.create.v1.7.42'),'newer_request_key_123456');
 await m.api.clearProgramRequestKey(7,42,'newer_request_key_123456');
 assert.equal(store.has('dai.program.create.v1.7.42'),false);
});

test('invalid account or patient scope is rejected before SecureStore access',async()=>{
 const m=moduleFor(new Map());
 await assert.rejects(()=>m.api.loadProgramRequestKey(0,42),/kapsam/);
 await assert.rejects(()=>m.api.loadProgramRequestKey(7,-1),/kapsam/);
});
