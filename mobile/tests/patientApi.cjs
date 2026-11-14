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

test('clinical media upload handles null HTTP error body as ApiError',async()=>{
 const {uploadPatientMedia,ApiError}=require('../src/api.ts');
 const original=global.fetch;
 global.fetch=async()=>({ok:false,status:503,text:async()=>'null'});
 try{
  await assert.rejects(()=>uploadPatientMedia('token',1,{uri:'file:///image.jpg',name:'image.jpg',type:'image/jpeg'}),err=>err instanceof ApiError&&err.status===503&&err.message==='Görüntü yüklenemedi.');
 }finally{global.fetch=original}
});

test('interrupted clinical upload warns to check gallery before retrying',async()=>{
 const {uploadPatientMedia,ApiError}=require('../src/api.ts');
 const original=global.fetch;
 const file={uri:'file:///image.jpg',name:'image.jpg',type:'image/jpeg'};
 try{
  for(const fetchFailure of [()=>Promise.reject(new TypeError('Network request failed')),()=>Promise.resolve({ok:true,status:200,text:async()=>{throw new TypeError('stream interrupted')}})]){
   global.fetch=fetchFailure;
   await assert.rejects(()=>uploadPatientMedia('token',1,file),err=>err instanceof ApiError&&err.status===503&&/galerisini kontrol edin/.test(err.message));
  }
 }finally{global.fetch=original}
});

test('successful API responses reject empty and array payloads before patient rendering',async()=>{
 const {getPatients,ApiError}=require('../src/api.ts');
 const original=global.fetch;
 try{
  for(const raw of ['', '  ', '[]', 'null', '42']){
   global.fetch=async()=>({ok:true,status:200,text:async()=>raw});
   await assert.rejects(()=>getPatients('token'),err=>err instanceof ApiError&&err.status===502);
  }
 }finally{global.fetch=original}
});

test('tooth chart writes reject invalid patient and FDI identifiers before fetch',async()=>{
 const {updateTooth,updateToothSurface}=require('../src/api.ts');
 const original=global.fetch;
 global.fetch=()=>{throw Error('unexpected network call')};
 try{
  for(const tooth of ['19','49','56','89','../11','11?x=1','']){
   assert.throws(()=>updateTooth('token',1,tooth,{status:'CARIES'}),/Geçersiz FDI/);
   assert.throws(()=>updateToothSurface('token',1,tooth,'MESIAL',{status:'CARIES'}),/Geçersiz FDI/);
  }
  for(const patientId of [0,-1,1.5,Number.NaN]){
   assert.throws(()=>updateTooth('token',patientId,'11',{status:'CARIES'}),/Geçersiz hasta/);
   assert.throws(()=>updateToothSurface('token',patientId,'11','MESIAL',{status:'CARIES'}),/Geçersiz hasta/);
  }
 }finally{global.fetch=original}
});
test('tooth chart writes preserve valid primary and permanent FDI routes',async()=>{
 const {updateTooth,updateToothSurface}=require('../src/api.ts');
 const original=global.fetch;
 const urls=[];
 global.fetch=async url=>{urls.push(url);return reply({ok:true})};
 try{
  await updateTooth('token',8,'18',{status:'HEALTHY'});
  await updateToothSurface('token',8,'85','LINGUAL',{status:'CARIES'});
  assert.match(urls[0],/\/patients\/8\/teeth\/18$/);
  assert.match(urls[1],/\/patients\/8\/teeth\/85\/surfaces\/LINGUAL$/);
 }finally{global.fetch=original}
});

test('tooth chart rejects invalid clinical status and surface values without network writes',async()=>{
 const {updateTooth,updateToothSurface}=require('../src/api.ts');
 const original=global.fetch;
 global.fetch=()=>{throw Error('unexpected clinical network write')};
 try{
  assert.throws(()=>updateTooth('token',8,'11',{status:'UNKNOWN'}),/Geçersiz diş durumu/);
  assert.throws(()=>updateTooth('token',8,'11',{status:'CARIES',surface:'../11'}),/Geçersiz diş yüzeyi/);
  assert.throws(()=>updateTooth('token',8,'11',{status:'CARIES',surfaces:['MESIAL','../11']}),/Geçersiz diş yüzeyi/);
  assert.throws(()=>updateToothSurface('token',8,'11','../11',{status:'CARIES'}),/Geçersiz diş yüzeyi/);
  assert.throws(()=>updateToothSurface('token',8,'11','MESIAL',{status:'UNKNOWN'}),/Geçersiz diş durumu/);
 }finally{global.fetch=original}
});
