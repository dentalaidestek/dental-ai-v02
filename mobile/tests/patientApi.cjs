const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const {getPatients,getPatient,getPatientTreatments,getToothTreatments,getPatientMediaUpload}=require('../src/api.ts');
const reply=body=>({ok:true,status:200,text:async()=>JSON.stringify(body)});
test('duplicate patient conflicts preserve only a valid existing record id',async()=>{
 const {createPatient,ApiError}=require('../src/api.ts');const original=global.fetch;
 try{
  for(const id of [12,0,-1,'12',null]){
   global.fetch=async()=>({ok:false,status:409,text:async()=>JSON.stringify({detail:{message:'Benzer hasta',patient_id:id}})});
   await assert.rejects(()=>createPatient('token',{first_name:'Test',last_name:'Hasta'}),e=>e instanceof ApiError&&e.duplicatePatientId===(id===12?12:undefined));
  }
 }finally{global.fetch=original}
});
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
  {...valid,teeth:[{tooth_number:'19',status:'HEALTHY'}]},
  {...valid,teeth:[{tooth_number:'11',status:'UNRECOGNIZED'}]},
  {...valid,surfaces:[{tooth_number:'89',surface:'MESIAL',status:'CARIES'}]},
  {...valid,surfaces:[{tooth_number:'11',surface:'INVALID',status:'CARIES'}]},
  {...valid,surfaces:[{tooth_number:'11',surface:'MESIAL',status:'INVALID'}]},
  {...valid,surfaces:[{tooth_number:'11',surface:null,status:'CARIES'}]},
  {...valid,treatments:[{id:0,treatment_name:'Dolgu'}]},
  {...valid,media:[{id:3,original_filename:'x.jpg',tooth_number:'89'}]},
  {...valid,media:[{id:2,original_filename:null}]},
 ];
 try{
  for(const body of malformed){
   global.fetch=async()=>reply(body);
   await assert.rejects(()=>getPatient('token',8),/beklenmeyen profil/);
  }
  global.fetch=async()=>reply({...valid,teeth:[{id:1,tooth_number:'11',status:'HEALTHY'}],surfaces:[{id:2,tooth_number:'11',surface:'MESIAL',status:'CARIES'}],treatments:[{id:3,treatment_name:'Dolgu',edit_revision:'a'.repeat(64),created_at:'2026-11-18T10:00:00'}],media:[{id:4,original_filename:'image.jpg'}]});
  assert.equal((await getPatient('token',8)).surfaces[0].surface,'MESIAL');
  // Web-created rows may carry free-text tooth numbers and unusable
  // revisions: the screen must degrade them, not fail entirely.
  global.fetch=async()=>reply({...valid,treatments:[{id:5,treatment_name:'Web kaydı',tooth_number:'19',edit_revision:'nope',created_at:'2026-11-18T10:00:00'}]});
  const degraded=await getPatient('token',8);
  assert.equal(degraded.treatments[0].tooth_number,null);
  assert.equal(degraded.treatments[0].edit_revision,'');
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

test('patient search enforces FastAPI 100-character query limit before network access',async()=>{
 const original=global.fetch;
 let calls=0;
 global.fetch=async url=>{calls++;assert.match(url,/q=/);return reply({items:[],total:0})};
 try{
  await assert.rejects(()=>getPatients('token','a'.repeat(101)),/100 karakter/);
  await assert.rejects(()=>getPatients('token',null),/100 karakter/);
  assert.equal(calls,0);
  await getPatients('token','a'.repeat(100));
  assert.equal(calls,1);
 }finally{global.fetch=original}
});

test('bearer-auth patient and notification requests never attach ambient web cookies',async()=>{
 const {getNotifications}=require('../src/modernApi.ts');
 const original=global.fetch;
 const calls=[];
 global.fetch=async(url,init)=>{
  calls.push({url,init});
  if(String(url).endsWith('/notifications'))return reply({items:[],unread:0});
  return reply({items:[],total:0});
 };
 try{
  await getPatients('secret');
  await getNotifications('secret');
  assert.equal(calls.length,2);
  for(const {init} of calls){
   assert.equal(init.credentials,'omit');
   assert.equal(init.headers.Authorization,'Bearer secret');
  }
 }finally{global.fetch=original}
});

test('treatment writes reject invalid patient, treatment and FDI identifiers before network access',()=>{
 const {createTreatment,updateTreatment}=require('../src/api.ts'),requestKey='synthetic-treatment-request-0001',revision='a'.repeat(64);
 const original=global.fetch;
 global.fetch=()=>{throw Error('unexpected network call')};
 try{
  for(const id of [0,-1,1.5,Number.NaN]){
   assert.throws(()=>createTreatment('token',id,{treatment_name:'Dolgu'},requestKey),/Geçersiz hasta/);
  }
  for(const id of [0,-2,1.5]){
   assert.throws(()=>updateTreatment('token',1,id,{treatment_name:'Dolgu'},requestKey,revision),/Geçersiz hasta veya tedavi/);
  }
  for(const tooth of ['19','49','56','89','../11']){
   assert.throws(()=>createTreatment('token',1,{treatment_name:'Dolgu',tooth_number:tooth},requestKey),/Geçersiz FDI/);
  }
  assert.throws(()=>createTreatment('token',1,{treatment_name:'   '},requestKey),/Tedavi adı/);
 }finally{global.fetch=original}
});
test('treatment writes preserve valid primary and permanent tooth routes',async()=>{
 const {createTreatment,updateTreatment}=require('../src/api.ts'),requestKey='synthetic-treatment-request-0002',revision='a'.repeat(64);
 const original=global.fetch;const urls=[];
 global.fetch=async url=>{urls.push(url);return reply({ok:true,treatment_id:7,edit_revision:'b'.repeat(64),replayed:false})};
 try{
  await createTreatment('token',4,{treatment_name:'Dolgu',tooth_number:'36'},requestKey);
  await updateTreatment('token',4,7,{treatment_name:'Kron',tooth_number:'85'},requestKey,revision);
  assert.match(urls[0],/\/patients\/4\/treatments$/);
  assert.match(urls[1],/\/patients\/4\/treatments\/7$/);
 }finally{global.fetch=original}
});

test('treatment date and name validation matches backend clinical contract',async()=>{
 const {createTreatment}=require('../src/api.ts'),requestKey='synthetic-treatment-request-0003';
 const original=global.fetch;const bodies=[];
 global.fetch=async (_url,init)=>{bodies.push(JSON.parse(init.body));return reply({ok:true,treatment_id:9,edit_revision:'c'.repeat(64),replayed:false})};
 try{
  for(const date of ['2026-02-30','2025-02-29','2026-13-01','2026-00-10','2026-12-00','2026/11/14','not-a-date']){
   assert.throws(()=>createTreatment('token',1,{treatment_name:'Dolgu',treatment_date:date},requestKey),/Tedavi tarihi/);
  }
  assert.throws(()=>createTreatment('token',1,{treatment_name:'x'.repeat(201)},requestKey),/200 karakter/);
  assert.equal(bodies.length,0);
  await createTreatment('token',1,{treatment_name:'Dolgu',treatment_date:'2024-02-29'},requestKey);
  await createTreatment('token',1,{treatment_name:'Kanal tedavisi',treatment_date:''},requestKey);
  assert.equal(bodies.length,2);
 }finally{global.fetch=original}
});


test('patient profile accepts only well-formed optional edit revisions',async()=>{
 const revision='a'.repeat(64),original=global.fetch;
 try{
  global.fetch=async()=>reply({patient:{id:8},teeth:[],surfaces:[],treatments:[],media:[],edit_revision:revision});
  assert.equal((await getPatient('token',8)).edit_revision,revision);
  global.fetch=async()=>reply({patient:{id:8},teeth:[],surfaces:[],treatments:[],media:[],edit_revision:'not-a-revision'});
  await assert.rejects(()=>getPatient('token',8),/beklenmeyen profil/);
 }finally{global.fetch=original}
});

test('native patient edit sends the loaded revision and rejects malformed revisions before fetch',async()=>{
 const {editPatient}=require('../src/api.ts'),revision='b'.repeat(64),original=global.fetch;
 let body;
 global.fetch=async(_url,init)=>{body=JSON.parse(init.body);return reply({ok:true,patient:{id:8},edit_revision:'c'.repeat(64)})};
 try{
  await editPatient('token',8,{first_name:'Synthetic',last_name:'Patient',expected_revision:revision});
  assert.equal(body.expected_revision,revision);
  global.fetch=async()=>reply({ok:true,patient:{id:8},edit_revision:'bad'});
  await assert.rejects(()=>editPatient('token',8,{first_name:'Synthetic',last_name:'Patient',expected_revision:revision}),/Hasta güncelleme yanıtı doğrulanamadı/);
  global.fetch=()=>{throw Error('unexpected network call')};
  await assert.rejects(()=>editPatient('token',8,{first_name:'Synthetic',last_name:'Patient',expected_revision:'bad'}),/kayıt sürümü/);
 }finally{global.fetch=original}
});


test('patient detail accepts only the bounded first treatment page and a valid continuation cursor',async()=>{
 const original=global.fetch,cursor='A'.repeat(32);
 const base={patient:{id:8},teeth:[],surfaces:[],treatments:[],media:[]};
 try{
  global.fetch=async()=>reply({...base,treatments:[{id:1,treatment_name:'One',edit_revision:'1'.repeat(64),created_at:'2026-11-18T10:00:00'},{id:2,treatment_name:'Two',edit_revision:'2'.repeat(64),created_at:'2026-11-17T10:00:00'},{id:3,treatment_name:'Three',edit_revision:'3'.repeat(64),created_at:'2026-11-16T10:00:00'}],treatments_next_cursor:cursor});
  assert.equal((await getPatient('token',8)).treatments_next_cursor,cursor);
  global.fetch=async()=>reply({...base,treatments:[{id:1,treatment_name:'One',edit_revision:'1'.repeat(64),created_at:'2026-11-18T10:00:00'},{id:2,treatment_name:'Two',edit_revision:'2'.repeat(64),created_at:'2026-11-17T10:00:00'},{id:3,treatment_name:'Three',edit_revision:'3'.repeat(64),created_at:'2026-11-16T10:00:00'},{id:4,treatment_name:'Four',edit_revision:'4'.repeat(64),created_at:'2026-11-15T10:00:00'}]});
  // Overlong embedded pages are truncated to the bounded first page.
  assert.equal((await getPatient('token',8)).treatments.length,3);
  global.fetch=async()=>reply({...base,treatments_next_cursor:'bad cursor'});
  await assert.rejects(()=>getPatient('token',8),/beklenmeyen profil/);
 }finally{global.fetch=original}
});

test('treatment history pages use the patient-scoped opaque cursor and validate every record',async()=>{
 const original=global.fetch,cursor='B'.repeat(32),next='C'.repeat(32),calls=[];
 global.fetch=async(url,init)=>{
  calls.push({url,init});
  return reply({items:[{id:7,tooth_number:'36',treatment_name:'Dolgu',edit_revision:'d'.repeat(64),analysis_id:null,created_at:'2026-11-18T10:00:00'}],next_cursor:null});
 };
 try{
  const page=await getPatientTreatments('secret',8,cursor);
  assert.equal(page.items[0].id,7);
  assert.match(calls[0].url,new RegExp('/patients/8/treatments\\?cursor='+cursor));
  assert.equal(calls[0].init.credentials,'omit');
  assert.equal(calls[0].init.headers.Authorization,'Bearer secret');
  global.fetch=async()=>reply({items:Array.from({length:20},(_,i)=>({id:i+1,treatment_name:'T'+i,edit_revision:'e'.repeat(64),created_at:'2026-11-18T10:00:00'})),next_cursor:next});
  assert.equal((await getPatientTreatments('token',8,cursor)).next_cursor,next);
 }finally{global.fetch=original}
});

test('invalid patient ids and cursors are rejected before treatment-history network access',async()=>{
 const original=global.fetch;let calls=0;global.fetch=()=>{calls++;throw Error('unexpected network call')};
 try{
  await assert.rejects(()=>getPatientTreatments('token',0,'A'.repeat(32)),/Geçersiz hasta/);
  await assert.rejects(()=>getPatientTreatments('token',8,'bad'),/imleci geçersiz/);
  assert.equal(calls,0);
 }finally{global.fetch=original}
});

test('malformed, duplicate, cyclic and truncated treatment pages are rejected',async()=>{
 const {ApiError}=require('../src/api.ts'),original=global.fetch,cursor='D'.repeat(32);
 const item=id=>({id,treatment_name:'Synthetic',edit_revision:'f'.repeat(64),created_at:'2026-11-18T10:00:00'});
 const invalid=[
  {items:[item(1),item(1)],next_cursor:null},
  {items:[{...item(1),tooth_number:'89'}],next_cursor:null},
  {items:[{...item(1),edit_revision:'bad'}],next_cursor:null},
  {items:[{id:1,treatment_name:'Missing date',edit_revision:'f'.repeat(64)}],next_cursor:null},
  {items:[item(1)],next_cursor:'invalid cursor'},
  {items:[item(1)],next_cursor:cursor},
  {items:[],next_cursor:'E'.repeat(32)},
  {items:Array.from({length:21},(_,i)=>item(i+1)),next_cursor:null}
 ];
 try{
  for(const body of invalid){
   global.fetch=async()=>reply(body);
   await assert.rejects(()=>getPatientTreatments('token',8,cursor),error=>error instanceof ApiError&&error.status===502);
  }
 }finally{global.fetch=original}
});
test('tooth treatment history uses an FDI-scoped endpoint and validates bounded pages',async()=>{
 const original=global.fetch,cursor='F'.repeat(32),next='G'.repeat(32),calls=[];
 const item=(id,tooth='36')=>({id,tooth_number:tooth,treatment_name:'Synthetic treatment',edit_revision:'a'.repeat(64),analysis_id:null,created_at:'2026-11-18T10:00:00'});
 global.fetch=async(url,init)=>{calls.push({url,init});return reply({items:[item(1)],next_cursor:null})};
 try{
  const page=await getToothTreatments('secret',8,'36');
  assert.equal(page.items[0].tooth_number,'36');
  assert.match(calls[0].url,/\/patients\/8\/teeth\/36\/treatments$/);
  assert.equal(calls[0].init.credentials,'omit');
  assert.equal(calls[0].init.headers.Authorization,'Bearer secret');
  global.fetch=async(url)=>{calls.push({url});return reply({items:Array.from({length:20},(_,i)=>item(i+2)),next_cursor:next})};
  assert.equal((await getToothTreatments('token',8,'36',cursor)).next_cursor,next);
  assert.match(calls[1].url,new RegExp('cursor='+cursor));
 }finally{global.fetch=original}
});

test('tooth treatment history rejects invalid ids, FDI values and cross-tooth records before display',async()=>{
 const {ApiError}=require('../src/api.ts'),original=global.fetch;let calls=0;
 global.fetch=async()=>{calls++;return reply({items:[{id:1,tooth_number:'37',treatment_name:'Wrong tooth',edit_revision:'a'.repeat(64),created_at:'2026-11-18T10:00:00'}],next_cursor:null})};
 try{
  await assert.rejects(()=>getToothTreatments('token',0,'36'),/Geçersiz hasta/);
  await assert.rejects(()=>getToothTreatments('token',8,'19'),/Geçersiz FDI/);
  global.fetch=()=>{calls++;throw Error('unexpected network call')};
  await assert.rejects(()=>getToothTreatments('token',8,'36','bad'),/imleci geçersiz/);
  assert.equal(calls,0);
  global.fetch=async()=>reply({items:[{id:1,tooth_number:'37',treatment_name:'Wrong tooth',edit_revision:'a'.repeat(64),created_at:'2026-11-18T10:00:00'}],next_cursor:null});
  await assert.rejects(()=>getToothTreatments('token',8,'36'),error=>error instanceof ApiError&&error.status===502);
 }finally{global.fetch=original}
});


test('patient profile keeps tooth-chart data opt-in while chart reads request it explicitly',async()=>{
 const original=global.fetch,urls=[];
 const body={patient:{id:8},edit_revision:'a'.repeat(64),teeth:[],surfaces:[],treatments:[],media:[]};
 global.fetch=async url=>{urls.push(String(url));return reply(body)};
 try{
  const profile=await getPatient('token',8);
  assert.deepEqual(profile.teeth,[]);
  await getPatient('token',8,true);
  await getPatient('token',8,false,true);
  assert.equal(urls.length,3);
  assert.match(urls[0],/\/patients\/8\?include_chart=false&include_media=false$/,'ordinary profile reads must omit unused chart and media collections');
  assert.match(urls[1],/\/patients\/8\?include_chart=true&include_media=false$/,'tooth-chart reads must request FDI data without a duplicate gallery page');
  assert.match(urls[2],/\/patients\/8\?include_chart=false&include_media=true$/,'a future screen can explicitly request the legacy media preview');
 }finally{global.fetch=original}
});


test('patient media upload receipt uses patient-scoped route and bearer identity',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async(url,init)=>{
   assert.match(url,/\/patients\/84\/media\/uploads\/native-media-receipt-0001$/);
   assert.equal(init.headers.Authorization,'Bearer secret');
   return reply({found:true,media:{id:19,original_filename:'synthetic.png',media_type:'PHOTO'}});
  };
  const result=await getPatientMediaUpload('secret',84,'native-media-receipt-0001');
  assert.equal(result.found,true);
  assert.equal(result.media.id,19);
  global.fetch=async()=>{throw Error('network must not be called for invalid intent')};
  await assert.rejects(()=>getPatientMediaUpload('secret',84,'short'),/Geçersiz/);
  await assert.rejects(()=>getPatientMediaUpload('secret',0,'native-media-receipt-0001'),/Geçersiz/);
 }finally{global.fetch=original}
});
