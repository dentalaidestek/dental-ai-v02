const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const text=node=>typeof node==='string'?node:!node?'':(node.children||[]).map(text).join('');
const page=(view='week',title='Synthetic appointment')=>({view,focus_date:'2030-01-07',today:'2030-01-07',timezone:'Europe/Istanbul',previous_day:'2029-12-31',next_day:'2030-01-14',month_title:'Ocak 2030',copy_days:Array.from({length:7},(_,i)=>({date:new Date(Date.UTC(2030,0,7+i)).toISOString().slice(0,10),label:'Pzt'})),days:Array.from({length:view==='month'?42:view==='week'?7:1},(_,i)=>({date:new Date(Date.UTC(2030,0,7+i)).toISOString().slice(0,10),label:'Pzt',in_month:true,count:i?0:1})),items:[{key:'1:2030-01-07T10:00',event_id:1,event_type:'APPOINTMENT',title,status:'ACTIVE',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_id:null,patient_name:null,location:null,notes:null,recurrence_rule:'NONE'}],total:1,next_offset:null,event_types:{APPOINTMENT:'Hasta / Randevu',CLASS:'Ders'},reminders:['NONE','30'],recurrences:['NONE','WEEKLY'],suggested_start_local:'2030-01-07T10:00',suggested_end_local:'2030-01-07T10:30'});
function component(file,api){
 const exports={},native={StyleSheet:{create:x=>x},AppState:{addEventListener:()=>({remove(){}})},BackHandler:{addEventListener:()=>({remove(){}})},Alert:{alert:(...args)=>api.onAlert?.(...args)},...Object.fromEntries(['ActivityIndicator','FlatList','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 native.FlatList=props=>React.createElement('FlatList',props,props.ListHeaderComponent,...(props.data||[]).map(item=>React.createElement(React.Fragment,{key:item.key},props.renderItem?.({item}))),props.ListEmptyComponent&&!(props.data||[]).length?props.ListEmptyComponent:null,props.ListFooterComponent);
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/'+file+'.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true,usePreventRemove:()=>{}}:name==='./programApi'?{checkProgramConflicts:async()=>({advisory:true,total:0,items:[]}),...api}:name==='./programModel'?require('../src/programModel.ts'):name==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'SYNTHETIC',first_name:'Synthetic'}})}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:{default:name.slice(2)}});
 return exports.default;
}
const button=(tree,label)=>tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>text(child)===label));
test('program payload validates real dates, end order and removes stale patient/recurrence fields',()=>{
 const {programPayload,validWallTime,wallTimeLabel}=require('../src/programModel.ts');
 const base={event_type:'APPOINTMENT',title:'Test visit',start_at:'2030-01-07T10:00',end_at:'2030-01-07T10:30',patient_id:8,location:'',notes:'',reminder_minutes:'NONE',recurrence_rule:'NONE',recurrence_until:'2029-01-01'};
 assert.equal(programPayload(base).patient_id,8);assert.equal(programPayload({...base,event_type:'CLASS'}).patient_id,undefined);assert.equal(programPayload(base).recurrence_until,'');
 assert.throws(()=>programPayload({...base,end_at:'2030-01-07T09:59'}));assert.throws(()=>programPayload({...base,recurrence_rule:'WEEKLY'}));
 assert.equal(validWallTime('2025-02-29T10:00'),false);assert.equal(validWallTime('2030-01-07T24:00'),false);assert.equal(wallTimeLabel(base.start_at),'10:00');
});
test('program form sends a selected record once despite duplicate taps and disables reminders explicitly',async()=>{
 const calls=[];let release;const Editor=component('NativeProgramEditor',{saveProgramEvent:async(_token,payload)=>{calls.push(payload);return new Promise(resolve=>{release=()=>resolve({id:7,...payload,start_local:payload.start_at})})}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',page:page(),onSaved(){},onClose(){}}))});
 await renderer.act(async()=>{tree.root.findByProps({accessibilityLabel:'Program başlığı'}).props.onChangeText('Actual native appointment');tree.root.findByType('NativePatientSelect').props.onChange({id:8,anonymous_id:'SYNTHETIC',first_name:'Synthetic'})});
 await renderer.act(async()=>button(tree,'Hatırlatma yok').props.onPress());
 await renderer.act(async()=>{const save=button(tree,'Programa Ekle');save.props.onPress();save.props.onPress()});
 assert.equal(calls.length,1);assert.equal(calls[0].patient_id,8);assert.equal(calls[0].reminder_minutes,'NONE');
 await renderer.act(async()=>release());await renderer.act(async()=>tree.unmount());
});
test('calendar hides previous account data while the next account request is pending',async()=>{
 let resolve;const Program=component('NativeProgram',{getProgram:async token=>token==='one'?page('week','Private first account'):new Promise(r=>{resolve=r})});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'one'}))});
 assert.equal(tree.root.findByType('FlatList').props.data[0].title,'Private first account');
 await renderer.act(async()=>tree.update(React.createElement(Program,{token:'two'})));
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

test('patient-profile appointment verifies its patient and uses the full common program form',async()=>{
 const saved=[];const Editor=component('NativeProgramEditor',{saveProgramEvent:async(_token,payload)=>{saved.push(payload);return{id:7,...payload,start_local:payload.start_at}}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',page:page(),initialPatientId:8,onSaved(){},onClose(){}}))});
 assert.equal(tree.root.findByType('NativePatientSelect').props.value.id,8);
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());
 assert.equal(saved[0].patient_id,8);assert.equal(saved[0].event_type,'APPOINTMENT');assert.equal(saved[0].end_at,'2030-01-07T10:30');
 await renderer.act(async()=>tree.unmount());
});

test('overlap advice needs an explicit confirmation before a program mutation',async()=>{
 let choice=0,writes=0;const Editor=component('NativeProgramEditor',{checkProgramConflicts:async()=>({advisory:true,total:1,items:[]}),onAlert:(_title,_message,buttons)=>buttons[choice].onPress(),saveProgramEvent:async(_token,payload)=>{writes++;return{id:7,...payload,start_local:payload.start_at}}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Editor,{token:'token',page:page(),initialPatientId:8,onSaved(){},onClose(){}}))});
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());assert.equal(writes,0);
 choice=1;
 await renderer.act(async()=>button(tree,'Programa Ekle').props.onPress());assert.equal(writes,1);
 await renderer.act(async()=>tree.unmount());
});

test('calendar switches to the real month grid and opens the shared editor',async()=>{
 const calls=[];const Program=component('NativeProgram',{getProgram:async(_token,view,day)=>{calls.push({view,day});return page(view)}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Program,{token:'one'}))});
 await renderer.act(async()=>button(tree,'Ay').props.onPress());
 assert.equal(calls.at(-1).view,'month');
 assert.equal(tree.root.findAllByType('Pressable').filter(node=>typeof node.props.accessibilityLabel==='string'&&node.props.accessibilityLabel.includes('kayıt')).length,42);
 await renderer.act(async()=>button(tree,'＋').props.onPress());
 assert.equal(tree.root.findByType('NativeProgramEditor').props.page.view,'month');
 await renderer.act(async()=>tree.unmount());
});
