const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
function component(api,file='NativePatientProfile'){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/'+file+'.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const native={StyleSheet:{create:s=>s},AppState:{addEventListener:()=>({remove(){}})},Platform:{OS:'android'},Alert:{alert(){}},...Object.fromEntries(['Modal','ActivityIndicator','KeyboardAvoidingView','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(s=>[s,s]))},exports={};
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./api'?api:name==='./clinicalDate'?{clinicalDate:(y,m,d)=>`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`,parseClinicalDate:value=>/^\d{4}-\d{2}-\d{2}$/.test(value)}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:{default:'Child'}});
 return exports.default;
}
const actions=Object.fromEntries(['chart','analysis','appointment','expert','voice','analysisResult','deleted'].map(k=>[k,()=>{}]));
const patient=id=>({patient:{id,first_name:'Synthetic'+id,last_name:'Test',anonymous_id:'SYN-'+id,chief_complaint:'Complaint'},teeth:[],surfaces:[],treatments:[{id:1,treatment_name:'Root canal',material:'Synthetic material',result:'Synthetic result',doctor_note:'Synthetic note'}],media:[]});
const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?node.children.map(text).join(''):'';
test('profile follows web section order, expands patient info, and preserves complete treatment details',async()=>{
 const Profile=component({getPatient:async()=>patient(8)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const content=text(tree.toJSON());
 assert.ok(content.includes('Synthetic8'));assert.ok(content.includes('Hasta Bilgileri'));assert.ok(content.includes('Tedavi Geçmişi'));
 for(const value of ['Synthetic material','Synthetic result','Synthetic note'])assert.ok(content.includes(value));
 assert.equal(tree.root.findAllByType('TextInput').length,0,'patient information starts collapsed like web');
 const toggle=tree.root.findAllByType('Pressable').find(n=>n.props.accessibilityState?.expanded===false);
 await renderer.act(async()=>toggle.props.onPress());
 assert.ok(tree.root.findAllByType('TextInput').some(n=>n.props.accessibilityLabel==='Adres'));
 await renderer.act(async()=>tree.unmount());
});
test('changing account and patient hides previous clinical content before pending requests resolve',async()=>{
 let resolve;const Profile=component({getPatient:async(token,id)=>id===8?patient(8):new Promise(r=>{resolve=r})});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await renderer.act(async()=>tree.update(React.createElement(Profile,{token:'two',patientId:9,actions})));
 assert.ok(!text(tree.toJSON()).includes('Synthetic8'));
 await renderer.act(async()=>{resolve(patient(9))});
 assert.ok(text(tree.toJSON()).includes('Synthetic9'));assert.ok(!text(tree.toJSON()).includes('Old account failed'),'stale failure must not leak into next account');
 await renderer.act(async()=>tree.unmount());
});
test('appointment created from a patient profile submits the actual selected id and local date/time',async()=>{
 let submitted,saved=0;const Form=component({getPatient:async()=>patient(8),createSchedule:async(_token,payload)=>{submitted=payload}},'NativePatientAppointment');let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Form,{token:'one',patientId:8,onSaved:()=>saved++}))});
 const save=tree.root.findAllByType('Pressable').find(n=>text(n.toJSON?.()||{children:n.findAllByType('Text').flatMap(t=>t.children)})==='Randevuyu Kaydet');
 assert.ok(save);
 await renderer.act(async()=>save.props.onPress());
 assert.equal(submitted.patient_id,8);assert.equal(submitted.event_type,'APPOINTMENT');
 assert.match(submitted.start_at,/^\d{4}-\d{2}-\d{2}T09:00$/);assert.equal(saved,1);
 await renderer.act(async()=>tree.unmount());
});

test('patient switch releases a pending mutation lock without leaking old account state',async()=>{
 let rejectOld;const calls=[];
 const Profile=component({
  getPatient:async(_token,id)=>patient(id),
  editPatient:async(token,id)=>{calls.push([token,id]);if(id===8)await new Promise((_resolve,reject)=>{rejectOld=reject})}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 let oldSave;
 await renderer.act(async()=>{const save=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Değişiklikleri Kaydet')));assert.ok(save);oldSave=save.props.onPress()});
 assert.deepEqual(calls,[['one',8]]);
 await renderer.act(async()=>{tree.update(React.createElement(Profile,{token:'two',patientId:9,actions}))});
 await press('Hasta Bilgileri');
 await press('Değişiklikleri Kaydet');
 assert.deepEqual(calls,[['one',8],['two',9]],'new patient must not inherit prior pending mutation lock');
 await renderer.act(async()=>{rejectOld(new Error('Old account failed'));await oldSave});
 assert.ok(text(tree.toJSON()).includes('Synthetic9'));
 await renderer.act(async()=>tree.unmount());
});
