const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const text=node=>typeof node==='string'?node:!node?'':(node.children||[]).map(text).join('');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const page=(view='week',title='Synthetic appointment')=>({view,focus_date:'2030-01-07',today:'2030-01-07',timezone:'Europe/Istanbul',previous_day:'2029-12-31',next_day:'2030-01-14',month_title:'Ocak 2030',copy_days:Array.from({length:7},(_,i)=>({date:new Date(Date.UTC(2030,0,7+i)).toISOString().slice(0,10),label:'Pzt'})),days:Array.from({length:view==='month'?42:view==='week'?7:1},(_,i)=>({date:new Date(Date.UTC(2030,0,7+i)).toISOString().slice(0,10),label:'Pzt',in_month:true,count:i?0:1,event_types:[],has_more:false})),items:[{key:'1:2030-01-07T10:00',event_id:1,event_type:'APPOINTMENT',title,status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:null,patient_name:null,location:null,notes:null,recurrence_rule:'NONE'}],total:1,next_offset:null,next_cursor:null,event_types:{APPOINTMENT:'Hasta / Randevu',CLASS:'Ders'},reminders:['NONE','30'],recurrences:['NONE','WEEKLY'],suggested_start_local:'2030-01-07T10:00',suggested_end_local:'2030-01-07T10:30'});
function component(file,api){
 const exports={},native={StyleSheet:{create:x=>x},AppState:{addEventListener:()=>({remove(){}})},BackHandler:{addEventListener:()=>({remove(){}})},Alert:{alert:(...args)=>api.onAlert?.(...args)},PanResponder:{create:()=>({panHandlers:{}})},...Object.fromEntries(['ActivityIndicator','FlatList','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 native.FlatList=props=>React.createElement('FlatList',props,props.ListHeaderComponent,...(props.data||[]).map((item,index)=>React.createElement(React.Fragment,{key:item.key},props.renderItem?.({item,index}))),props.ListEmptyComponent&&!(props.data||[]).length?props.ListEmptyComponent:null,props.ListFooterComponent);
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/'+file+'.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true,usePreventRemove:()=>{},useNavigation:()=>({navigate:(...args)=>api.onNavigate?.(...args)})}:name==='./programApi'?{checkProgramConflicts:async()=>({advisory:true,total:0,items:[]}),getProgramMutation:async()=>({state:'NOT_FOUND'}),verifyProgramAction:async()=> 'UNKNOWN',...api,programEventMatchesPayload:api.programEventMatchesPayload||require('../src/programApi.ts').programEventMatchesPayload}:name==='./programIntent'?{loadProgramRequestKey:async()=>null,getOrCreateProgramRequestKey:async()=> 'program-request-key-00000001',clearProgramRequestKey:async()=>{},loadProgramActionIntent:async()=>null,saveProgramActionIntent:async()=>{},clearProgramActionIntent:async()=>{},...api}:name==='./programInlineAdd'?require('../src/programInlineAdd.ts'):name==='./programModel'?require('../src/programModel.ts'):name==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'SYNTHETIC',first_name:'Synthetic'}})}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='./useSessionRenderKey'?require('./helpers/useSessionRenderKeyModule.cjs'):{default:name.slice(2)}});
 return exports.default;
}
const button=(tree,label)=>tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>text(child)===label));
test('program payload validates real dates, end order and removes stale patient/recurrence fields',()=>{
 const {programPayload,validWallTime,wallTimeLabel}=require('../src/programModel.ts');
 const base={event_type:'APPOINTMENT',title:'Test visit',start_at:'2030-01-07T10:00',end_at:'2030-01-07T10:30',patient_id:8,location:'',notes:'',reminder_minutes:'NONE',recurrence_rule:'NONE',recurrence_until:'2029-01-01'};
 assert.equal(programPayload(base).patient_id,8);assert.equal(programPayload({...base,event_type:'CLASS'}).patient_id,undefined);assert.equal(programPayload(base).recurrence_until,'');
 assert.throws(()=>programPayload({...base,end_at:'2030-01-07T09:59'}));assert.throws(()=>programPayload({...base,recurrence_rule:'WEEKLY'}));
 assert.equal(validWallTime('2025-02-29T10:00'),false);assert.equal(validWallTime('2030-01-07T24:00'),false);assert.equal(wallTimeLabel(base.start_at),'10:00');assert.throws(()=>programPayload({...base,location:'x'.repeat(161)}),/Konum/);assert.throws(()=>programPayload({...base,reminder_minutes:'BAD'}),/Hatırlatma/);const {programTitleCopy}=require('../src/programModel.ts');assert.deepEqual(programTitleCopy('CLASS'),{label:'Ders adı',placeholder:'Örn. Ortodonti'});assert.equal(programTitleCopy('UNKNOWN').label,'Başlık');
});
test('program form sends a selected record once despite duplicate taps and disables reminders explicitly',async()=>{
 const calls=[];let release;const Editor=component('NativeProgramEditor',{saveProgramEvent:async(_token,payload,_eventId,requestKey)=>{calls.push({payload,requestKey});return new Promise(resolve=>{release=()=>resolve({id:7,...payload,start_local:payload.start_at})})}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),onSaved(){},onClose(){}}));await tick()});
 await renderer.act(async()=>{tree.root.findByProps({accessibilityLabel:'Program başlığı'}).props.onChangeText('Actual native appointment');tree.root.findByType('NativePatientSelect').props.onChange({id:8,anonymous_id:'SYNTHETIC',first_name:'Synthetic'})});
 await renderer.act(async()=>button(tree,'Hatırlatma yok').props.onPress());
 await renderer.act(async()=>{const save=button(tree,'Programa Ekle');save.props.onPress();save.props.onPress()});
 assert.equal(calls.length,1);assert.equal(calls[0].payload.patient_id,8);assert.equal(calls[0].payload.reminder_minutes,'NONE');assert.equal(calls[0].requestKey,'program-request-key-00000001');
 await renderer.act(async()=>release());await renderer.act(async()=>tree.unmount());
});
test('calendar hides previous account data while the next account request is pending',async()=>{
 let resolve;const Program=component('NativeProgram',{getProgram:async token=>token==='one'?page('week','Private first account'):new Promise(r=>{resolve=r})});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'one',userId:1}));await tick()});
 assert.equal(tree.root.findByType('FlatList').props.data[0].title,'Private first account');
 await renderer.act(async()=>tree.update(React.createElement(Program,{token:'two',userId:2})));
 assert.equal(tree.root.findByType('FlatList').props.data.length,0);
 await renderer.act(async()=>resolve(page('week','Second account')));
 assert.equal(tree.root.findByType('FlatList').props.data[0].title,'Second account');
 await renderer.act(async()=>tree.unmount());
});
test('program API refuses mismatched days, malformed pages and another event receipt',async()=>{
 const api=require('../src/programApi.ts'),original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({...page(),focus_date:'2030-01-08'}),{status:200});
  await assert.rejects(()=>api.getProgram('token','week','2030-01-07'),/geçersiz takvim/);
  global.fetch=async()=>new Response(JSON.stringify({...page(),items:[null]}),{status:200});
  await assert.rejects(()=>api.getProgram('token','week'),/geçersiz takvim/);
  global.fetch=async()=>new Response(JSON.stringify({event:{id:2}}),{status:200});
  await assert.rejects(()=>api.getProgramEvent('token',1),/doğrulanamadı/);
 }finally{global.fetch=original}
});

test('program API sends a stable request key and reconciles the server receipt',async()=>{
 const api=require('../src/programApi.ts'),original=global.fetch;
 const draft={event_type:'APPOINTMENT',title:'Synthetic API visit',start_at:'2030-01-07T10:00',end_at:'2030-01-07T10:30',patient_id:8,location:'',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 const event={id:7,event_type:'APPOINTMENT',title:draft.title,status:'ACTIVE',start_local:draft.start_at,end_local:draft.end_at,patient_id:8,patient_name:'Synthetic',location:'',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 try{
  let body,url;
  global.fetch=async(path,options)=>{url=String(path);body=JSON.parse(options.body);return new Response(JSON.stringify({event}),{status:200})};
  const saved=await api.saveProgramEvent('token',draft,undefined,'program-create-request-000001');
  assert.equal(saved.id,7);assert.equal(body.request_key,'program-create-request-000001');
  assert.equal(url.includes('/program/events'),true);
  global.fetch=async(path)=>{url=String(path);return new Response(JSON.stringify({state:'FOUND',event}),{status:200})};
  const receipt=await api.getProgramMutation('token','program-create-request-000001');
  assert.equal(receipt.state,'FOUND');assert.equal(receipt.event.id,7);
  assert.ok(url.includes('/program/mutations/program-create-request-000001'));
 }finally{global.fetch=original}
});

test('program create receipt must match every persisted field, not only start time and patient',async()=>{
 const api=require('../src/programApi.ts'),original=global.fetch;
 const draft={event_type:'APPOINTMENT',title:'Synthetic API visit',start_at:'2030-01-07T10:00',end_at:'2030-01-07T10:30',patient_id:8,location:'Clinic A',notes:'Synthetic note',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 const event={id:7,event_type:'APPOINTMENT',title:draft.title,status:'ACTIVE',start_local:draft.start_at,end_local:draft.end_at,patient_id:8,patient_name:'Synthetic',location:draft.location,notes:draft.notes,reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 try{
  assert.equal(api.programEventMatchesPayload(event,draft),true);
  const mismatches=[
   {...event,title:'Different title'},
   {...event,end_local:'2030-01-07T10:45'},
   {...event,patient_id:9},
   {...event,location:'Different clinic'},
   {...event,notes:'Different note'},
   {...event,reminder_minutes:'60'},
   {...event,recurrence_rule:'WEEKLY',recurrence_until:'2030-01-14'}
  ];
  for(const mismatch of mismatches){
   assert.equal(api.programEventMatchesPayload(mismatch,draft),false);
   global.fetch=async()=>new Response(JSON.stringify({event:mismatch}),{status:200});
   await assert.rejects(()=>api.saveProgramEvent('token',draft,undefined,'program-create-request-000001'),/Program kaydı sunucudan doğrulanamadı/);
  }
 }finally{global.fetch=original}
});

test('program event receipts reject invalid end ordering, malformed nullable fields and recurrence dates',async()=>{
 const api=require('../src/programApi.ts'),original=global.fetch;
 const event={id:7,event_type:'APPOINTMENT',title:'Synthetic visit',status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:8,patient_name:'Synthetic',location:'',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 try{
  for(const malformed of [
   {...event,end_local:'2030-01-07T09:59'},
   {...event,patient_name:{name:'Synthetic'}},
   {...event,location:'x'.repeat(161)},
   {...event,notes:'x'.repeat(2001)},
   {...event,recurrence_rule:'WEEKLY',recurrence_until:'2030-02-30'}
  ]){
   global.fetch=async()=>new Response(JSON.stringify({event:malformed}),{status:200});
   await assert.rejects(()=>api.getProgramEvent('token',7),/Program kaydı doğrulanamadı/);
  }
  global.fetch=async()=>new Response(JSON.stringify({event}),{status:200});
  assert.equal((await api.getProgramEvent('token',7)).id,7);
 }finally{global.fetch=original}
});

test('create recovery preserves its request key when a found receipt does not match the submitted appointment',async()=>{
 let clears=0,saved=0,lookups=0;
 const mismatch={id:77,event_type:'APPOINTMENT',title:'Another appointment',status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:null,patient_name:null,location:'',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 const Editor=component('NativeProgramEditor',{
  getOrCreateProgramRequestKey:async()=> 'program-create-request-000001',
  getProgramMutation:async()=>{lookups++;return{state:'FOUND',event:mismatch}},
  saveProgramEvent:async()=>{throw new Error('Synthetic response mismatch')},
  clearProgramRequestKey:async()=>{clears++}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),onSaved(){saved++},onClose(){}}));await tick()});
 await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'Program başlığı'}).props.onChangeText('Expected appointment'));
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(lookups,1);
 assert.equal(clears,0);
 assert.equal(saved,0);
 assert.ok(button(tree,'Bekleyen randevuyu doğrula'));
 await renderer.act(async()=>button(tree,'Bekleyen randevuyu doğrula').props.onPress());
 assert.equal(lookups,2);
 assert.equal(clears,0);
 assert.equal(saved,0);
 assert.ok(text(tree.root).includes('bekleyen form ile eşleşmiyor'));
 await renderer.act(async()=>tree.unmount());
});

test('patient-profile appointment verifies its patient and uses the full common program form',async()=>{
 const saved=[];const Editor=component('NativeProgramEditor',{saveProgramEvent:async(_token,payload)=>{saved.push(payload);return{id:7,...payload,start_local:payload.start_at}}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialPatientId:8,onSaved(){},onClose(){}}));await tick()});
 assert.equal(tree.root.findByType('NativePatientSelect').props.value.id,8);
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(saved[0].patient_id,8);assert.equal(saved[0].event_type,'APPOINTMENT');assert.equal(saved[0].end_at,'2030-01-07T10:30');
 await renderer.act(async()=>tree.unmount());
});

test('overlap advice needs an explicit confirmation before a program mutation',async()=>{
 let choice=0,writes=0;const Editor=component('NativeProgramEditor',{checkProgramConflicts:async()=>({advisory:true,total:1,items:[]}),onAlert:(_title,_message,buttons)=>buttons[choice].onPress(),saveProgramEvent:async(_token,payload)=>{writes++;return{id:7,...payload,start_local:payload.start_at}}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialPatientId:8,onSaved(){},onClose(){}}));await tick()});
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());assert.equal(writes,0);
 choice=1;
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());assert.equal(writes,1);
 await renderer.act(async()=>tree.unmount());
});

test('calendar switches to the real month grid and opens the shared editor',async()=>{
 const calls=[];const Program=component('NativeProgram',{getProgram:async(_token,view,day)=>{calls.push({view,day});return page(view)}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'one',userId:1}))});
 await renderer.act(async()=>button(tree,'Ay').props.onPress());
 assert.equal(calls.at(-1).view,'month');
 assert.equal(tree.root.findAllByType('Pressable').filter(node=>typeof node.props.accessibilityLabel==='string'&&node.props.accessibilityLabel.includes('kayıt')).length,42);
 await renderer.act(async()=>button(tree,'＋').props.onPress());
 assert.equal(tree.root.findByType('NativeProgramEditor').props.page.view,'month');
 await renderer.act(async()=>tree.unmount());
});


test('program API requests opaque cursors and rejects malformed continuation tokens',async()=>{
 const api=require('../src/programApi.ts'),original=global.fetch,cursor='program-cursor-token-00000001';
 try{
  let url='';
  global.fetch=async(path)=>{url=String(path);return new Response(JSON.stringify({...page('today'),next_cursor:null}),{status:200})};
  await api.getProgram('token','today','2030-01-07',cursor);
  assert.ok(url.includes('cursor='+cursor));
  global.fetch=async()=>new Response(JSON.stringify({...page('today'),next_cursor:'invalid!'}),{status:200});
  await assert.rejects(()=>api.getProgram('token','today','2030-01-07'),/geçersiz takvim/);
  const malformedDays=page('today');malformedDays.days[0]={...malformedDays.days[0],event_types:['CLASS','CLINIC','EXAM','TASK']};
  global.fetch=async()=>new Response(JSON.stringify(malformedDays),{status:200});
  await assert.rejects(()=>api.getProgram('token','today','2030-01-07'),/geçersiz takvim/);
 }finally{global.fetch=original}
});

test('native calendar follows the snapshot cursor and appends pages without duplicates',async()=>{
 const calls=[];
 const occurrence=id=>({key:id+':2030-01-07T10:00:00+03:00',event_id:id,event_type:'TASK',title:'Synthetic '+id,status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'',patient_id:null,patient_name:null,location:null,notes:null,recurrence_rule:'NONE'});
 const first={...page(),items:Array.from({length:50},(_,i)=>occurrence(100+i)),total:100,next_offset:50,next_cursor:'program-cursor-token-00000001'};
 const second={...page(),items:Array.from({length:50},(_,i)=>occurrence(150+i)),total:100,next_offset:null,next_cursor:null};
 const Program=component('NativeProgram',{getProgram:async(_token,_view,_day,cursor,offset)=>{calls.push({cursor,offset});return cursor?second:first}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 assert.equal(tree.root.findByType('FlatList').props.data.length,50);
 await renderer.act(async()=>button(tree,'Diğer kayıtlar').props.onPress());
 await renderer.act(async()=>tick());
 assert.equal(calls.length,2);
 assert.equal(calls[1].cursor,'program-cursor-token-00000001');
 assert.equal(calls[1].offset,0);
 const items=tree.root.findByType('FlatList').props.data;
 assert.equal(items.length,100);
 assert.equal(new Set(items.map(item=>item.key)).size,100);
 await renderer.act(async()=>tree.unmount());
});

test('native calendar retains offset pagination only for an older backend without cursor metadata',async()=>{
 const calls=[];
 const legacy={...page(),next_cursor:undefined,next_offset:50};
 const next={...page(),next_cursor:undefined,next_offset:null};
 const Program=component('NativeProgram',{getProgram:async(_token,_view,_day,cursor,offset)=>{calls.push({cursor,offset});return offset?next:legacy}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 await renderer.act(async()=>button(tree,'Diğer kayıtlar').props.onPress());
 await renderer.act(async()=>tick());
 assert.equal(calls[1].cursor,undefined);
 assert.equal(calls[1].offset,50);
 await renderer.act(async()=>tree.unmount());
});


test('native calendar stops stale cursor retries after 409 and requires a full refresh',async()=>{
 let calls=0;
 const first={...page(),next_offset:50,next_cursor:'program-cursor-token-00000001'};
 const refreshed={...page('week','Fresh calendar'),next_offset:null,next_cursor:null};
 const conflict=Object.assign(new Error('Takvim bu sırada değişti. Yenileyin.'),{status:409});
 const Program=component('NativeProgram',{getProgram:async()=>{calls++;if(calls===1)return first;if(calls===2)throw conflict;return refreshed}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 assert.ok(button(tree,'Diğer kayıtlar'));
 await renderer.act(async()=>button(tree,'Diğer kayıtlar').props.onPress());
 await renderer.act(async()=>tick());
 assert.equal(calls,2);
 assert.equal(button(tree,'Diğer kayıtlar'),undefined);
 assert.ok(button(tree,'Programı Yenile'));
 await renderer.act(async()=>button(tree,'Programı Yenile').props.onPress());
 await renderer.act(async()=>tick());
 assert.equal(calls,3);
 assert.equal(tree.root.findByType('FlatList').props.data[0].title,'Fresh calendar');
 await renderer.act(async()=>tree.unmount());
});


test('native month grid renders the web event-type dots and overflow marker',async()=>{
 const month=page('month');
 month.days[0]={...month.days[0],event_types:['CLASS','CLINIC','EXAM'],has_more:true,count:5};
 const Program=component('NativeProgram',{getProgram:async(_token,view)=>view==='month'?month:page('week')});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 await renderer.act(async()=>button(tree,'Ay').props.onPress());
 await renderer.act(async()=>tick());
 for(const type of ['CLASS','CLINIC','EXAM'])assert.equal(tree.root.findAllByProps({testID:'program-month-dot-'+type+'-2030-01-07'}).length,1);
 assert.equal(tree.root.findAllByProps({testID:'program-month-dot-more-2030-01-07'}).length,1);
 await renderer.act(async()=>tree.unmount());
});


test('native copy sheet excludes the source date like the web copy form',async()=>{
 const Program=component('NativeProgram',{getProgram:async()=>page()});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 await renderer.act(async()=>button(tree,'İşlemler').props.onPress());
 await renderer.act(async()=>button(tree,'Günlere Kopyala').props.onPress());
 const modal=tree.root.findByType('Modal');
 const modalText=text(modal);
 assert.ok(!modalText.includes('07.01.2030'));
 assert.ok(modalText.includes('08.01.2030'));
 await renderer.act(async()=>tree.unmount());
});

test('native editor mirrors web title copy and caps location at 160 characters',async()=>{
 const Editor=component('NativeProgramEditor',{saveProgramEvent:async(_token,payload)=>({id:7,...payload,start_local:payload.start_at})});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialType:'CLASS',onSaved(){},onClose(){}}));await tick()});
 const titleInput=tree.root.findByProps({accessibilityLabel:'Program başlığı'});
 assert.equal(titleInput.props.placeholder,'Örn. Ortodonti');
 assert.ok(tree.root.findAllByType('Text').some(node=>text(node)==='Ders adı'));
 await renderer.act(async()=>button(tree,'Konum, tekrar ve notlar').props.onPress());
 const locationInput=tree.root.findByProps({accessibilityLabel:'Program konumu'});
 assert.equal(locationInput.props.maxLength,160);
 await renderer.act(async()=>tree.unmount());
});


test('uncertain program edit verifies the server and closes only when the saved fields match',async()=>{
 const original={id:7,event_type:'APPOINTMENT',title:'Old visit',status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:null,patient_name:null,location:'',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 const updated={...original,title:'Updated visit'};
 let reads=0,writes=0,saved=0;
 const Editor=component('NativeProgramEditor',{
  getProgramEvent:async()=>{reads++;return reads===1?original:updated},
  checkProgramConflicts:async()=>({advisory:true,total:0,items:[]}),
  saveProgramEvent:async()=>{writes++;throw Object.assign(new Error('timeout'),{status:408})}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),eventId:7,onSaved(){saved++},onClose(){}}));await tick()});
 await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'Program başlığı'}).props.onChangeText('Updated visit'));
 await renderer.act(async()=>button(tree,'Değişiklikleri Kaydet').props.onPress());
 assert.equal(writes,1);
 assert.ok(button(tree,'Değişikliği sunucuda doğrula'));
 await renderer.act(async()=>button(tree,'Değişikliği sunucuda doğrula').props.onPress());
 assert.equal(reads,2);
 assert.equal(saved,1);
 await renderer.act(async()=>tree.unmount());
});

test('uncertain program edit does not claim success when the server still has old values',async()=>{
 const original={id:7,event_type:'APPOINTMENT',title:'Old visit',status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:null,patient_name:null,location:'',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 let reads=0,writes=0,saved=0;
 const Editor=component('NativeProgramEditor',{
  getProgramEvent:async()=>{reads++;return original},
  checkProgramConflicts:async()=>({advisory:true,total:0,items:[]}),
  saveProgramEvent:async()=>{writes++;throw Object.assign(new Error('timeout'),{status:408})}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),eventId:7,onSaved(){saved++},onClose(){}}));await tick()});
 await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'Program başlığı'}).props.onChangeText('Updated visit'));
 await renderer.act(async()=>button(tree,'Değişiklikleri Kaydet').props.onPress());
 await renderer.act(async()=>button(tree,'Değişikliği sunucuda doğrula').props.onPress());
 assert.equal(reads,2);
 assert.equal(saved,0);
 assert.equal(tree.root.findByProps({accessibilityLabel:'Program başlığı'}).props.value,'Updated visit');
 assert.ok(tree.root.findAllByType('Text').some(node=>text(node).includes('eşleşmiyor')));
 assert.equal(button(tree,'Değişiklikleri Kaydet').props.disabled,false);
 await renderer.act(async()=>tree.unmount());
});


test('uncertain calendar action stays locked until the exact server event state is verified',async()=>{
 let reads=0,actions=0,verifications=0,clears=0;
 const timeout=Object.assign(new Error('network timeout'),{status:408});
 const Program=component('NativeProgram',{
  getProgram:async()=>{reads++;return page('week','Fresh server calendar');},
  programAction:async()=>{actions++;throw timeout},
  verifyProgramAction:async()=>{verifications++;return verifications===1?'UNKNOWN':'APPLIED';},
  saveProgramActionIntent:async()=>{},
  clearProgramActionIntent:async()=>{clears++;}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 await renderer.act(async()=>button(tree,'İşlemler').props.onPress());
 await renderer.act(async()=>button(tree,'Tamamlandı').props.onPress());
 assert.equal(actions,1);
 assert.ok(button(tree,'İşlemi sunucuda doğrula'));
 await renderer.act(async()=>button(tree,'İşlemi sunucuda doğrula').props.onPress());
 assert.equal(verifications,1);
 assert.ok(button(tree,'İşlemi sunucuda doğrula'));
 await renderer.act(async()=>button(tree,'İşlemi sunucuda doğrula').props.onPress());
 assert.equal(verifications,2);
 assert.equal(clears,1);
 assert.equal(reads,2);
 assert.equal(button(tree,'İşlemi sunucuda doğrula'),undefined);
 assert.equal(tree.root.findByType('FlatList').props.data[0].title,'Fresh server calendar');
 await renderer.act(async()=>tree.unmount());
});

test('restored pending Program action is verified before the calendar unlocks',async()=>{
 const intent={version:1,action:'delete',event_id:1};
 let verifications=0,clears=0;
 const Program=component('NativeProgram',{
  getProgram:async()=>page(),
  loadProgramActionIntent:async()=>intent,
  verifyProgramAction:async(_token,value)=>{verifications++;assert.deepEqual(value,intent);return 'APPLIED';},
  clearProgramActionIntent:async(_userId,value)=>{clears++;assert.deepEqual(value,intent);}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 assert.ok(button(tree,'İşlemi sunucuda doğrula'));
 await renderer.act(async()=>button(tree,'İşlemi sunucuda doğrula').props.onPress());
 assert.equal(verifications,1);
 assert.equal(clears,1);
 assert.equal(button(tree,'İşlemi sunucuda doğrula'),undefined);
 await renderer.act(async()=>tree.unmount());
});

test('a confirmed not-applied Program action unlocks only after its intent is cleared',async()=>{
 let actions=0,clears=0;
 const timeout=Object.assign(new Error('network timeout'),{status:408});
 const Program=component('NativeProgram',{
  getProgram:async()=>page(),
  programAction:async()=>{actions++;throw timeout},
  verifyProgramAction:async()=> 'NOT_APPLIED',
  saveProgramActionIntent:async()=>{},
  clearProgramActionIntent:async()=>{clears++;}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 await renderer.act(async()=>button(tree,'İşlemler').props.onPress());
 await renderer.act(async()=>button(tree,'Tamamlandı').props.onPress());
 assert.ok(button(tree,'İşlemi sunucuda doğrula'));
 await renderer.act(async()=>button(tree,'İşlemi sunucuda doğrula').props.onPress());
 assert.equal(clears,1);
 assert.equal(button(tree,'İşlemi sunucuda doğrula'),undefined);
 assert.equal(button(tree,'Tamamlandı').props.disabled,false);
 await renderer.act(async()=>tree.unmount());
});

test('copy verification follows the snapshot cursor to find a later target-day page',async()=>{
 const api=require('../src/programApi.ts'),original=global.fetch,cursor='program-cursor-token-00000001';
 const source={id:1,event_type:'APPOINTMENT',title:'Synthetic source',status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:8,patient_name:'Synthetic',location:'Clinic',notes:'',reminder_minutes:'30',recurrence_rule:'NONE',recurrence_until:''};
 const occurrence=(id,title='Other')=>({key:id+':2030-01-08T09:00',event_id:id,event_type:'TASK',title,status:'ACTIVE',start_local:'2030-01-08T09:00',end_local:'2030-01-08T09:30',patient_id:null,patient_name:null,location:null,notes:null,recurrence_rule:'NONE'});
 const first={...page('today'),focus_date:'2030-01-08',days:[{date:'2030-01-08',label:'8',in_month:true,count:51,event_types:[],has_more:false}],copy_days:Array.from({length:7},(_,i)=>({date:new Date(Date.UTC(2030,0,8+i)).toISOString().slice(0,10),label:'Gün'})),items:Array.from({length:50},(_,i)=>occurrence(100+i)),total:51,next_cursor:cursor,next_offset:null};
 const target={...occurrence(999,'Synthetic source'),event_type:'APPOINTMENT',start_local:'2030-01-08T10:00',end_local:'2030-01-08T10:30',patient_id:8,location:'Clinic',notes:''};
 const second={...first,items:[target],next_cursor:null,next_offset:null};
 try{
  const calls=[];
  global.fetch=async(url)=>{const value=String(url);calls.push(value);if(value.includes('/program/events/1'))return new Response(JSON.stringify({event:source}),{status:200});if(value.includes('cursor='+cursor))return new Response(JSON.stringify(second),{status:200});return new Response(JSON.stringify(first),{status:200});};
  const result=await api.verifyProgramAction('token',{version:1,action:'copy',event_id:1,days:['2030-01-08']});
  assert.equal(result,'APPLIED');
  assert.equal(calls.length,3);
 }finally{global.fetch=original}
});



test('transient conflict-check outage requires explicit confirmation before web-parity save',async()=>{
 let choice=0,alerts=0,writes=0;
 const Editor=component('NativeProgramEditor',{
  checkProgramConflicts:async()=>{throw Object.assign(new Error('temporary outage'),{status:503})},
  onAlert:(_title,_message,buttons)=>{alerts++;buttons[choice].onPress()},
  saveProgramEvent:async(_token,payload)=>{writes++;return{id:7,...payload,start_local:payload.start_at}}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialPatientId:8,onSaved(){},onClose(){}}));await tick()});
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(alerts,1);assert.equal(writes,0);
 choice=1;
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(alerts,2);assert.equal(writes,1);
 await renderer.act(async()=>tree.unmount());
});

test('authentication and validation failures never bypass the conflict-check gate',async()=>{
 let alerts=0,writes=0;
 const Editor=component('NativeProgramEditor',{
  checkProgramConflicts:async()=>{throw Object.assign(new Error('unauthorized'),{status:401})},
  onAlert:()=>{alerts++},
  saveProgramEvent:async(_token,payload)=>{writes++;return{id:7,...payload,start_local:payload.start_at}}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialPatientId:8,onSaved(){},onClose(){}}));await tick()});
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(alerts,0);assert.equal(writes,0);
 assert.ok(tree.root.findAllByType('Text').some(node=>text(node).includes('unauthorized')));
 await renderer.act(async()=>tree.unmount());
});


test('malformed conflict-advice responses do not become a transient bypass',async()=>{
 let alerts=0,writes=0;
 const Editor=component('NativeProgramEditor',{
  checkProgramConflicts:async()=>{throw new Error('invalid conflict response')},
  onAlert:()=>{alerts++},
  saveProgramEvent:async(_token,payload)=>{writes++;return{id:7,...payload,start_local:payload.start_at}}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialPatientId:8,onSaved(){},onClose(){}}));await tick()});
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(alerts,0);assert.equal(writes,0);
 assert.ok(tree.root.findAllByType('Text').some(node=>text(node).includes('invalid conflict response')));
 await renderer.act(async()=>tree.unmount());
});


test('week calendar groups entries under date headings like web',async()=>{
 const data=page('week');
 const base=data.items[0];
 data.items=[
  {...base,key:'1:2030-01-07T10:00',event_id:1,start_local:'2030-01-07T10:00',title:'First day morning'},
  {...base,key:'2:2030-01-07T11:00',event_id:2,start_local:'2030-01-07T11:00',title:'First day afternoon'},
  {...base,key:'3:2030-01-08T09:00',event_id:3,start_local:'2030-01-08T09:00',title:'Second day'},
 ];
 data.total=3;
 const Program=component('NativeProgram',{getProgram:async()=>data});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 const headings=tree.root.findAll(node=>typeof node.props.testID==='string'&&node.props.testID.startsWith('program-day-heading-'));
 assert.deepEqual(headings.map(node=>node.props.testID),[
  'program-day-heading-2030-01-07',
  'program-day-heading-2030-01-08',
 ]);
 assert.equal(tree.root.findAllByProps({testID:'program-day-heading-2030-01-07'}).length,1,'same-day events share one heading');
 assert.ok(text(tree.toJSON()).includes('First day afternoon'));
 assert.ok(text(tree.toJSON()).includes('Second day'));
 await renderer.act(async()=>tree.unmount());
});


test('week inline-add actions appear after each complete day group and carry the chosen date into the editor',async()=>{
 const data=page('week'),base=data.items[0];
 data.items=[
  {...base,key:'1:2030-01-07T10:00',event_id:1,start_local:'2030-01-07T10:00',title:'First day morning'},
  {...base,key:'2:2030-01-07T11:00',event_id:2,start_local:'2030-01-07T11:00',title:'First day afternoon'},
  {...base,key:'3:2030-01-08T09:00',event_id:3,start_local:'2030-01-08T09:00',title:'Second day'}
 ];
 data.total=3;
 const Program=component('NativeProgram',{getProgram:async()=>data});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 const addButtons=tree.root.findAllByType('Pressable').filter(node=>node.findAllByType('Text').some(child=>text(child)==='＋ Ders ekle'));
 assert.equal(addButtons.length,2,'one inline add follows each completed day group');
 await renderer.act(async()=>addButtons[1].props.onPress());
 const editor=tree.root.findByType('NativeProgramEditor');
 assert.equal(editor.props.initialType,'CLASS');
 assert.equal(editor.props.initialDate,'2030-01-08');
 await renderer.act(async()=>tree.unmount());
});

test('week inline add waits for the final cursor page before exposing the last date action',async()=>{
 const data=page('week');
 data.next_cursor='program-cursor-token-00000001';
 data.next_offset=null;
 data.total=51;
 const Program=component('NativeProgram',{getProgram:async()=>data});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 const addButtons=tree.root.findAllByType('Pressable').filter(node=>node.findAllByType('Text').some(child=>text(child)==='＋ Ders ekle'));
 assert.equal(addButtons.length,0,'the current page tail may continue the same date group');
 await renderer.act(async()=>tree.unmount());
});

test('native Program editor applies the inline-add date and preserves the suggested time',async()=>{
 const Editor=component('NativeProgramEditor',{});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',userId:1,page:page(),initialType:'CLASS',initialDate:'2030-01-09',onSaved(){},onClose(){}}));await tick()});
 const startDate=tree.root.findAllByType('NativeDateField').find(node=>node.props.label==='Başlangıç tarihi');
 const endDate=tree.root.findAllByType('NativeDateField').find(node=>node.props.label==='Bitiş tarihi');
 const startTime=tree.root.findAllByType('NativeTimeField').find(node=>node.props.label==='Başlangıç saati');
 assert.equal(startDate.props.value,'2030-01-09');
 assert.equal(endDate.props.value,'2030-01-09');
 assert.equal(startTime.props.value,'10:00');
 await renderer.act(async()=>tree.unmount());
});


test('web patient link in a Program card opens the matching native patient profile',async()=>{
 const calls=[];
 const data=page();
 data.items=[{...data.items[0],patient_id:8,patient_name:'Synthetic Patient'}];
 const Program=component('NativeProgram',{getProgram:async()=>data,onNavigate:(...args)=>calls.push(args)});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 const link=tree.root.findByProps({accessibilityLabel:'Hasta profilini aç: Synthetic Patient'});
 assert.equal(link.props.accessibilityRole,'link');
 await renderer.act(async()=>link.props.onPress());
 assert.equal(calls.length,1);assert.equal(calls[0][0],'AppTabs');assert.equal(calls[0][1].screen,'Patients');assert.equal(calls[0][1].params.screen,'PatientDetail');assert.equal(calls[0][1].params.params.id,8);
 await renderer.act(async()=>tree.unmount());
});

test('Program cards mirror web event type, recurrence, completion and today labels',async()=>{
 const data=page();
 data.items=[{...data.items[0],status:'COMPLETED',recurrence_rule:'WEEKLY'}];
 const Program=component('NativeProgram',{getProgram:async()=>data});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'token',userId:1}));await tick()});
 assert.equal(tree.root.findAllByProps({testID:'program-event-type-1'}).length,1);
 assert.equal(tree.root.findAllByProps({testID:'program-event-status-1'}).length,1);
 assert.equal(tree.root.findAllByProps({testID:'program-day-today-2030-01-07'}).length,1);
 assert.ok(text(tree.toJSON()).includes('Hasta / Randevu'));
 assert.ok(text(tree.toJSON()).includes('Her hafta'));
 assert.ok(text(tree.toJSON()).includes('Tamamlandı'));
 assert.ok(text(tree.toJSON()).includes('Bugün'));
 await renderer.act(async()=>tree.unmount());
});


test('Program session render identity never exposes bearer credentials in renderer keys',()=>{
 const {resolveSessionRenderIdentity}=require('../src/sessionRenderKey.ts');
 const secret='Bearer_opaque_program_session_token_1234567890';
 const first=resolveSessionRenderIdentity(null,secret+':7:week:2030-01-07');
 assert.ok(first.key.startsWith('dai-session-'));
 assert.equal(first.key.includes(secret),false);
 const same=resolveSessionRenderIdentity(first,secret+':7:week:2030-01-07');
 assert.equal(same.key,first.key);
 const changedAccount=resolveSessionRenderIdentity(same,'rotated-session-token:7:week:2030-01-07');
 assert.notEqual(changedAccount.key,first.key);
 assert.equal(changedAccount.key.includes('rotated-session-token'),false);
});

test('Program calendar and editor keep async response ownership on opaque session keys',()=>{
 const calendar=fs.readFileSync(require.resolve('../src/NativeProgram.tsx'),'utf8');
 const editor=fs.readFileSync(require.resolve('../src/NativeProgramEditor.tsx'),'utf8');
 assert.match(calendar,/const scope=useSessionRenderKey\(\x60\$\{token\}:\$\{userId\}:\$\{view\}:\$\{day\}\x60\)/);
 assert.match(editor,/const scopeKey=useSessionRenderKey\(\x60\$\{token\}:\$\{userId\}:\$\{eventId\|\|0\}:\$\{initialPatientId\|\|0\}\x60\)/);
 assert.match(editor,/scope\.current=scopeKey/);
 assert.doesNotMatch(calendar,/data\?\.scope===\x60\$\{token\}/);
 assert.doesNotMatch(editor,/scope=useRef\(\x60\$\{token\}/);
});
