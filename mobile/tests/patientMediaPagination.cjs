const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

function loadApi(payload,status=200){
 const calls=[];
 const source=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');
 const compiled=ts.transpileModule(source,{fileName:'modernApi.ts',compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020
 }}).outputText;
 const exports={};
 class ApiError extends Error{constructor(code,message){super(message);this.status=code}}
 vm.runInNewContext(compiled,{
  exports,Error,Number,Array,Set,Date,Promise,AbortController,setTimeout,clearTimeout,
  FormData:class FormData{},
  fetch:async(url,init)=>{calls.push({url,init});return{ok:status>=200&&status<300,status,text:async()=>JSON.stringify(payload)}},
  require:name=>{
   if(name==='./chatFiles')return{validateChatFile:()=>true};
   if(name==='./api')return{ApiError,API_BASE:'https://dentalai.tr/api/mobile/v1'};
   if(name==='./sessionExpiry')return{revalidateSession:async()=>{}};
   if(name==='./notificationState')return{normalizeNotificationReadAt:value=>value};
   throw Error('Unexpected module '+name);
  }
 });
 return{api:exports,calls};
}
const row=(id,media_type='PHOTO')=>({
 id,filename:'clinical-'+id+'.jpg',media_type,tooth_number:'36',
 note:'Kontrol',uploaded_at:'2026-11-20T10:00:00'
});

test('modern media API imports the shared canonical API base',()=>{const source=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');assert.match(source,/import \{ApiError,API_BASE\} from '\.\/api'/);assert.doesNotMatch(source,/const API_BASE=/);});

test('native clinical media accepts the web-compatible descending cursor page and builds private API paths',async()=>{
 const {api,calls}=loadApi({items:[row(42,'RADIOGRAPH'),row(41)],next_before:41});
 const page=await api.getMedia('synthetic-token',7);
 assert.deepEqual(Array.from(page.items,x=>x.id),[42,41]);
 assert.equal(page.next_before,41);
 assert.equal(page.items[0].media_type,'RADIOGRAPH');
 assert.equal(page.items[0].url,'https://dentalai.tr/api/mobile/v1/patients/7/media/42/file');
 assert.equal(page.items[0].thumbnail_url,'https://dentalai.tr/api/mobile/v1/patients/7/media/42/thumbnail');
 assert.match(calls[0].url,/\/patients\/7\/media\?limit=40$/);
 assert.equal(calls[0].init.credentials,'omit');
 assert.equal(calls[0].init.headers.Authorization,'Bearer synthetic-token');
});

test('native clinical media accepts an explicit terminal cursor and empty terminal page',async()=>{
 const first=loadApi({items:[row(9)],next_before:null});
 const page=await first.api.getMedia('token',4);
 assert.equal(page.next_before,null);
 const empty=loadApi({items:[],next_before:null});
 assert.deepEqual(Array.from((await empty.api.getMedia('token',4)).items),[]);
});

test('native clinical media rejects missing, misplaced and non-descending cursors before rendering',async()=>{
 const malformed=[
  {items:[row(9)]},
  {items:[row(9),row(8)],next_before:9},
  {items:[row(8),row(9)],next_before:9},
  {items:[row(9),row(9)],next_before:null},
  {items:[row(9,'UNRECOGNIZED')],next_before:null},
  {items:[{...row(9),note:'x'.repeat(2001)}],next_before:null},
  {items:[row(9)],next_before:0},
  {items:[],next_before:9}
 ];
 for(const body of malformed){
  const {api}=loadApi(body);
  await assert.rejects(()=>api.getMedia('token',4),/Klinik medya sunucusundan geçersiz/);
 }
});

test('native clinical media rejects rows that cross the requested before cursor',async()=>{
 const {api}=loadApi({items:[row(8),row(7)],next_before:7});
 await assert.rejects(()=>api.getMedia('token',4,8),/Klinik medya sunucusundan geçersiz/);
});

test('native clinical media validates patient and cursor IDs before making a request',async()=>{
 const {api,calls}=loadApi({items:[],next_before:null});
 for(const value of [0,-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'4',null]){
  await assert.rejects(()=>api.getMedia('token',value),/Geçersiz hasta veya sayfa kimliği/);
 }
 await assert.rejects(()=>api.getMedia('token',4,0),/Geçersiz hasta veya sayfa kimliği/);
 assert.equal(calls.length,0);
});
