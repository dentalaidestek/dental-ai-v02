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

test('patient profile rejects malformed nested clinical collections before tooth chart rendering',async()=>{
 const original=global.fetch;
 const valid={patient:{id:8},teeth:[],surfaces:[],treatments:[],media:[]};
 const malformed=[
  {...valid,teeth:[null]},
  {...valid,teeth:[{tooth_number:'11',status:null}]},
  {...valid,surfaces:[{tooth_number:'11',surface:null,status:'CARIES'}]},
  {...valid,treatments:[{id:0,treatment_name:'Dolgu'}]},
  {...valid,media:[{id:2,original_filename:null}]},
 ];
 try{
  for(const body of malformed){
   global.fetch=async()=>reply(body);
   await assert.rejects(()=>getPatient('token',8),/beklenmeyen profil/);
  }
  global.fetch=async()=>reply({...valid,teeth:[{id:1,tooth_number:'11',status:'HEALTHY'}],surfaces:[{id:2,tooth_number:'11',surface:'MESIAL',status:'CARIES'}],treatments:[{id:3,treatment_name:'Dolgu'}],media:[{id:4,original_filename:'image.jpg'}]});
  assert.equal((await getPatient('token',8)).surfaces[0].surface,'MESIAL');
 }finally{global.fetch=original}
});

test('clinical media upload rejects invalid FDI tooth numbers before network access',async()=>{
 const {uploadPatientMedia}=require('../src/api.ts');
 const original=global.fetch;
 const file={uri:'file:///image.jpg',name:'image.jpg',type:'image/jpeg'};
 global.fetch=()=>{throw Error('unexpected network call')};
 try{
  for(const tooth of ['19','49','56','66','89','00','99']){
   await assert.rejects(()=>uploadPatientMedia('token',1,file,tooth),/Geçersiz FDI/);
  }
 }finally{global.fetch=original}
});
test('clinical media upload accepts primary and permanent FDI tooth numbers',async()=>{
 const {uploadPatientMedia}=require('../src/api.ts');
 const original=global.fetch;
 const file={uri:'file:///image.jpg',name:'image.jpg',type:'image/jpeg'};
 let calls=0;
 global.fetch=async()=>{calls++;return reply({media:{id:calls,original_filename:'image.jpg',media_type:'PHOTO'}})};
 try{
  for(const tooth of ['11','18','48','51','65','75','85'])
   assert.ok((await uploadPatientMedia('token',1,file,tooth)).media.id>0);
  assert.equal(calls,7);
 }finally{global.fetch=original}
});

test('API handles null and malformed error bodies without leaking raw exceptions',async()=>{
 const {getPatients,ApiError}=require('../src/api.ts');
 const original=global.fetch;
 try{
  for(const body of ['null','[]','{"detail":{"message":42}}','<html>gateway error</html>']){
   global.fetch=async()=>({ok:false,status:503,text:async()=>body});
   await assert.rejects(()=>getPatients('token'),err=>err instanceof ApiError&&err.status===503&&err.message==='İstek başarısız.');
  }
  global.fetch=async()=>({ok:false,status:403,text:async()=>JSON.stringify({detail:'Erişim reddedildi'})});
  await assert.rejects(()=>getPatients('token'),err=>err instanceof ApiError&&err.status===403&&err.message==='Erişim reddedildi');
 }finally{global.fetch=original}
});
