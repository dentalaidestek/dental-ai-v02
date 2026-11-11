const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const {getPatients,getPatient}=require('../src/api.ts');
const reply=body=>({ok:true,status:200,text:async()=>JSON.stringify(body)});
test('patient list rejects malformed or duplicated clinical records',async()=>{
 const original=global.fetch;
 try{
  for(const body of [{items:[{id:3},{id:3}],total:2},{items:[null],total:1},{items:[{id:4}],total:0},{items:[],total:100}]){
   global.fetch=async()=>reply(body);
   await assert.rejects(()=>getPatients('token'),/geçersiz liste/);
  }
 }finally{global.fetch=original}
});
test('patient list accepts offset pagination without exposing invalid cursors',async()=>{
 const original=global.fetch;
 global.fetch=async url=>{assert.match(url,/offset=30/);return reply({items:[{id:99}],total:31})};
 try{assert.equal((await getPatients('token','',30)).items[0].id,99)}finally{global.fetch=original}
});
test('patient profile rejects a different patient returned by the server',async()=>{
 const original=global.fetch;
 global.fetch=async()=>reply({patient:{id:7},teeth:[],surfaces:[],treatments:[],media:[]});
 try{await assert.rejects(()=>getPatient('token',8),/beklenmeyen profil/)}finally{global.fetch=original}
});
test('patient profile rejects incomplete clinical collections',async()=>{
 const original=global.fetch;
 global.fetch=async()=>reply({patient:{id:8},teeth:[],surfaces:[],treatments:[]});
 try{await assert.rejects(()=>getPatient('token',8),/beklenmeyen profil/)}finally{global.fetch=original}
});
test('invalid patient identifiers do not trigger network requests',async()=>{
 const original=global.fetch;
 global.fetch=()=>{throw Error('unexpected network call')};
 try{
  await assert.rejects(()=>getPatient('token',0),/Geçersiz hasta/);
  await assert.rejects(()=>getPatients('token','',-1),/Geçersiz hasta sayfası/);
 }finally{global.fetch=original}
});
