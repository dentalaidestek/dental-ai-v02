const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const {getSchedule}=require('../src/api.ts');
const reply=body=>({ok:true,status:200,text:async()=>JSON.stringify(body)});
test('native schedule rejects malformed patient-linked events and duplicate identifiers',async()=>{
 const old=global.fetch;
 const base={items:[{id:7,event_type:'APPOINTMENT',title:'Kontrol',start_at:'2026-11-15T10:00:00',patient_id:2}],event_types:{APPOINTMENT:'Randevu'}};
 try{
  for(const body of [
   {...base,items:null}, {...base,event_types:null},
   {...base,items:[...base.items,...base.items]},
   {...base,items:[{...base.items[0],id:0}]},
   {...base,items:[{...base.items[0],patient_id:-1}]},
   {...base,items:[{...base.items[0],patient_id:'2'}]},
   {...base,items:[{...base.items[0],start_at:null}]},
  ]){
   global.fetch=async()=>reply(body);
   await assert.rejects(()=>getSchedule('token'),/geçersiz randevu listesi/);
  }
  global.fetch=async()=>reply(base);
  assert.equal((await getSchedule('token')).items[0].patient_id,2);
 }finally{global.fetch=old}
});

test('appointment creation requires a valid patient identity and matching server receipt',async()=>{
 const {createSchedule}=require('../src/api.ts');
 const old=global.fetch;let calls=0;
 const payload={event_type:'APPOINTMENT',title:'Kontrol',start_at:'2026-11-15T10:00:00',patient_id:8};
 try{
  global.fetch=async()=>{calls++;return reply({event:{id:23,patient_id:9}})};
  await assert.rejects(()=>createSchedule('token',{...payload,patient_id:0}),/Geçersiz randevu/);
  assert.equal(calls,0);
  await assert.rejects(()=>createSchedule('token',payload),/Randevu kaydı doğrulanamadı/);
  global.fetch=async()=>reply({event:{id:23,patient_id:8}});
  assert.equal((await createSchedule('token',payload)).event.patient_id,8);
 }finally{global.fetch=old}
});
