const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);

const presentation=require('../src/dashboardPresentation.ts');
const {
 dashboardGreetingForHour,dashboardProfessionalName,isDashboardProgramEvent,
 parseDashboardProgramSnapshot,applyDashboardProgramSnapshot,
}=presentation;

test('dashboard greeting follows the web time bands',()=>{
 assert.equal(dashboardGreetingForHour(4),'İyi akşamlar');
 assert.equal(dashboardGreetingForHour(5),'Günaydın');
 assert.equal(dashboardGreetingForHour(11),'Günaydın');
 assert.equal(dashboardGreetingForHour(12),'Merhaba');
 assert.equal(dashboardGreetingForHour(17),'Merhaba');
 assert.equal(dashboardGreetingForHour(18),'İyi akşamlar');
 assert.equal(dashboardGreetingForHour(24),'Merhaba');
});

test('professional display name mirrors web title prefixes without doubling them',()=>{
 assert.equal(dashboardProfessionalName('Diş Hekimi','Cihan Akak'),'Dt. Cihan Akak');
 assert.equal(dashboardProfessionalName('Uzman Diş Hekimi','Cihan Akak'),'Uzm. Dt. Cihan Akak');
 assert.equal(dashboardProfessionalName('Doç. Dr.','Doç. Dr. Cihan Akak'),'Doç. Dr. Cihan Akak');
 assert.equal(dashboardProfessionalName(null,'Cihan Akak'),'Cihan Akak');
 assert.equal(dashboardProfessionalName('Diş Hekimi',''),'Dental AI');
});

const event={id:42,title:'Kontrol randevusu',start_time:'09:30',type_label:'Randevu',patient_name:'Hasta A'};
const realtime={event_type:'PROGRAM_UPDATED',payload:{payload_version:1,dashboard_event:event,dashboard_event_label:'Bugün'}};

test('program snapshot accepts only the compact web realtime contract',()=>{
 assert.equal(isDashboardProgramEvent(event),true);
 assert.deepEqual(parseDashboardProgramSnapshot(realtime),{label:'Bugün',event});
 assert.deepEqual(parseDashboardProgramSnapshot({type:'PROGRAM_DELETED',payload:{payload_version:1,dashboard_event:null,dashboard_event_label:'Bugün'}}),{label:'Bugün',event:null});
 assert.equal(parseDashboardProgramSnapshot({...realtime,event_type:'PATIENT_UPDATED'}),null);
 assert.equal(parseDashboardProgramSnapshot({...realtime,payload:{...realtime.payload,payload_version:2}}),null);
 assert.equal(parseDashboardProgramSnapshot({...realtime,payload:{...realtime.payload,dashboard_event:{...event,start_time:'99:99'}}}),null);
 assert.equal(parseDashboardProgramSnapshot({...realtime,payload:{...realtime.payload,dashboard_event:{...event,patient_tc:'123'}}}),null);
});

test('program snapshot patch is immutable and preserves unrelated dashboard data',()=>{
 const current={stats:{patient_count:7},dashboard_event:null,dashboard_event_label:'Bugün'};
 const next=applyDashboardProgramSnapshot(current,{label:'Bugün',event});
 assert.notEqual(next,current);
 assert.equal(current.dashboard_event,null);
 assert.equal(next.dashboard_event.id,42);
 assert.deepEqual(next.stats,current.stats);
});

test('native home renders real recent analyses and patches valid program events without a dashboard GET',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 assert.match(source,/dashboardGreetingForHour/);
 assert.match(source,/dashboardProfessionalName/);
 assert.match(source,/parseDashboardProgramSnapshot\(lastEvent\)/);
 assert.match(source,/if\(snapshot\)setD\(previous=>previous\?applyDashboardProgramSnapshot/);
 assert.match(source,/recent_analyses\|\|\[\]/);
 assert.match(source,/nav\.navigate\("AnalysisResult",\{id:item\.id\}\)/);

 assert.match(source,/dashboard_event!==undefined/);

 const program=fs.readFileSync(path.join(__dirname,'../src/NativeProgram.tsx'),'utf8');
 assert.match(source,/nav\.navigate\("Program",hasProgramSnapshot\?\{eventId:programEvent\.id\}:\{\}\)/);
 assert.match(program,/visible\.items\.find\(item=>item\.event_id===targetEventId\)/);
 assert.match(program,/setEditor\(\{id:target\.event_id\}\)/);
 assert.match(program,/!actionIntentReady\|\|uncertain/);
 assert.match(source,/initialEventId=\{eventId\}/);
 assert.match(source,/openRequestId:Date\.now\(\)/);
 assert.match(source,/key=\{token\+":"\+openRequestId\}/);
 assert.match(program,/navigation\.setParams\?\.\(\{eventId:undefined\}\)/);



});

test('dashboard API validates the minimized summary and keeps old-server compatibility',async()=>{
 const {getDashboard,ApiError}=require('../src/api.ts');
 const original=global.fetch,calls=[];
 const base={user:{id:1,username:'owner',display_name:'Owner',role:'DOCTOR',is_active:true},stats:{patient_count:1,analysis_count:1,upcoming_event_count:0},recent_patients:[],upcoming_events:[]};
 global.fetch=async(url,init)=>{
  calls.push({url:String(url),init});
  return {ok:true,status:200,text:async()=>JSON.stringify(base)};
 };
 try{
  const legacy=await getDashboard('synthetic-token');
  assert.deepEqual(legacy.recent_analyses,undefined);
  assert.match(calls[0].url,/\/dashboard$/);
  assert.equal(calls[0].init.credentials,'omit');
  assert.equal(calls[0].init.headers.Authorization,'Bearer synthetic-token');

  const valid={...base,recent_analyses:[{id:9,patient_id:4,patient_name:'Hasta A',tooth_number:'36',status:'AI_ANALYZED',created_at:'2026-11-21T08:00:00'}],dashboard_event:event,dashboard_event_label:'Bugün'};
  global.fetch=async()=>({ok:true,status:200,text:async()=>JSON.stringify(valid)});
  const result=await getDashboard('synthetic-token');
  assert.equal(result.recent_analyses[0].id,9);

  global.fetch=async()=>({ok:true,status:200,text:async()=>JSON.stringify({...base,recent_analyses:[{id:9,patient_id:4,patient_name:'Hasta A',clinical_notes:'must not be returned',status:'DRAFT',created_at:'2026-11-21'}]})});
  await assert.rejects(()=>getDashboard('synthetic-token'),error=>error instanceof ApiError&&error.status===502);

  global.fetch=async()=>({ok:true,status:200,text:async()=>JSON.stringify({...base,dashboard_event:{...event,start_time:'88:88'}})});
  await assert.rejects(()=>getDashboard('synthetic-token'),error=>error instanceof ApiError&&error.status===502);
 }finally{global.fetch=original}
});
