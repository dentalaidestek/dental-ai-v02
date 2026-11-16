const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
let focused=true,lastEvent=null,appListeners=[];
function chartComponent(api){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText;
 const native={AppState:{addEventListener:(_event,listener)=>{appListeners.push(listener);return{remove(){appListeners=appListeners.filter(x=>x!==listener)}}}},...Object.fromEntries(['ActivityIndicator','Image','Pressable','ScrollView','Text','TextInput','View'].map(name=>[name,name]))};
 const exports={};
 vm.runInNewContext(code,{exports,require:name=>{
  if(name==='react')return{...React,default:React};
  if(name==='react-native')return native;
  if(name==='@react-navigation/native')return{useNavigation:()=>({getParent:()=>({getParent:()=>({navigate(){}})})}),useIsFocused:()=>focused};
  if(name==='./api')return api;
  if(name==='./realtime')return{useRealtime:()=>({lastEvent})};
  if(name==='./toothChartPresentation')return require('../src/toothChartPresentation.ts');
  if(name==='./NativeToothVisual'||name==='./NativeDateField'||name==='./NativePatientHistory')return{default:'Child'};
  throw Error('unexpected import '+name);
 }});
 return exports.default;
}
const patient=(id,firstName='Synthetic',status='HEALTHY',age=35)=>({patient:{id,first_name:firstName,last_name:'Patient',age,anonymous_id:'SYN-'+id},teeth:[{id:1,tooth_number:'11',status,note:'saved note'}],surfaces:[],treatments:[],media:[]});
const flat=node=>typeof node==='string'?node:Array.isArray(node)?node.map(flat).join(''):node?.children?node.children.map(flat).join(''):'';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r});return{promise,resolve};}

test('patient summary handles names, infant age and incomplete records',()=>{
 const {toothChartPatientSummary}=require('../src/toothChartPresentation.ts');
 assert.equal(toothChartPatientSummary({first_name:'  Ada ',last_name:'Dentist',age:0}),'Ada Dentist · 0 yaş');
 assert.equal(toothChartPatientSummary({first_name:'Ada',last_name:'',age:null}),'Ada');
 assert.equal(toothChartPatientSummary({first_name:' ',last_name:null,age:4}),'İsimsiz hasta · 4 yaş');
 assert.equal(toothChartPatientSummary({first_name:'Ada',age:4.5}),'Ada');
});

test('native tooth chart displays the selected patient identity like the web chart',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const Chart=chartComponent({getPatient:async()=>patient(8,'Ada', 'HEALTHY',0)});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const identity=tree.root.findAllByType('Text').find(node=>String(node.props.accessibilityLabel||'').startsWith('Hasta '));
 assert.ok(identity,'patient identity must be visible above the chart');
 assert.equal(flat(identity.children),'Hasta: Ada Patient · 0 yaş');
 await renderer.act(async()=>tree.unmount());
});

test('returning to the chart and foregrounding refresh server data without erasing an unsaved tooth note',async()=>{
 focused=true;lastEvent=null;appListeners=[];let calls=0;
 const Chart=chartComponent({getPatient:async()=>{calls++;return patient(8,calls===1?'Ada':'Ada Güncel',calls===1?'HEALTHY':'CARIES',35)}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await press('Diş 11, Sağlıklı');
 await press('Notlar');
 const note=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Diş notları');
 assert.ok(note);
 await renderer.act(async()=>note.props.onChangeText('Unsaved clinical note'));
 await renderer.act(async()=>{appListeners.slice().forEach(listener=>listener('background'));appListeners.slice().forEach(listener=>listener('active'));await flush()});
 assert.equal(calls,2,'foreground must reload the owned patient chart');
 const currentNote=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Diş notları');
 assert.equal(currentNote.props.value,'Unsaved clinical note','refresh must not replace the unsaved form');
 assert.ok(flat(tree.toJSON()).includes('Ada Güncel'));
 await renderer.act(async()=>tree.unmount());
});

test('overlapping chart refreshes keep the newest patient response',async()=>{
 focused=true;lastEvent=null;appListeners=[];let calls=0;const older=deferred(),newer=deferred();
 const Chart=chartComponent({getPatient:()=>{calls++;if(calls===1)return Promise.resolve(patient(8,'Ada'));if(calls===2)return older.promise;if(calls===3)return newer.promise;throw Error('unexpected extra refresh')}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await renderer.act(async()=>{appListeners.slice().forEach(listener=>listener('active'))});
 assert.equal(calls,2);
 await renderer.act(async()=>{lastEvent={event_type:'PATIENT_UPDATED',entity_id:999,payload:{patient_id:8}};tree.update(React.createElement(Chart,{token:'account-a',patientId:8}))});
 assert.equal(calls,3,'patient_id payload must trigger a refresh even when entity_id is not the patient id');
 await renderer.act(async()=>{newer.resolve(patient(8,'Ada New','CARIES'));await flush()});
 await renderer.act(async()=>{older.resolve(patient(8,'Ada Old','HEALTHY'));await flush()});
 const labels=tree.root.findAllByType('Pressable').map(node=>node.props.accessibilityLabel);
 assert.ok(labels.includes('Diş 11, Çürük'),'an older response must not overwrite the newest tooth state');
 assert.ok(flat(tree.toJSON()).includes('Ada New'));
 await renderer.act(async()=>tree.unmount());
});

test('an in-flight background refresh cannot overwrite a confirmed tooth save',async()=>{
 focused=true;lastEvent=null;appListeners=[];let calls=0;const older=deferred();
 const Chart=chartComponent({
  getPatient:()=>{calls++;if(calls===1)return Promise.resolve(patient(8,'Ada','HEALTHY'));if(calls===2)return older.promise;if(calls===3)return Promise.resolve(patient(8,'Ada','CARIES'));throw Error('unexpected extra patient read')},
  updateTooth:async()=>({ok:true})
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{appListeners.slice().forEach(listener=>listener('active'))});
 assert.equal(calls,2);
 await press('Diş 11, Sağlıklı');
 await press('Diş durumu: Çürük');
 await press('Durumu Kaydet');
 assert.equal(calls,3,'successful save must fetch the committed server state');
 await renderer.act(async()=>{older.resolve(patient(8,'Ada','HEALTHY'));await flush()});
 const labels=tree.root.findAllByType('Pressable').map(node=>node.props.accessibilityLabel);
 assert.ok(labels.includes('Diş 11, Çürük'),'a stale pre-save refresh must not replace the saved status');
 await renderer.act(async()=>tree.unmount());
});
