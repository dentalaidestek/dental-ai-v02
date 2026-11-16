const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
function component(api,file='NativePatientProfile',storage=new Map()){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/'+file+'.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const intentExports={};
 const intentCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/treatmentMutation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 vm.runInNewContext(intentCode,{exports:intentExports,Error,JSON,Date,Number,RegExp});
 const secure={getItemAsync:async key=>storage.get(key)||null,setItemAsync:async(key,value)=>storage.set(key,value),deleteItemAsync:async key=>storage.delete(key)};
 let sequence=0;
 const native={StyleSheet:{create:s=>s},AppState:{addEventListener:()=>({remove(){}})},Platform:{OS:'android'},Alert:{alert(){}},...Object.fromEntries(['Modal','ActivityIndicator','KeyboardAvoidingView','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(s=>[s,s]))},exports={};
 const endpoints={getPatient:async()=>patient(8),createTreatment:async()=>({ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false}),updateTreatment:async()=>({ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false}),...api};
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./api'?endpoints:name==='./clinicalDate'?{clinicalDate:(y,m,d)=>`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`,parseClinicalDate:value=>/^\d{4}-\d{2}-\d{2}$/.test(value)}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='expo-secure-store'?secure:name==='expo-crypto'?{randomUUID:()=>`synthetic-treatment-request-${String(++sequence).padStart(8,'0')}`}:name==='./socialDraft'?{chunkedDraftStore:raw=>raw}:name==='./treatmentMutation'?intentExports:{default:'Child'}});
 const Original=exports.default;
 const Wrapped=props=>React.createElement(Original,{userId:1,...props});
 Wrapped.storage=storage;
 return Wrapped;
}
const actions=Object.fromEntries(['chart','analysis','appointment','expert','voice','analysisResult','deleted'].map(k=>[k,()=>{}]));
const patient=id=>({patient:{id,first_name:'Synthetic'+id,last_name:'Test',anonymous_id:'SYN-'+id,chief_complaint:'Complaint'},edit_revision:'a'.repeat(64),teeth:[],surfaces:[],treatments:[{id:1,treatment_name:'Root canal',material:'Synthetic material',result:'Synthetic result',doctor_note:'Synthetic note',edit_revision:'c'.repeat(64)}],media:[]});
const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?node.children.map(text).join(''):'';
test('profile follows web section order, expands patient info, and preserves complete treatment details',async()=>{
 const Profile=component({getPatient:async()=>patient(8)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const content=text(tree.toJSON());
 assert.ok(content.includes('Synthetic8'));assert.ok(content.includes('Hasta Bilgileri'));assert.ok(content.includes('Tedavi Geçmişi'));
 const children=tree.root.findAllByType('Child');
 const mediaIndex=children.findIndex(node=>node.props.patientId===8&&typeof node.props.onAnalysis==='function');
 const historyIndex=children.findIndex(node=>node.props.patientId===8&&typeof node.props.onOpenAnalysis==='function');
 assert.ok(mediaIndex>=0,'web patient profile clinical-media section must be mounted natively');
 assert.ok(historyIndex>mediaIndex,'native profile must keep clinical media before analysis history like web');
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
 assert.ok(!text(tree.toJSON()).includes('Old account failed'),'stale failure must not leak into the new patient');
 await renderer.act(async()=>tree.unmount());
});

test('definitive validation errors keep patient editing available for correction',async()=>{
 let calls=0;const Profile=component({getPatient:async()=>patient(8),editPatient:async()=>{calls++;if(calls===1)throw Object.assign(new Error('Geçersiz alan'),{status:422})}});let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');await press('Değişiklikleri Kaydet');
 assert.ok(text(tree.toJSON()).includes('Bilgileri düzeltip yeniden deneyin.'));
 const input=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');assert.ok(input.props.editable,'422 must not freeze the form');
 await press('Değişiklikleri Kaydet');assert.equal(calls,2,'corrected submission must be allowed');
 await renderer.act(async()=>tree.unmount());
});

test('ambiguous server failure prevents duplicate patient submission until reviewed',async()=>{
 let calls=0;const Profile=component({getPatient:async()=>patient(8),editPatient:async()=>{calls++;throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503})}});let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');await press('Değişiklikleri Kaydet');
 assert.ok(text(tree.toJSON()).includes('Tekrar göndermeden önce profili yenileyip kaydı kontrol edin.'));
 await press('Değişiklikleri Kaydet');assert.equal(calls,1,'uncertain server write must not be repeated automatically');
 await renderer.act(async()=>tree.unmount());
});

test('treatment validation 422 does not trap the clinician in uncertain state',async()=>{
 let calls=0;const Profile=component({getPatient:async()=>patient(8),createTreatment:async()=>{calls++;if(calls===1)throw Object.assign(new Error('Geçersiz tedavi'),{status:422})}});let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Yeni Tedavi');
 const input=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Tedavi adı *');assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Synthetic treatment'));
 await press('Tedaviyi Kaydet');
 assert.ok(text(tree.toJSON()).includes('Bilgileri düzeltip yeniden deneyin.'));
 await press('Tedaviyi Kaydet');assert.equal(calls,2);
 await renderer.act(async()=>tree.unmount());
});

test('uncertain treatment creation survives remount and reuses the exact secure request key',async()=>{
 const storage=new Map(),calls=[];let first=true;
 const make=()=>component({
  getPatient:async()=>patient(8),
  createTreatment:async(_token,_id,payload,requestKey)=>{
   calls.push({payload,requestKey,stored:storage.has('dai.treatment.1.8')});
   if(first){first=false;throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503})}
   return {ok:true,treatment_id:9,edit_revision:'d'.repeat(64),replayed:true};
  }
 },'NativePatientProfile',storage);
 const press=async(tree,label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 let tree,Profile=make();
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press(tree,'Yeni Tedavi');
 const input=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Tedavi adı *');assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Synthetic treatment'));
 await press(tree,'Tedaviyi Kaydet');
 assert.ok(storage.has('dai.treatment.1.8'),'intent must be encrypted and persisted before network mutation');
 assert.ok(calls[0].stored,'server request must never precede durable intent storage');
 assert.ok(text(tree.toJSON()).includes('Aynı işlem anahtarı güvenli taslakta korundu'));
 await renderer.act(async()=>tree.unmount());

 Profile=make();
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 assert.ok(text(tree.toJSON()).includes('Bekleyen Tedaviyi Doğrula'));
 await press(tree,'Bekleyen Tedaviyi Doğrula');
 assert.equal(calls.length,2);
 assert.equal(calls[0].requestKey,calls[1].requestKey,'restart must reuse the original request key');
 assert.ok(calls[1].stored);
 assert.ok(!storage.has('dai.treatment.1.8'),'confirmed receipt clears the secure intent');
 await renderer.act(async()=>tree.unmount());
});

test('stale patient revision preserves the draft until the clinician explicitly reloads current data',async()=>{
 let reads=0,attempted;
 const latest={...patient(8),edit_revision:'b'.repeat(64),patient:{...patient(8).patient,first_name:'Latest'}};
 const Profile=component({
  getPatient:async()=>reads++===0?patient(8):latest,
  editPatient:async(_token,_id,payload)=>{attempted=payload;throw Object.assign(new Error('Hasta bilgileri başka bir oturumda güncellendi.'),{status:409})}
 });
 let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 const first=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 await renderer.act(async()=>first.props.onChangeText('Draft'));
 await press('Değişiklikleri Kaydet');
 assert.equal(attempted.expected_revision,'a'.repeat(64));
 assert.ok(text(tree.toJSON()).includes('başka bir oturumda güncellendi'));
 assert.ok(text(tree.toJSON()).includes('Güncel hasta bilgilerini yükle'));
 await press('Güncel hasta bilgilerini yükle');
 const refreshed=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 assert.equal(refreshed.props.value,'Latest');
 assert.ok(text(tree.toJSON()).includes('Güncel hasta bilgileri yüklendi'));
 assert.ok(!text(tree.toJSON()).includes('Güncel hasta bilgilerini yükle'));
 await renderer.act(async()=>tree.unmount());
});
