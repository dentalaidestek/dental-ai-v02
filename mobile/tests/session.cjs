const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {test} = require('node:test');
require.extensions['.ts'] = (module, filename) => {
 const source = fs.readFileSync(filename, 'utf8');
 const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}});
 module._compile(compiled.outputText, filename);
};
const {ApiError, getMe} = require('../src/api.ts');
const {restoreStoredSession} = require('../src/session.ts');

for (const [name,error,shouldDelete] of [
 ['offline',new TypeError('Network request failed'),false],
 ['server failure',new ApiError(503,'Unavailable'),false],
 ['forbidden',new ApiError(403,'Forbidden'),false],
 ['rate limit',new ApiError(429,'Retry later'),false],
 ['invalid session',new ApiError(401,'Unauthorized'),true],
]) {
 test(`session restore: ${name}`,async()=>{
  const deleted=[];
  const store={getItemAsync:async()=> 'stored-token',deleteItemAsync:async key=>{deleted.push(key)}};
  const action=()=>restoreStoredSession(store,async()=>{throw error});
  if(shouldDelete)assert.equal(await action(),null);
  else await assert.rejects(action,error);
  assert.deepEqual(deleted,shouldDelete?['dentalai_token']:[]);
 });
}
test('successful restore keeps token and returns validated user',async()=>{
 const user={id:7};
 const store={getItemAsync:async()=> 'stored-token',deleteItemAsync:async()=>{assert.fail('must not delete')}};
 assert.deepEqual(await restoreStoredSession(store,async token=>{assert.equal(token,'stored-token');return {user}}),{token:'stored-token',user});
});
test('API error retains HTTP status for session policy',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({detail:'Unauthorized'}),{status:401});
  await assert.rejects(()=>getMe('stored-token'),error=>error instanceof ApiError&&error.status===401);
 }finally{global.fetch=original;}
});

const {RealtimeCursor} = require('../src/realtimeCursor.ts');
test('durable event_id advances cursor, replay deduplicates and delayed events survive',()=>{
 const c=new RealtimeCursor(900);
 assert.equal(c.resumeAfter(),400);
 assert.equal(c.accept({event_id:1000}),true);
 assert.equal(c.accept({event_id:1000}),false);
 assert.equal(c.accept({event_id:950}),true);
 assert.equal(c.current,1000);
 assert.equal(c.accept({id:1001}),true);
 assert.equal(c.current,1001);
});
test('invalid stored and event cursors cannot poison recovery',()=>{
 for(const saved of ['NaN',-1,Infinity])assert.equal(new RealtimeCursor(saved).current,0);
 const c=new RealtimeCursor();
 for(const id of [0,-1,'200',NaN,Infinity,1.5])assert.equal(c.accept({event_id:id}),false);
 assert.equal(c.current,0);
});

const modernApi=require('../src/modernApi.ts');
test('academic request uses the authoritative JSON contract',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async(url,init)=>{
   assert.equal(url,'https://dentalai.tr/api/mobile/v1/academic/courses/12/ask');
   assert.equal(init.headers['Content-Type'],'application/json');
   assert.deepEqual(JSON.parse(init.body),{message:'Synthetic question'});
   return new Response(JSON.stringify({ok:true,answer:'Synthetic answer'}));
  };
  assert.equal((await modernApi.askAcademic('token',12,'Synthetic question')).answer,'Synthetic answer');
 }finally{global.fetch=original;}
});
test('media URL remains on the authenticated native endpoint',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:3,original_filename:'scan.png',url:'https://untrusted.invalid/file'}]}));
  const result=await modernApi.getMedia('token',7);
  assert.equal(result.items[0].filename,'scan.png');
  assert.equal(result.items[0].url,'https://dentalai.tr/api/mobile/v1/patients/7/media/3/file');
 }finally{global.fetch=original;}
});
test('message retries retain the server idempotency identity',async()=>{
 const original=global.fetch;const ids=[];
 try{
  global.fetch=async(url,init)=>{ids.push(JSON.parse(init.body).client_message_id);return new Response(JSON.stringify({ok:true,message:{id:3}}));};
  await modernApi.sendConsultationMessage('token',7,'Synthetic','stable-client-message-id');
  await modernApi.sendConsultationMessage('token',7,'Synthetic','stable-client-message-id');
  assert.deepEqual(ids,['stable-client-message-id','stable-client-message-id']);
 }finally{global.fetch=original;}
});
test('patient media upload sends a stable receipt key and reports real multipart byte progress',async()=>{
 const originalXHR=global.XMLHttpRequest,originalForm=global.FormData;
 const fields=[],progress=[];let request;
 try{
  global.FormData=class {append(name,value){fields.push([name,value]);}};
  global.XMLHttpRequest=class{
   constructor(){this.upload={onprogress:null};this.headers={};request=this;}
   open(method,url){this.method=method;this.url=url;}
   setRequestHeader(name,value){this.headers[name]=value;}
   send(body){this.body=body;this.upload.onprogress?.({loaded:50,total:100,lengthComputable:true});this.status=200;this.responseText=JSON.stringify({media:{id:3,original_filename:'scan.png',media_type:'RADIOGRAPH'},replayed:false});this.onload();}
  };
  const {uploadPatientMedia}=require('../src/api.ts');
  const result=await uploadPatientMedia('token',7,{uri:'file:///synthetic.png',name:'scan.png',type:'image/png'},undefined,'RADIOGRAPH','stable-media-request-key-0001',value=>progress.push(value));
  assert.equal(result.media.id,3);
  assert.equal(request.method,'POST');
  assert.equal(request.url,'https://dentalai.tr/api/mobile/v1/patients/7/media');
  assert.equal(request.headers.Authorization,'Bearer token');
  assert.equal(request.headers['Content-Type'],undefined);
  assert.equal(request.withCredentials,false);
  assert.deepEqual(fields.map(([name])=>name),['media_type','request_key','file']);
  assert.equal(fields[0][1],'RADIOGRAPH');
  assert.equal(fields[1][1],'stable-media-request-key-0001');
  assert.deepEqual(fields[2][1],{uri:'file:///synthetic.png',name:'scan.png',type:'image/png'});
  assert.deepEqual(progress,[{loaded:50,total:100,lengthComputable:true}]);
 }finally{global.XMLHttpRequest=originalXHR;global.FormData=originalForm;}
});

test('patient media receipt lookup is authenticated, patient-scoped and validates its response',async()=>{
 const original=global.fetch;let url,init;
 try{
  global.fetch=async(value,options)=>{url=value;init=options;return new Response(JSON.stringify({found:true,media:{id:3,original_filename:'scan.png',media_type:'PHOTO'}}));};
  const {getPatientMediaUpload}=require('../src/api.ts');
  const result=await getPatientMediaUpload('token',7,'stable-media-request-key-0001');
  assert.equal(result.found,true);
  assert.equal(result.media.id,3);
  assert.equal(url,'https://dentalai.tr/api/mobile/v1/patients/7/media/uploads/stable-media-request-key-0001');
  assert.equal(init.headers.Authorization,'Bearer token');
 }finally{global.fetch=original;}
});

test('invalid patient media request keys are rejected before network or upload',async()=>{
 const original=global.fetch,originalXHR=global.XMLHttpRequest;let calls=0;
 try{
  global.fetch=async()=>{calls++;return new Response('{}')};
  global.XMLHttpRequest=class{open(){calls++}};
  const {getPatientMediaUpload,uploadPatientMedia}=require('../src/api.ts');
  await assert.rejects(()=>getPatientMediaUpload('token',7,'bad-key'));
  await assert.rejects(()=>uploadPatientMedia('token',7,{uri:'file:///x',name:'x.png',type:'image/png'},undefined,'PHOTO','bad-key'));
  assert.equal(calls,0);
 }finally{global.fetch=original;global.XMLHttpRequest=originalXHR;}
});
