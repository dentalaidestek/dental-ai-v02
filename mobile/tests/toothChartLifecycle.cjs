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
function chartComponent(api,storage=new Map()){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText;
 const native={AppState:{addEventListener:(_event,listener)=>{appListeners.push(listener);return{remove(){appListeners=appListeners.filter(x=>x!==listener)}}}},...Object.fromEntries(['ActivityIndicator','Image','Pressable','ScrollView','Text','TextInput','View'].map(name=>[name,name]))};
 const exports={};let sequence=0;
 const secure={getItemAsync:async key=>storage.has(key)?storage.get(key):null,setItemAsync:async(key,value)=>storage.set(key,value),deleteItemAsync:async key=>storage.delete(key)};
 const crypto={randomUUID:()=>`synthetic-treatment-request-${String(++sequence).padStart(8,"0")}`};
 vm.runInNewContext(code,{exports,require:name=>{
  if(name==='react')return{...React,default:React};
  if(name==='react-native')return native;
  if(name==='@react-navigation/native')return{useNavigation:()=>({getParent:()=>({getParent:()=>({navigate(){}})})}),useIsFocused:()=>focused};
  if(name==='./api')return api;
  if(name==='expo-secure-store')return secure;
  if(name==='expo-crypto')return crypto;
  if(name==='./socialDraft')return{chunkedDraftStore:raw=>raw};
  if(name==='./treatmentMutation')return require('../src/treatmentMutation.ts');
  if(name==='./realtime')return{useRealtime:()=>({lastEvent})};
  if(name==='./toothChartPresentation')return require('../src/toothChartPresentation.ts');
  if(name==='./NativeToothVisual'||name==='./NativeDateField'||name==='./NativePatientHistory')return{default:'Child'};
  throw Error('unexpected import '+name);
 }});
 const Original=exports.default;
 return props=>React.createElement(Original,{userId:1,...props});
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


test('tooth chart persists a treatment request before sending and reuses its key after remount',async()=>{
 focused=true;lastEvent=null;appListeners=[];const storage=new Map(),calls=[];let first=true;
 const api={
  getPatient:async()=>patient(8),
  createTreatment:async(...args)=>{
   calls.push({args,stored:storage.has('dai.treatment.1.8')});
   if(first){first=false;throw Object.assign(new Error('Synthetic network timeout'),{status:503});}
   return{ok:true,treatment_id:9,edit_revision:'d'.repeat(64),replayed:true};
  }
 };
 const press=async(tree,label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 const Chart=chartComponent(api,storage);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press(tree,'Diş 11, Sağlıklı');
 await press(tree,'Tedavi Geçmişi');
 const input=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Tedavi adı');assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Synthetic composite'));
 await press(tree,'Tedavi Kaydı Ekle');
 assert.equal(calls.length,1);
 assert.ok(calls[0].stored,'durable intent must be stored before the network request');
 const originalKey=calls[0].args[3];assert.match(originalKey,/^synthetic-treatment-request-/);
 assert.ok(storage.has('dai.treatment.1.8'),'uncertain result must retain the secure intent');
 assert.ok(tree.root.findAllByType('Pressable').some(node=>node.props.accessibilityLabel==='Bekleyen Tedaviyi Doğrula'));
 await renderer.act(async()=>tree.unmount());

 const Restored=chartComponent(api,storage);
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Restored,{token:'account-a',patientId:8}));await flush()});
 await press(tree,'Bekleyen Tedaviyi Doğrula');
 assert.equal(calls.length,2);
 assert.equal(calls[1].args[3],originalKey,'restart must reuse the exact original idempotency key');
 assert.equal(storage.has('dai.treatment.1.8'),false,'confirmed receipt must clear the secure intent');
 await renderer.act(async()=>tree.unmount());
});

test('tooth chart treatment updates send the stored edit revision and a stable request key',async()=>{
 focused=true;lastEvent=null;appListeners=[];const revision='c'.repeat(64),calls=[];
 const record={id:7,tooth_number:'11',treatment_name:'Old treatment',treatment_date:'2026-11-01',material:'Old material',doctor_note:'Old note',result:'Old result',edit_revision:revision};
 const api={
  getPatient:async()=>({...patient(8),treatments:[record]}),
  updateTreatment:async(...args)=>{calls.push(args);return{ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false};}
 };
 const Chart=chartComponent(api);let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press('Diş 11, Sağlıklı');await press('Tedavi Geçmişi');await press('Düzenle');
 const input=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Tedavi adı');assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Updated treatment'));
 await press('Tedaviyi Güncelle');
 assert.equal(calls.length,1);
 assert.equal(calls[0][2],7);
 assert.equal(calls[0][4].startsWith('synthetic-treatment-request-'),true);
 assert.equal(calls[0][5],revision,'update must use the revision from the selected treatment record');
 assert.ok(!tree.root.findAllByType('Pressable').some(node=>node.props.accessibilityLabel==='Bekleyen Tedaviyi Doğrula'));
 await renderer.act(async()=>tree.unmount());
});


test('tooth chart clears a definitive validation rejection and permits a corrected retry',async()=>{
 focused=true;lastEvent=null;appListeners=[];const storage=new Map(),calls=[];let first=true;
 const api={
  getPatient:async()=>patient(8),
  createTreatment:async(...args)=>{
   calls.push({args,stored:storage.has('dai.treatment.1.8')});
   if(first){first=false;throw Object.assign(new Error('Synthetic validation rejection'),{status:422});}
   return{ok:true,treatment_id:10,edit_revision:'e'.repeat(64),replayed:false};
  }
 };
 const Chart=chartComponent(api,storage);let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press('Diş 11, Sağlıklı');await press('Tedavi Geçmişi');
 const input=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Tedavi adı');assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Synthetic treatment'));
 await press('Tedavi Kaydı Ekle');
 assert.equal(calls.length,1);assert.ok(calls[0].stored);
 assert.equal(storage.has('dai.treatment.1.8'),false,'definitive validation rejection must clear the pending request');
 await press('Tedavi Kaydı Ekle');
 assert.equal(calls.length,2,'clinician can retry after correcting a definitive rejection');
 assert.notEqual(calls[0].args[3],calls[1].args[3],'a rejected intent is replaced with a new request key');
 await renderer.act(async()=>tree.unmount());
});

test('tooth chart refuses to update a legacy treatment without a server revision',async()=>{
 focused=true;lastEvent=null;appListeners=[];let updates=0;
 const legacy={id:4,tooth_number:'11',treatment_name:'Legacy treatment',material:'',doctor_note:'',result:''};
 const Chart=chartComponent({getPatient:async()=>({...patient(8),treatments:[legacy]}),updateTreatment:async()=>{updates++;return{ok:true,treatment_id:4,edit_revision:'f'.repeat(64),replayed:false}}});
 let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press('Diş 11, Sağlıklı');await press('Tedavi Geçmişi');await press('Düzenle');
 assert.equal(updates,0,'update must not be sent without an edit revision');
 assert.ok(flat(tree.toJSON()).includes('Tedavi sürümü alınamadı'));
 await renderer.act(async()=>tree.unmount());
});

test('pending treatment drafts are isolated by authenticated user and patient',async()=>{
 focused=true;lastEvent=null;appListeners=[];const storage=new Map();
 const {parseTreatmentMutationIntent}=require('../src/treatmentMutation.ts');
 const candidate={userId:1,patientId:8,operation:'CREATE',treatmentId:null,requestKey:'synthetic-treatment-request-private-0001',expectedRevision:null,payload:{treatment_name:'Private synthetic draft',tooth_number:'11',treatment_date:'',material:'',doctor_note:'',result:''}};
 const intent=parseTreatmentMutationIntent(JSON.stringify(candidate),1,8);
 storage.set('dai.treatment.1.8',JSON.stringify(intent));
 const Chart=chartComponent({getPatient:async()=>patient(8)},storage);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-b',userId:2,patientId:8}));await flush()});
 assert.equal(tree.root.findAllByType('Pressable').filter(node=>node.props.accessibilityLabel==='Bekleyen Tedaviyi Doğrula').length,0);
 assert.equal(storage.has('dai.treatment.1.8'),true,'another account must neither read nor delete the prior account draft');
 await renderer.act(async()=>tree.unmount());
});
