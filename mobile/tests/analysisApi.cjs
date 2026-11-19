const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const api=require('../src/analysisApi.ts');
test('analysis detail rejects HTML success and bounds a stalled history request',async t=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response('<html>login</html>',{status:200});
  await assert.rejects(()=>api.getAnalysis('test',23),e=>e.status===502);
  t.mock.timers.enable({apis:['setTimeout']});
  global.fetch=(_url,options)=>new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted'))));
  const pending=assert.rejects(()=>api.getAnalysis('test',23),e=>e.status===408);
  t.mock.timers.tick(30000);
  await pending;
 }finally{global.fetch=original;t.mock.timers.reset()}
});
test('AI rejects invalid patient and missing clinical image without contacting backend',async()=>{
 const original=global.fetch;global.fetch=()=>{throw Error('unexpected network call')};
 try{
  await assert.rejects(()=>api.createAnalysis('token',{patientId:0,images:[{uri:'file:///image.jpg'}]}),/geçerli hasta/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:5,images:[]}),/en az bir klinik/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:5,images:[{uri:''}]}),/klinik görüntü/);
 }finally{global.fetch=original}
});
test('AI rejects invalid analysis IDs before a network request',async()=>{
 const original=global.fetch;global.fetch=()=>{throw Error('unexpected network call')};
 try{
  await assert.rejects(()=>api.getAnalysis('token',0),/Geçersiz analiz/);
  await assert.rejects(()=>api.getAnalysis('token',NaN),/Geçersiz analiz/);
  assert.throws(()=>api.startAnalysisAI('token',-3),/Geçersiz analiz/);
 }finally{global.fetch=original}
});
test('AI status and start use authorized mobile API routes',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify(url.endsWith('/ai')?{ok:true,status:'VISION_READY',job_id:31}:{analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null},assets:[]}),{status:200})};
 try{
  await api.getAnalysis('secret',23);
  await api.startAnalysisAI('secret',23);
  assert.match(calls[0].url,/\/api\/mobile\/v1\/analyses\/23$/);
  assert.match(calls[1].url,/\/api\/mobile\/v1\/analyses\/23\/ai$/);
  assert.equal(calls[1].init.method,'POST');
  assert.equal(calls[0].init.headers.Authorization,'Bearer secret');
  assert.equal(calls[1].init.headers.Authorization,'Bearer secret');
 }finally{global.fetch=original}
});

test('AI start accepts an already completed analysis without creating another job',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({ok:true,status:'AI_ANALYZED'}),{status:200});
 try{const result=await api.startAnalysisAI('token',23);assert.equal(result.status,'AI_ANALYZED');assert.equal(result.job_id,undefined)}
 finally{global.fetch=original}
});
test('AI start rejects a response without a durable job receipt',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({ok:true,status:'VISION_READY'}),{status:200});
 try{await assert.rejects(()=>api.startAnalysisAI('token',23),error=>error.status===502)}
 finally{global.fetch=original}
});
test('AI refuses malformed created-job response instead of persisting an invalid job ID',async()=>{
 const originalFetch=global.fetch,originalFormData=global.FormData;
 class NativeFormStub{append(){}}
 global.FormData=NativeFormStub;
 global.fetch=async()=>new Response(JSON.stringify({ok:true,analysis_id:null,status:'UPLOADED'}),{status:200});
 try{
  await assert.rejects(()=>api.createAnalysis('secret',{patientId:7,images:[{uri:'file:///image.jpg',name:'image.jpg',type:'image/jpeg'}]}),/geçerli bir iş kimliği/);
 }finally{global.fetch=originalFetch;global.FormData=originalFormData}
});

test('AI rejects a result linked to a different patient',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:8,anonymous_id:'SYNTHETIC-8',age:null,chief_complaint:null},assets:[]}),{status:200});
 try{await assert.rejects(()=>api.getAnalysis('token',23),/hasta veya iş kimliği uyuşmayan/)}
 finally{global.fetch=original}
});
test('analysis detail rejects a duplicate raw clinical result payload',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null},assets:[],ai_result:{private_marker:'Synthetic private result'}}),{status:200});
 try{await assert.rejects(()=>api.getAnalysis('token',23),error=>error.status===502)}
 finally{global.fetch=original}
});
test('AI rejects a result with a mismatched analysis job ID',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({analysis:{id:24,patient_id:7,status:'VISION_READY'},patient:{id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null},assets:[]}),{status:200});
 try{await assert.rejects(()=>api.getAnalysis('token',23),/hasta veya iş kimliği uyuşmayan/)}
 finally{global.fetch=original}
});

test('modern API rejects HTML and scalar success payloads instead of silently accepting them',async()=>{
 const {getNotifications}=require('../src/modernApi.ts');
 const original=global.fetch;
 try{
  for(const raw of ['<html>login</html>','null','42','', '   ', '[]']){
   global.fetch=async()=>new Response(raw,{status:200});
   await assert.rejects(()=>getNotifications('token'),error=>error.status===502);
  }
 }finally{global.fetch=original}
});

test('modern API preserves HTTP errors with null or malformed response bodies',async()=>{
 const {getNotifications}=require('../src/modernApi.ts');
 const original=global.fetch;
 try{
  for(const raw of ['null','<html>service unavailable</html>','{"detail":null}']){
   global.fetch=async()=>new Response(raw,{status:503});
   await assert.rejects(()=>getNotifications('token'),error=>error.status===503&&error.name==='ApiError');
  }
  global.fetch=async()=>new Response(JSON.stringify({detail:{message:'Bakım sürüyor'}}),{status:503});
  await assert.rejects(()=>getNotifications('token'),error=>error.status===503&&error.message==='Bakım sürüyor');
 }finally{global.fetch=original}
});


test('native image AI rejects more than four images and unsupported file types before network',async()=>{
 const original=global.fetch;let requests=0;
 global.fetch=()=>{requests++;throw Error('unexpected network request')};
 try{
  const valid={uri:'file:///scan.jpg',name:'scan.jpg',type:'image/jpeg'};
  await assert.rejects(()=>api.createAnalysis('token',{patientId:8,images:Array(5).fill(valid)}),/en fazla 4/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:8,images:[{uri:'file:///scan.txt',name:'scan.txt',type:'text/plain'}]}),/JPEG, PNG veya WebP/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:8,images:[{uri:'file:///scan.png',name:'scan.png',type:'application/pdf'}]}),/JPEG, PNG veya WebP/);
  assert.equal(requests,0);
 }finally{global.fetch=original}
});

test('valid JPEG PNG and WebP clinical filenames pass preflight and invalid suffixes fail',async()=>{
 const original=global.fetch,originalFormData=global.FormData,calls=[];
 class NativeFormStub{append(){}}
 global.FormData=NativeFormStub;
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({ok:true,analysis_id:73,status:'ANALYZING'}),{status:200})};
 try{
  for(const [name,type] of [['photo.jpg','image/jpeg'],['scan.PNG','image/png'],['image.webp','image/webp']]){
   const result=await api.createAnalysis('token',{patientId:7,images:[{uri:'file:///scan',name,type}]});
   assert.equal(result.analysis_id,73);
  }
  assert.equal(calls.length,3);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[{uri:'file:///scan',name:'malware.exe',type:'image/jpeg'}]}),/JPEG, PNG veya WebP/);
  assert.equal(calls.length,3,'invalid filename must not reach network');
 }finally{global.fetch=original;global.FormData=originalFormData}
});

test('analysis history rejects malformed patient filters without a request',async()=>{
 const original=global.fetch;let count=0;
 global.fetch=async()=>{count++;return new Response(JSON.stringify({items:[]}),{status:200})};
 try{
  for(const id of [0,-1,NaN,1.5,Number.MAX_SAFE_INTEGER+1])assert.throws(()=>api.getAnalysisHistory('token',id),/Geçersiz hasta/);
  assert.equal(count,0);
  await api.getAnalysisHistory('token',7);
  assert.equal(count,1);
 }finally{global.fetch=original}
});

test('mixed valid and invalid clinical image batch is rejected atomically before upload',async()=>{
 const original=global.fetch;let count=0;global.fetch=async()=>{count++;throw Error('unexpected upload')};
 try{
  await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[{uri:'file:///a',name:'a.jpg',type:'image/jpeg'},{uri:'file:///b',name:'b.pdf',type:'application/pdf'}]}),/JPEG, PNG veya WebP/);
  assert.equal(count,0,'no partial batch must be sent');
 }finally{global.fetch=original}
});


test('image picker missing MIME uses extension and mismatched MIME is rejected before upload',async()=>{
 const oldFetch=global.fetch,oldForm=global.FormData,parts=[];
 class NativeFormStub{append(key,value){parts.push({key,value})}}
 global.FormData=NativeFormStub;
 let calls=0;
 global.fetch=async()=>{calls++;return new Response(JSON.stringify({ok:true,analysis_id:90,status:'ANALYZING'}),{status:200})};
 try{
  await api.createAnalysis('token',{patientId:7,images:[{uri:'file:///scan.png',name:'scan.png'},{uri:'file:///scan.webp',name:'scan.webp'}]});
  assert.deepEqual(parts.filter(x=>x.key==='images').map(x=>x.value.type),['image/png','image/webp']);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[{uri:'file:///scan.png',name:'scan.png',type:'image/jpeg'}]}),/eşleşmelidir/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[{uri:'file:///scan.jpg',name:'scan.jpg',type:'image/webp'}]}),/eşleşmelidir/);
  assert.equal(calls,1);
 }finally{global.fetch=oldFetch;global.FormData=oldForm}
});

test('unnamed PNG and WebP picker assets retain their URI-derived MIME type',async()=>{
 const oldFetch=global.fetch,oldForm=global.FormData,parts=[];
 class FormStub{append(key,value){parts.push({key,value})}}
 global.FormData=FormStub;
 global.fetch=async()=>new Response(JSON.stringify({ok:true,analysis_id:91,status:'ANALYZING'}),{status:200});
 try{
  await api.createAnalysis('token',{patientId:7,images:[
   {uri:'file:///private/scan.PNG?cache=1'},
   {uri:'content://provider/scan.webp#preview'}
  ]});
  assert.deepEqual(parts.filter(p=>p.key==='images').map(p=>[p.value.name,p.value.type]),[
   ['dental-image-0.png','image/png'],['dental-image-1.webp','image/webp']
  ]);
 }finally{global.fetch=oldFetch;global.FormData=oldForm}
});

test('clinical image upload rejects unsafe filenames and unknown unnamed URI formats',async()=>{
 const oldFetch=global.fetch;let requests=0;
 global.fetch=()=>{requests++;throw Error('unexpected upload')};
 try{
  for(const name of ['../scan.jpg','folder/scan.jpg','folder\\scan.jpg','bad\u0000scan.png','bad\nscan.webp','x'.repeat(256)+'.jpg']){
   await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[{uri:'file:///scan.jpg',name,type:'image/jpeg'}]}));
  }
  await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[{uri:'content://provider/opaque'}]}),/JPEG, PNG veya WebP/);
  assert.equal(requests,0);
 }finally{global.fetch=oldFetch}
});

test('patient-scoped analysis history refuses cross-patient entries',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({items:[{id:10,patient_id:9,status:'VISION_READY'}]}),{status:200});
 try{await assert.rejects(()=>api.getAnalysisHistory('token',7),error=>error.status===502&&/hasta veya kayıt/.test(error.message))}
 finally{global.fetch=original}
});

test('analysis history refuses malformed item identifiers and non-array items',async()=>{
 const original=global.fetch;
 try{
  for(const items of [null,{},[{id:0,patient_id:7}],[{id:3,patient_id:0}],[null]]){
   global.fetch=async()=>new Response(JSON.stringify({items}),{status:200});
   await assert.rejects(()=>api.getAnalysisHistory('token',7),error=>error.status===502);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:3,patient_id:7,status:'VISION_READY'}]}),{status:200});
  assert.equal((await api.getAnalysisHistory('token',7)).items[0].id,3);
 }finally{global.fetch=original}
});

test('opaque Android content URI with trusted picker MIME receives matching filename',async()=>{
 const oldFetch=global.fetch,oldForm=global.FormData,parts=[];
 class FormStub{append(key,value){parts.push({key,value})}}
 global.FormData=FormStub;
 let calls=0;
 global.fetch=async()=>{calls++;return new Response(JSON.stringify({ok:true,analysis_id:92,status:'ANALYZING'}),{status:200})};
 try{
  await api.createAnalysis('token',{patientId:7,images:[
   {uri:'content://media/external/images/media/12345',type:'image/png'},
   {uri:'content://com.android.providers.media.documents/document/image%3A89',type:'image/webp'},
   {uri:'content://provider/opaque',type:'image/jpeg'}
  ]});
  assert.deepEqual(parts.filter(p=>p.key==='images').map(p=>[p.value.name,p.value.type]),[
   ['dental-image-0.png','image/png'],['dental-image-1.webp','image/webp'],['dental-image-2.jpg','image/jpeg']
  ]);
  assert.equal(calls,1);
 }finally{global.fetch=oldFetch;global.FormData=oldForm}
});
test('opaque Android image URI cannot bypass unsupported or conflicting MIME checks',async()=>{
 const oldFetch=global.fetch;let calls=0;
 global.fetch=()=>{calls++;throw Error('unexpected network')};
 try{
  for(const image of [
   {uri:'content://provider/opaque',type:'application/pdf'},
   {uri:'content://provider/opaque',type:'image/svg+xml'},
   {uri:'content://provider/scan.png',type:'image/jpeg'},
   {uri:'content://provider/opaque',name:'scan.webp',type:'image/png'}
  ]){
   await assert.rejects(()=>api.createAnalysis('token',{patientId:7,images:[image]}),/JPEG, PNG veya WebP/);
  }
  assert.equal(calls,0);
 }finally{global.fetch=oldFetch}
});


test('analysis detail rejects duplicate and malformed clinical asset identifiers',async()=>{
 const oldFetch=global.fetch,asset=id=>({id,original_filename:'scan-'+id+'.png',image_type:'PERIAPICAL',has_vision:false});
 try{
  for(const assets of [[asset(2),asset(2)],[{...asset(2),id:0}],[{...asset(2),id:'4'}],[null]]){
   global.fetch=async()=>new Response(JSON.stringify({analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null},assets}),{status:200});
   await assert.rejects(()=>api.getAnalysis('token',23),error=>error.status===502);
  }
  global.fetch=async()=>new Response(JSON.stringify({analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null},assets:[asset(2),asset(3)]}),{status:200});
  assert.equal((await api.getAnalysis('token',23)).assets.length,2);
 }finally{global.fetch=oldFetch}
});

test('analysis history rejects duplicate record IDs even when patient matches',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({items:[
   {id:17,patient_id:7,status:'VISION_READY'},
   {id:17,patient_id:7,status:'ANALYZING'}
  ]}),{status:200});
  await assert.rejects(()=>api.getAnalysisHistory('token',7),error=>error.status===502);
  global.fetch=async()=>new Response(JSON.stringify({items:[
   {id:17,patient_id:7,status:'VISION_READY'},
   {id:18,patient_id:7,status:'ANALYZING'}
  ]}),{status:200});
  assert.deepEqual((await api.getAnalysisHistory('token',7)).items.map(item=>item.id),[17,18]);
 }finally{global.fetch=original}
});


test('analysis workspace rejects direct patient identifiers even when the patient ID matches',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({
  analysis:{id:23,patient_id:7,status:'VISION_READY'},
  patient:{id:7,anonymous_id:'SYNTHETIC-7',age:36,chief_complaint:'Synthetic complaint',first_name:'Private',phone:'5550000000'},
  assets:[]
 }),{status:200});
 try{await assert.rejects(()=>api.getAnalysis('token',23),error=>error.status===502&&/veri minimizasyonu/.test(error.message))}
 finally{global.fetch=original}
});

test('analysis workspace accepts only anonymous patient summary fields',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({
  analysis:{id:23,patient_id:7,status:'VISION_READY'},
  patient:{id:7,anonymous_id:'SYNTHETIC-7',age:0,chief_complaint:'Synthetic complaint'},
  assets:[]
 }),{status:200});
 try{
  const result=await api.getAnalysis('token',23);
  assert.equal(result.patient.anonymous_id,'SYNTHETIC-7');
  assert.equal(result.patient.age,0);
 }finally{global.fetch=original}
});

test('restored analysis patient choice falls back to anonymous ID while patient-list names remain usable',()=>{
 assert.equal(api.analysisPatientLabel({id:7,anonymous_id:'SYNTHETIC-7'}),'SYNTHETIC-7');
 assert.equal(api.analysisPatientLabel({id:7,anonymous_id:'SYNTHETIC-7',first_name:'Ada',last_name:'Lovelace'}),'Ada Lovelace');
});


test('analysis detail rejects storage paths, unsafe filenames and internal job errors',async()=>{
 const original=global.fetch;
 const patient={id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null};
 const asset={id:2,original_filename:'scan.png',image_type:'PERIAPICAL',has_vision:true};
 const analysis={id:23,patient_id:7,status:'VISION_READY'};
 const valid={analysis,patient,assets:[asset],job:null};
 const invalid=[
  {...valid,analysis:{...analysis,result_path:'uploads/private.json'}},
  {...valid,assets:[{...asset,file_path:'uploads/private.png'}]},
  {...valid,assets:[{...asset,original_filename:'../private.png'}]},
  {...valid,assets:Array(5).fill(asset)},
  {...valid,job:{id:5,kind:'PRELIMINARY',status:'FAILED',retryable:true,error_code:'PRIVATE_PROVIDER_ERROR'}}
 ];
 try{
  for(const payload of invalid){
   global.fetch=async()=>new Response(JSON.stringify(payload),{status:200});
   await assert.rejects(()=>api.getAnalysis('token',23),error=>error.status===502);
  }
  global.fetch=async()=>new Response(JSON.stringify({...valid,job:{id:5,kind:'PRELIMINARY',status:'DONE',retryable:false}}),{status:200});
  const result=await api.getAnalysis('token',23);
  assert.equal(result.job.id,5);
 }finally{global.fetch=original}
});

test('image-backed analysis accepts the canonical VISION work job and rejects unknown kinds',async()=>{
 const original=global.fetch;
 const patient={id:7,anonymous_id:'SYNTHETIC-7',age:null,chief_complaint:null};
 const analysis={id:23,patient_id:7,status:'VISION_PENDING'};
 const asset={id:2,original_filename:'scan.png',image_type:'PERIAPICAL',has_vision:false};
 const valid={analysis,patient,assets:[asset],job:{id:52,kind:'VISION',status:'QUEUED',retryable:false}};
 try{
  global.fetch=async()=>new Response(JSON.stringify(valid),{status:200});
  const result=await api.getAnalysis('token',23);
  assert.equal(result.job.kind,'VISION');
  assert.equal(result.job.status,'QUEUED');
  for(const kind of ['UPLOAD_RECEIPT','UNKNOWN']){
   global.fetch=async()=>new Response(JSON.stringify({...valid,job:{...valid.job,kind}}),{status:200});
   await assert.rejects(()=>api.getAnalysis('token',23),error=>error.status===502);
  }
 }finally{global.fetch=original}
});
