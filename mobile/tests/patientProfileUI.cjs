const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
// Evaluate transpiled CommonJS in THIS realm instead of a fresh vm context:
// arrays/objects the modules return then share prototypes with the test's
// assert.deepStrictEqual comparisons (cross-realm values fail strict deep
// equality), while require stubs and exported bindings still work exactly
// as before. No assertion or stub shape is changed here.
const loadModuleRealm=(code,exports,require=()=>{throw Error('unexpected require')})=>{vm.runInThisContext('(function(exports,require,module,__filename,__dirname){'+code+'\n})',{filename:'synthetic-module.js'})(exports,require,{exports},'synthetic-module.js','.')};
const presentationExports={};
const presentationCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/patientProfilePresentation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
loadModuleRealm(presentationCode,presentationExports);
const deleteIntentExports={};
const deleteIntentCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/patientDeleteIntent.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
loadModuleRealm(deleteIntentCode,deleteIntentExports);
function component(api,file='NativePatientProfile',storage=new Map()){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/'+file+'.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const intentExports={};
 const intentCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/treatmentMutation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 loadModuleRealm(intentCode,intentExports);
 const secure={getItemAsync:async key=>storage.has(key)?storage.get(key):null,setItemAsync:async(key,value)=>storage.set(key,value),deleteItemAsync:async key=>storage.delete(key)};
 let sequence=0;const focusState={current:true};
 const alertCalls=[];
 const native={StyleSheet:{create:s=>s},AppState:{addEventListener:()=>({remove(){}})},Platform:{OS:'android'},Alert:{alert:(title,message,buttons)=>alertCalls.push({title,message,buttons})},...Object.fromEntries(['Modal','ActivityIndicator','KeyboardAvoidingView','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(s=>[s,s])),ScrollView:props=>React.createElement('ScrollView',props,props.refreshControl,props.children)},exports={};
 const endpoints={getPatient:async()=>patient(8),getPatientTreatments:async()=>({items:[],next_cursor:null}),createTreatment:async()=>({ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false}),updateTreatment:async()=>({ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false}),...api};
 loadModuleRealm(code,exports,name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>focusState.current}:name==='./api'?endpoints:name==='./clinicalDate'?{clinicalDate:(y,m,d)=>`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`,parseClinicalDate:value=>/^\d{4}-\d{2}-\d{2}$/.test(value)}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='expo-secure-store'?secure:name==='expo-crypto'?{randomUUID:()=>`synthetic-treatment-request-${String(++sequence).padStart(8,'0')}`}:name==='./socialDraft'?{chunkedDraftStore:raw=>raw}:name==='./treatmentMutation'?intentExports:name==='./patientDeleteIntent'?deleteIntentExports:name==='./patientProfilePresentation'?presentationExports:{default:'Child'});
 const Original=exports.default;
 const Wrapped=props=>React.createElement(Original,{userId:1,...props});
 Wrapped.storage=storage;
 Wrapped.alertCalls=alertCalls;
 Wrapped.focusState=focusState;
 return Wrapped;
}
const actions=Object.fromEntries(['chart','analysis','appointment','expert','analysisResult','deleted'].map(k=>[k,()=>{}]));
const patient=id=>({patient:{id,first_name:'Synthetic'+id,last_name:'Test',anonymous_id:'SYN-'+id,chief_complaint:'Complaint',age:0},edit_revision:'a'.repeat(64),teeth:[],surfaces:[],treatments:[{id:1,treatment_name:'Root canal',material:'Synthetic material',result:'Synthetic result',doctor_note:'Synthetic note',edit_revision:'c'.repeat(64),created_at:'2026-11-18T10:00:00'}],media:[]});
const pagedPatient=(id,cursor)=>{const value=patient(id);value.treatments=[{id:1,treatment_name:'Root canal',edit_revision:'c'.repeat(64),created_at:'2026-11-18T10:00:00'},{id:2,treatment_name:'Second treatment',edit_revision:'d'.repeat(64),created_at:'2026-11-17T10:00:00'},{id:3,treatment_name:'Third treatment',edit_revision:'e'.repeat(64),created_at:'2026-11-16T10:00:00'}];value.treatments_next_cursor=cursor;return value};
const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?node.children.map(text).join(''):'';
test('presentation model preserves zero age, safe identity fallbacks, and web action order',()=>{
 assert.equal(presentationExports.patientProfileName(' Ada ',' Kaya '),'Ada Kaya');
 assert.equal(presentationExports.patientProfileName(null,'  '),'İsimsiz Hasta');
 assert.equal(presentationExports.patientProfileInitials('Ada','Kaya'),'AK');
 assert.equal(presentationExports.patientProfileInitials(null,null),'H');
 assert.equal(presentationExports.patientProfileAgeLabel(0),'0 yaş');
 assert.equal(presentationExports.patientProfileAgeLabel(null),'Hasta kaydı');
 assert.deepEqual(presentationExports.patientProfileQuickActions().map(item=>item.key),['chart','analysis','appointment','treatment']);
});
test('three-way profile merge adopts unrelated server edits and reports same-field conflicts',()=>{
 const base={first_name:'Ada',last_name:'Kaya',phone:'05551112222',birth_date:'2000-01-01',tc_kimlik_no:'',address:'Ankara',chief_complaint:'Ağrı'};
 const draft={...base,first_name:'Cihan',chief_complaint:'Şişlik'};
 const latest={...base,last_name:'Yılmaz',phone:'05559998877',chief_complaint:'Kırık'};
 const merged=presentationExports.patientProfileMergeEditConflict(base,draft,latest);
 assert.equal(merged.values.first_name,'Cihan','local-only edits must remain in the draft');
 assert.equal(merged.values.last_name,'Yılmaz','remote-only edits must be adopted');
 assert.equal(merged.values.phone,'05559998877','unmodified local phone must not overwrite the remote phone');
 assert.equal(merged.values.address,'Ankara');
 assert.deepEqual(merged.conflicts.map(item=>item.field),['chief_complaint']);
 assert.equal(merged.conflicts[0].draftValue,'Şişlik');
 assert.equal(merged.conflicts[0].currentValue,'Kırık');
});

test('patient profile quick-action tiles are accessible and retain their native actions',async()=>{
 const calls=[];
 const routed={...actions,chart:()=>calls.push('chart'),analysis:()=>calls.push('analysis'),appointment:()=>calls.push('appointment')};
 const Profile=component({getPatient:async()=>patient(8)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions:routed}))});
 const expected=['Diş Şeması','AI Analiz','Randevu','Tedavi'];
 const tiles=tree.root.findAllByType('Pressable').filter(node=>expected.includes(node.props.accessibilityLabel));
 assert.deepEqual(tiles.map(node=>node.props.accessibilityLabel),expected,'quick actions must preserve the web patient-detail order');
 for(const tile of tiles){
  assert.equal(tile.props.accessibilityRole,'button');
  assert.ok(tile.props.accessibilityHint);
  assert.equal(tile.props.disabled,false);
  const styles=Array.isArray(tile.props.style)?tile.props.style.flat(Infinity):[tile.props.style];
  assert.ok(styles.some(style=>style&&style.minHeight>=44),'every action tile must retain a 44pt touch target');
 }
 for(const tile of tiles.slice(0,3))await renderer.act(async()=>tile.props.onPress());
 assert.deepEqual(calls,['chart','analysis','appointment']);
 await renderer.act(async()=>tiles[3].props.onPress());
 assert.ok(text(tree.toJSON()).includes('Yeni tedavi kaydı'),'treatment tile must open the existing treatment editor');
 await renderer.act(async()=>tree.unmount());
});
test('profile identity displays an unnamed fallback and does not hide age zero',async()=>{
 const base=patient(10);base.patient.first_name=null;base.patient.last_name=null;
 const Profile=component({getPatient:async()=>base});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:10,actions}))});
 const content=text(tree.toJSON());
 assert.ok(content.includes('İsimsiz Hasta'));
 assert.ok(content.includes('0 yaş'));
 await renderer.act(async()=>tree.unmount());
});
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
test('account switch invalidates the previous patient edit snapshot before a new profile resolves',async()=>{
 let resolve;const Profile=component({getPatient:async(token,id)=>id===8?patient(8):new Promise(r=>{resolve=r})});let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 const oldName=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 await renderer.act(async()=>oldName.props.onChangeText('Old account draft'));
 await renderer.act(async()=>tree.update(React.createElement(Profile,{token:'two',userId:2,patientId:9,actions})));
 assert.ok(!text(tree.toJSON()).includes('Synthetic8'));
 const next={...patient(9),edit_revision:'d'.repeat(64)};
 await renderer.act(async()=>{resolve(next)});
 assert.ok(text(tree.toJSON()).includes('Synthetic9'));
 assert.ok(!text(tree.toJSON()).includes('Old account draft'),'a new account must never inherit the previous patient edit snapshot');
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

test('stale patient revision merges drafts and requires an explicit choice for same-field conflicts',async()=>{
 let reads=0;const writes=[];
 const initial=patient(8);
 const latest={...patient(8),edit_revision:'b'.repeat(64),patient:{...patient(8).patient,first_name:'Latest',phone:'05559998877'}};
 const saved={...latest,edit_revision:'c'.repeat(64),patient:{...latest.patient,first_name:'Draft'}};
 const Profile=component({
  getPatient:async()=>{reads++;return reads===1?initial:reads===2?latest:saved},
  editPatient:async(_token,_id,payload)=>{writes.push(payload);if(writes.length===1)throw Object.assign(new Error('Hasta bilgileri başka bir oturumda güncellendi.'),{status:409});return {ok:true,patient:saved.patient,edit_revision:saved.edit_revision}}
 });
 let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 const first=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 await renderer.act(async()=>first.props.onChangeText('Draft'));
 await press('Değişiklikleri Kaydet');
 assert.equal(writes[0].expected_revision,'a'.repeat(64));
 assert.ok(text(tree.toJSON()).includes('Güncel kayıtla taslağı birleştir'));
 await press('Güncel kayıtla taslağı birleştir');
 let name=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 assert.equal(name.props.value,'Draft','the local draft must not be discarded');
 assert.ok(text(tree.toJSON()).includes('Taslağınız: Draft'));
 assert.ok(text(tree.toJSON()).includes('Güncel kayıt: Latest'));
 const save=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Değişiklikleri Kaydet')));
 assert.equal(save.props.disabled,true,'same-field conflicts must block saving');
 await press('Taslağımı koru');
 name=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 assert.equal(name.props.value,'Draft');
 assert.ok(!text(tree.toJSON()).includes('Eşzamanlı alan değişiklikleri'));
 await press('Değişiklikleri Kaydet');
 assert.equal(writes[1].expected_revision,'b'.repeat(64),'retry must use the refreshed revision');
 assert.equal(writes[1].first_name,'Draft');
 assert.equal(writes[1].phone,'05559998877','unmodified fields must keep the concurrent server update');
 assert.ok(reads>=3,'successful save must reload the authoritative profile');
 await renderer.act(async()=>tree.unmount());
});

test('realtime refresh during an open patient draft does not silently advance its edit revision',async()=>{
 let reads=0;const writes=[];
 const initial=patient(8);initial.patient.phone='05551112222';initial.patient.address='Ankara';
 const latest={...patient(8),edit_revision:'b'.repeat(64),patient:{...initial.patient,phone:'05559998877',address:'İzmir'}};
 const saved={...latest,edit_revision:'c'.repeat(64),patient:{...latest.patient,first_name:'Local draft'}};
 const Profile=component({
  getPatient:async()=>{reads++;return reads===1?initial:reads<4?latest:saved},
  editPatient:async(_token,_id,payload)=>{writes.push(payload);return {ok:true,patient:saved.patient,edit_revision:saved.edit_revision}}
 });
 let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 const name=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 await renderer.act(async()=>name.props.onChangeText('Local draft'));
 const refresh=tree.root.findByType('RefreshControl');
 await renderer.act(async()=>refresh.props.onRefresh());
 assert.ok(text(tree.toJSON()).includes('Güncel kayıtla taslağı birleştir'));
 assert.equal(tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad').props.value,'Local draft');
 await press('Güncel kayıtla taslağı birleştir');
 assert.equal(tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad').props.value,'Local draft');
 assert.equal(tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Telefon').props.value,'05559998877');
 await press('Değişiklikleri Kaydet');
 assert.equal(writes[0].expected_revision,'b'.repeat(64));
 assert.equal(writes[0].phone,'05559998877');
 assert.equal(writes[0].address,'İzmir');
 await renderer.act(async()=>tree.unmount());
});


test('secure intent cleanup failure blocks subsequent treatment writes',async()=>{
 const storage=new Map();storage.delete=()=>{throw new Error('synthetic keychain failure')};
 let calls=0;const Profile=component({getPatient:async()=>patient(8),createTreatment:async()=>{calls++;throw Object.assign(new Error('Validation rejected'),{status:422})}},'NativePatientProfile',storage);let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Yeni Tedavi');
 const input=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Tedavi adı *');assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Synthetic treatment'));
 await press('Tedaviyi Kaydet');
 assert.ok(storage.has('dai.treatment.1.8'));
 assert.ok(text(tree.toJSON()).includes('güvenli taslak temizlenemedi'));
 await press('Bekleyen Tedaviyi Doğrula');
 assert.equal(calls,1,'a blocked secure draft must not produce another server mutation');
 await renderer.act(async()=>tree.unmount());
});

test('patient profile edit validation matches the web form and mobile API contract',()=>{
 const validate=presentationExports.patientProfileEditError;
 assert.equal(validate({first_name:' Ada ',last_name:' Kaya ',phone:''}),null);
 assert.equal(validate({first_name:'Ada',last_name:'Kaya',phone:'05123456789'}),null);
 assert.equal(validate({first_name:' ',last_name:'Kaya',phone:''}),'Ad ve soyad zorunludur.');
 for(const phone of ['5','0512345678','04123456789','05abcdefgh','051234567890']){
  assert.equal(validate({first_name:'Ada',last_name:'Kaya',phone}),'Telefon numarası 05 ile başlamalı ve toplam 11 rakam olmalıdır.');
 }
 assert.equal(validate({first_name:'Ada',last_name:'Kaya',phone:'   '}),null);
});

test('invalid native patient phone is blocked before mutation and valid Turkish mobile number saves',async()=>{
 const writes=[];
 const Profile=component({
  getPatient:async()=>patient(8),
  editPatient:async(_token,_id,payload)=>{writes.push(payload);return {ok:true,patient:patient(8).patient,edit_revision:'b'.repeat(64)}}
 });
 let tree;
 const press=async(label)=>{
  const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));
  assert.ok(item,'missing '+label);
  await renderer.act(async()=>item.props.onPress());
 };
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 let phone=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Telefon');
 assert.ok(phone);
 assert.equal(phone.props.maxLength,11,'native phone field must mirror the web form length');
 await renderer.act(async()=>phone.props.onChangeText('0512345678'));
 await press('Değişiklikleri Kaydet');
 assert.equal(writes.length,0,'invalid phone must not reach the mobile API');
 assert.ok(text(tree.toJSON()).includes('Telefon numarası 05 ile başlamalı'));
 phone=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Telefon');
 await renderer.act(async()=>phone.props.onChangeText('05123456789'));
 await press('Değişiklikleri Kaydet');
 assert.equal(writes.length,1);
 assert.equal(writes[0].phone,'05123456789');
 assert.equal(writes[0].expected_revision,'a'.repeat(64));
 await renderer.act(async()=>tree.unmount());
});

test('patient edit reconciliation compares every web-editable field after trim/null normalization',()=>{
 const matches=presentationExports.patientProfileEditMatches;
 const draft={first_name:' Ada ',last_name:' Kaya ',phone:' 05123456789 ',birth_date:'2000-02-29',tc_kimlik_no:' 12345678901 ',address:' Ankara ',chief_complaint:' Ağrı '};
 const current={first_name:'Ada',last_name:'Kaya',phone:'05123456789',birth_date:'2000-02-29',tc_kimlik_no:'12345678901',address:'Ankara',chief_complaint:'Ağrı'};
 assert.equal(matches(draft,current),true);
 assert.equal(matches({...draft,address:'İzmir'},current),false,'address must participate in reconciliation');
 assert.equal(matches({...draft,chief_complaint:'Başka şikâyet'},current),false,'chief complaint must participate in reconciliation');
 assert.equal(matches({...draft,birth_date:'2000-02-28'},current),false,'birth date must participate in reconciliation');
});

test('patient deletion gate requires all profile and treatment intents to be known and settled',()=>{
 const can=presentationExports.patientProfileCanDeletePatient;
 const ready={busy:false,uncertain:false,treatmentIntentReady:true,treatmentIntentBlocked:false,hasPendingTreatment:false,deleteIntentReady:true,deleteIntentBlocked:false,hasPendingDelete:false};
 assert.equal(can(ready),true);
 for(const patch of [
  {busy:true},{uncertain:true},{treatmentIntentReady:false},
  {treatmentIntentBlocked:true},{hasPendingTreatment:true},
   {deleteIntentReady:false},{deleteIntentBlocked:true},{hasPendingDelete:true}
 ]) assert.equal(can({...ready,...patch}),false,JSON.stringify(patch));
});

test('pending or unreadable secure treatment intent disables patient deletion',async()=>{
 const pending={userId:1,patientId:8,operation:'CREATE',treatmentId:null,requestKey:'synthetic-treatment-request-0001',expectedRevision:null,payload:{treatment_name:'Synthetic treatment',tooth_number:'',treatment_date:'',material:'',doctor_note:'',result:''}};
 for(const raw of [JSON.stringify(pending),'not-json']){
  const storage=new Map([['dai.treatment.1.8',raw]]);
  const Profile=component({getPatient:async()=>patient(8)},'NativePatientProfile',storage);let tree;
  await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
  const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
  await renderer.act(async()=>info.props.onPress());
  const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
  assert.ok(remove,'web-equivalent patient delete action remains visible');
  assert.equal(remove.props.disabled,true,'unresolved or unreadable clinical intent must fail closed');
  const newTreatment=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Yeni Tedavi')));
  assert.equal(newTreatment.props.disabled,true,'new clinical mutations must wait for secure intent recovery');
  assert.ok(text(tree.toJSON()).includes('güvenli durum kontrolü tamamlanana kadar devre dışıdır'));
  await renderer.act(async()=>tree.unmount());
 }
});

test('ambiguous patient edit stays locked until a successful server read reconciles the draft',async()=>{
 let reads=0;
 const saved={...patient(8),patient:{...patient(8).patient,first_name:'Saved'},edit_revision:'b'.repeat(64)};
 const Profile=component({
  getPatient:async()=>reads++===0?patient(8):saved,
  editPatient:async()=>{throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503})}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 const name=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 await renderer.act(async()=>name.props.onChangeText('Saved'));
 await press('Değişiklikleri Kaydet');
 assert.ok(text(tree.toJSON()).includes('Sunucu yanıtı belirsiz'));
 assert.ok(text(tree.toJSON()).includes('Sunucudaki profil kaydını karşılaştır'));
 let remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,true,'an ambiguous profile write blocks deletion');
 await press('Sunucudaki profil kaydını karşılaştır');
 assert.ok(text(tree.toJSON()).includes('Hasta bilgileri sunucuda doğrulandı'));
 assert.ok(!text(tree.toJSON()).includes('Sunucudaki profil kaydını karşılaştır'));
 await press('Hasta Bilgileri');
 remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,false,'a successful read that matches every field resolves the uncertain write');
 await renderer.act(async()=>tree.unmount());
});

test('uncertain patient edit reconciliation merges remote-only fields before retry',async()=>{
 let reads=0;const writes=[];
 const initial=patient(8);initial.patient.phone='05551112222';initial.patient.address='Ankara';
 const latest={...patient(8),edit_revision:'b'.repeat(64),patient:{...initial.patient,phone:'05559998877',address:'İzmir'}};
 const saved={...latest,edit_revision:'c'.repeat(64),patient:{...latest.patient,first_name:'Local draft'}};
 const Profile=component({
  getPatient:async()=>{reads++;return reads===1?initial:reads===2?latest:saved},
  editPatient:async(_token,_id,payload)=>{writes.push(payload);if(writes.length===1)throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503});return {ok:true,patient:saved.patient,edit_revision:saved.edit_revision}}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');
 const name=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad');
 await renderer.act(async()=>name.props.onChangeText('Local draft'));
 await press('Değişiklikleri Kaydet');
 await press('Sunucudaki profil kaydını karşılaştır');
 assert.equal(tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ad').props.value,'Local draft');
 assert.equal(tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Telefon').props.value,'05559998877');
 assert.equal(tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Adres').props.value,'İzmir');
 assert.ok(text(tree.toJSON()).includes('güncel sunucu alanlarıyla birleştirildi'));
 await press('Değişiklikleri Kaydet');
 assert.equal(writes[1].expected_revision,'b'.repeat(64));
 assert.equal(writes[1].first_name,'Local draft');
 assert.equal(writes[1].phone,'05559998877');
 assert.equal(writes[1].address,'İzmir');
 await renderer.act(async()=>tree.unmount());
});

test('failed patient edit reconciliation preserves uncertainty and keeps deletion disabled',async()=>{
 let reads=0;
 const Profile=component({
  getPatient:async()=>{reads++;if(reads===1)return patient(8);throw new Error('Offline')},
  editPatient:async()=>{throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503})}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');await press('Değişiklikleri Kaydet');
 await press('Sunucudaki profil kaydını karşılaştır');
 assert.ok(text(tree.toJSON()).includes('Belirsizlik korunuyor'));
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,true);
 await renderer.act(async()=>tree.unmount());
});

test('restored treatment intent blocks profile edits until its exact receipt is reconciled',async()=>{
 const pending={userId:1,patientId:8,operation:'CREATE',treatmentId:null,requestKey:'synthetic-treatment-request-0001',expectedRevision:null,payload:{treatment_name:'Synthetic treatment',tooth_number:'',treatment_date:'',material:'',doctor_note:'',result:''}};
 const storage=new Map([['dai.treatment.1.8',JSON.stringify(pending)]]);
 let writes=0;
 const Profile=component({getPatient:async()=>patient(8),editPatient:async()=>{writes++}},'NativePatientProfile',storage);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
 await renderer.act(async()=>info.props.onPress());
 const save=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Değişiklikleri Kaydet')));
 assert.equal(save.props.disabled,true);
 const inputs=tree.root.findAllByType('TextInput');
 assert.ok(inputs.every(input=>input.props.editable===false),'profile fields stay read-only while treatment receipt is unresolved');
 const newTreatment=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Yeni Tedavi')));
 assert.equal(newTreatment.props.disabled,true);
 assert.equal(writes,0);
 await renderer.act(async()=>tree.unmount());
});

test('ambiguous profile edit cannot start a treatment mutation until profile reconciliation',async()=>{
 let treatmentWrites=0;
 const Profile=component({
  getPatient:async()=>patient(8),
  editPatient:async()=>{throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503})},
  createTreatment:async()=>{treatmentWrites++;return {ok:true,treatment_id:9,edit_revision:'e'.repeat(64),replayed:false}}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');await press('Değişiklikleri Kaydet');
 await press('Yeni Tedavi');
 assert.equal(treatmentWrites,0,'profile uncertainty must not be cleared by a treatment receipt');
 assert.ok(text(tree.toJSON()).includes('Önce bekleyen profil veya tedavi işlemini sunucuyla doğrulayın.'));
 await renderer.act(async()=>tree.unmount());
});

test('second patient-delete confirmation is discarded after account or patient scope changes',async()=>{
 let deletes=0;
 const Profile=component({
  getPatient:async(_token,id)=>patient(id),
  deletePatient:async()=>{deletes++;return {ok:true,patient_id:8}}
 });let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
 await renderer.act(async()=>info.props.onPress());
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,false);
 await renderer.act(async()=>remove.props.onPress());
 assert.equal(Profile.alertCalls.length,1);
 await renderer.act(async()=>Profile.alertCalls[0].buttons[1].onPress());
 assert.equal(Profile.alertCalls.length,2,'first confirmation opens the second destructive confirmation');
 await renderer.act(async()=>tree.update(React.createElement(Profile,{token:'two',patientId:9,actions})));
 await renderer.act(async()=>Profile.alertCalls[1].buttons[1].onPress());
 assert.equal(deletes,0,'a stale alert must not delete the previous account or patient');
 await renderer.act(async()=>tree.unmount());
});

test('second patient-delete confirmation is discarded after the profile loses focus',async()=>{
 let deletes=0;
 const Profile=component({getPatient:async()=>patient(8),deletePatient:async()=>{deletes++;return {ok:true,patient_id:8}}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
 await renderer.act(async()=>info.props.onPress());
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 await renderer.act(async()=>remove.props.onPress());
 await renderer.act(async()=>Profile.alertCalls[0].buttons[1].onPress());
 assert.equal(Profile.alertCalls.length,2);
 Profile.focusState.current=false;
 await renderer.act(async()=>tree.update(React.createElement(Profile,{token:'one',patientId:8,actions})));
 await renderer.act(async()=>Profile.alertCalls[1].buttons[1].onPress());
 assert.equal(deletes,0,'a destructive alert cannot execute after the profile loses focus');
 await renderer.act(async()=>tree.unmount());
});

test('patient profile refuses a response whose patient id differs from the requested route',async()=>{
 const Profile=component({getPatient:async()=>patient(9)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const content=text(tree.toJSON());
 assert.ok(content.includes('Sunucu farklı bir hasta kaydı döndürdü.'));
 assert.ok(!content.includes('Synthetic9'),'another patient response must never render in this profile');
 await renderer.act(async()=>tree.unmount());
});

test('mismatched patient identity cannot resolve an ambiguous edit or enable deletion',async()=>{
 let reads=0;
 const Profile=component({
  getPatient:async()=>reads++===0?patient(8):patient(9),
  editPatient:async()=>{throw Object.assign(new Error('Sunucu yanıtı belirsiz'),{status:503})}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 await press('Hasta Bilgileri');await press('Değişiklikleri Kaydet');
 await press('Sunucudaki profil kaydını karşılaştır');
 assert.ok(text(tree.toJSON()).includes('Belirsizlik korunuyor'));
 assert.ok(text(tree.toJSON()).includes('Sunucu farklı bir hasta kaydı döndürdü.'));
 assert.ok(!text(tree.toJSON()).includes('Synthetic9'));
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,true);
 await renderer.act(async()=>tree.unmount());
});

test('patient delete intent parser is bound to one account and patient',()=>{
 const created=deleteIntentExports.createPatientDeleteIntent(1,8,'synthetic-patient-delete-0001');
 assert.equal(created.version,1);
 assert.equal(created.userId,1);
 assert.equal(created.patientId,8);
 assert.equal(created.requestKey,'synthetic-patient-delete-0001');
 assert.equal(deleteIntentExports.patientDeleteIntentStorageKey(1,8),'dai.patient-delete.v1.1.8');
 assert.throws(()=>deleteIntentExports.parsePatientDeleteIntent(JSON.stringify(created),2,8));
 assert.throws(()=>deleteIntentExports.parsePatientDeleteIntent(JSON.stringify(created),1,9));
 assert.throws(()=>deleteIntentExports.parsePatientDeleteIntent('not-json',1,8));
 assert.throws(()=>deleteIntentExports.createPatientDeleteIntent(1,8,'short'));
});

test('native patient delete persists its request key before the server mutation and clears it after success',async()=>{
 const storage=new Map(),calls=[],deleted=[];
 const routed={...actions,deleted:()=>deleted.push(true)};
 const Profile=component({
  getPatient:async()=>patient(8),
  deletePatient:async(_token,id,key)=>{calls.push({id,key,stored:storage.has('dai.patient-delete.v1.1.8')});return{ok:true,patient_id:id,already_deleted:false};}
 },'NativePatientProfile',storage);
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions:routed}));await Promise.resolve();await Promise.resolve()});
 const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
 await renderer.act(async()=>info.props.onPress());
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,false);
 await renderer.act(async()=>remove.props.onPress());
 await renderer.act(async()=>Profile.alertCalls[0].buttons[1].onPress());
 await renderer.act(async()=>{Profile.alertCalls[1].buttons[1].onPress();await new Promise(resolve=>setImmediate(resolve));});
 assert.equal(calls.length,1);
 assert.equal(calls[0].id,8);
 assert.equal(calls[0].stored,true,'the durable intent must exist before DELETE');
 assert.match(calls[0].key,/^synthetic-treatment-request-/);
 assert.equal(storage.has('dai.patient-delete.v1.1.8'),false);
 assert.deepEqual(deleted,[true]);
 await renderer.act(async()=>tree.unmount());
});

test('ambiguous patient delete replays the exact same key after restoring the durable intent',async()=>{
 const storage=new Map(),calls=[],deleted=[];let attempt=0;
 const routed={...actions,deleted:()=>deleted.push(true)};
 const Profile=component({
  getPatient:async()=>patient(8),
  deletePatient:async(_token,id,key)=>{
   calls.push({id,key,stored:storage.has('dai.patient-delete.v1.1.8')});
   if(attempt++===0)throw Object.assign(new Error('Yanıt kayboldu'),{status:503});
   return{ok:true,patient_id:id,already_deleted:true};
  }
 },'NativePatientProfile',storage);
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions:routed}));await Promise.resolve();await Promise.resolve()});
 const press=async(label)=>{const node=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(node,'missing '+label);await renderer.act(async()=>node.props.onPress())};
 await press('Hasta Bilgileri');
 await press('Hasta Kaydını Sil');
 await renderer.act(async()=>Profile.alertCalls[0].buttons[1].onPress());
 await renderer.act(async()=>{Profile.alertCalls[1].buttons[1].onPress();await new Promise(resolve=>setImmediate(resolve));});
 assert.equal(calls.length,1);
 assert.equal(storage.has('dai.patient-delete.v1.1.8'),true,'ambiguous result must retain the request key');
 await press('Bekleyen Silme İşlemini Doğrula');
 await renderer.act(async()=>Profile.alertCalls[2].buttons[1].onPress());
 await renderer.act(async()=>{Profile.alertCalls[3].buttons[1].onPress();await new Promise(resolve=>setImmediate(resolve));});
 assert.equal(calls.length,2);
 assert.equal(calls[0].key,calls[1].key,'recovery must replay the exact original request key');
 assert.equal(calls[1].stored,true);
 assert.equal(storage.has('dai.patient-delete.v1.1.8'),false);
 assert.deepEqual(deleted,[true]);
 await renderer.act(async()=>tree.unmount());
});

test('corrupt patient delete intent fails closed and never creates a replacement request',async()=>{
 const storage=new Map([['dai.patient-delete.v1.1.8','']]);let deletes=0;
 const Profile=component({getPatient:async()=>patient(8),deletePatient:async()=>{deletes++;return{ok:true,patient_id:8,already_deleted:false}}},'NativePatientProfile',storage);
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}));await Promise.resolve();await Promise.resolve()});
 const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
 await renderer.act(async()=>info.props.onPress());
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 assert.equal(remove.props.disabled,true);
 assert.ok(text(tree.toJSON()).includes('Güvenli hasta silme kaydı okunamadı'));
 assert.equal(deletes,0);
 await renderer.act(async()=>tree.unmount());
});

test('patient delete does not send a request when SecureStore cannot persist the intent',async()=>{
 const storage=new Map();const originalSet=storage.set.bind(storage);
 storage.set=(key,value)=>{if(String(key).startsWith('dai.patient-delete.'))throw new Error('synthetic secure storage failure');return originalSet(key,value)};
 let deletes=0;
 const Profile=component({getPatient:async()=>patient(8),deletePatient:async()=>{deletes++;return{ok:true,patient_id:8,already_deleted:false}}},'NativePatientProfile',storage);
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}));await Promise.resolve();await Promise.resolve()});
 const info=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Bilgileri')));
 await renderer.act(async()=>info.props.onPress());
 const remove=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Hasta Kaydını Sil')));
 await renderer.act(async()=>remove.props.onPress());
 await renderer.act(async()=>Profile.alertCalls[0].buttons[1].onPress());
 await renderer.act(async()=>{Profile.alertCalls[1].buttons[1].onPress();await new Promise(resolve=>setImmediate(resolve));});
 assert.equal(deletes,0,'DELETE must not be sent before the idempotency key is durable');
 assert.ok(text(tree.toJSON()).includes('Sunucuya istek gönderilmedi'));
 await renderer.act(async()=>tree.unmount());
});

test('missing or no-longer-owned patient exits the stale profile route safely',async()=>{
 const deleted=[];
 const routed={...actions,deleted:()=>deleted.push(true)};
 const Profile=component({getPatient:async()=>{throw Object.assign(new Error('Hasta bulunamadı.'),{status:404})}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions:routed}));await Promise.resolve();await Promise.resolve()});
 assert.deepEqual(deleted,[true],'a 404 must not leave a deleted patient profile in a permanent retry state');
 await renderer.act(async()=>tree.unmount());
});

test('pending patient deletion makes nested clinical media and analysis surfaces read-only',async()=>{
 const storage=new Map([['dai.patient-delete.v1.1.8',JSON.stringify(deleteIntentExports.createPatientDeleteIntent(1,8,'synthetic-patient-delete-0005'))]]);
 const Profile=component({getPatient:async()=>patient(8)},'NativePatientProfile',storage);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}));await Promise.resolve();await Promise.resolve()});
 const children=tree.root.findAllByType('Child');
 const media=children.find(node=>node.props.patientId===8&&typeof node.props.onAnalysis==='function');
 const history=children.find(node=>node.props.patientId===8&&typeof node.props.onOpenAnalysis==='function');
 assert.ok(media);
 assert.equal(media.props.readOnly,true,'clinical media uploads/deletes and new analysis must be read-only');
 assert.ok(history);
 assert.equal(history.props.onNew,undefined,'new analysis entry must be hidden while deletion is unresolved');
 const voice=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(t=>text(t.children).trim()==='Sesli Muayene'));
 assert.equal(voice,undefined,'voice examination entry belongs to the dedicated home screen, not the patient profile');
 await renderer.act(async()=>tree.unmount());
});



test('patient profile loads older treatment records in bounded pages and can collapse them again',async()=>{
 const base=pagedPatient(8,'A'.repeat(32)),cursor='A'.repeat(32),calls=[];
 base.treatments=[
  {id:1,treatment_name:'Initial treatment 1',edit_revision:'1'.repeat(64),created_at:'2026-11-18T10:00:00'},
  {id:2,treatment_name:'Initial treatment 2',edit_revision:'2'.repeat(64),created_at:'2026-11-17T10:00:00'},
  {id:3,treatment_name:'Initial treatment 3',edit_revision:'3'.repeat(64),created_at:'2026-11-16T10:00:00'}
 ];
 base.treatments_next_cursor=cursor;
 const Profile=component({
  getPatient:async()=>base,
  getPatientTreatments:async(token,id,before)=>{
   calls.push({token,id,before});
   return {items:[
    {id:4,treatment_name:'Paged treatment 4',edit_revision:'4'.repeat(64),created_at:'2026-11-18T10:00:00'},
    {id:5,treatment_name:'Paged treatment 5',edit_revision:'5'.repeat(64),created_at:'2026-11-18T09:00:00'}
   ],next_cursor:null};
  }
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>{item.props.onPress();await new Promise(resolve=>setImmediate(resolve))});};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'owner-token',patientId:8,actions}))});
 assert.ok(text(tree.toJSON()).includes('Initial treatment 3'));
 assert.equal(text(tree.toJSON()).includes('Paged treatment 4'),false,'older records must not be downloaded or rendered initially');
 await press('Diğer tedavileri göster');
 assert.deepEqual(calls,[{token:'owner-token',id:8,before:cursor}]);
 assert.ok(text(tree.toJSON()).includes('Paged treatment 4'));
 assert.ok(text(tree.toJSON()).includes('Paged treatment 5'));
 await press('Tedavileri gizle');
 assert.equal(text(tree.toJSON()).includes('Paged treatment 4'),false);
 await press('Diğer tedavileri göster');
 assert.ok(text(tree.toJSON()).includes('Paged treatment 4'));
 assert.equal(calls.length,1,'already fetched pages are shown locally without a duplicate API read');
 await renderer.act(async()=>tree.unmount());
});

test('treatment page errors preserve the first page and retry the same cursor',async()=>{
 const cursor='B'.repeat(32),base=pagedPatient(8,cursor),calls=[];
 let fail=true;
 const Profile=component({
  getPatient:async()=>base,
  getPatientTreatments:async(_token,_id,before)=>{calls.push(before);if(fail)throw Error('Sentetik çevrimdışı hata');return {items:[{id:9,treatment_name:'Recovered treatment',edit_revision:'9'.repeat(64),created_at:'2026-11-18T10:00:00'}],next_cursor:null}}
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>{item.props.onPress();await new Promise(resolve=>setImmediate(resolve))});};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'owner-token',patientId:8,actions}))});
 await press('Diğer tedavileri göster');
 assert.ok(text(tree.toJSON()).includes('Sentetik çevrimdışı hata'));
 assert.ok(text(tree.toJSON()).includes('Root canal'),'verified first-page treatment must remain visible');
 assert.equal(text(tree.toJSON()).includes('Recovered treatment'),false);
 fail=false;
 await press('Tekrar dene');
 assert.deepEqual(calls,[cursor,cursor]);
 assert.ok(text(tree.toJSON()).includes('Recovered treatment'));
 await renderer.act(async()=>tree.unmount());
});

test('duplicate treatment page rows are rejected without replacing verified clinical history',async()=>{
 const cursor='C'.repeat(32),base=pagedPatient(8,cursor);
 const Profile=component({getPatient:async()=>base,getPatientTreatments:async()=>({items:[{id:1,treatment_name:'Stale duplicate',edit_revision:'a'.repeat(64),created_at:'2026-11-18T10:00:00'}],next_cursor:null})});let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>{item.props.onPress();await new Promise(resolve=>setImmediate(resolve))});};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'owner-token',patientId:8,actions}))});
 await press('Diğer tedavileri göster');
 assert.ok(text(tree.toJSON()).includes('tekrarlanan kayıt algılandı'));
 assert.ok(text(tree.toJSON()).includes('Root canal'));
 assert.equal(text(tree.toJSON()).includes('Stale duplicate'),false);
 await renderer.act(async()=>tree.unmount());
});

test('late treatment page from a previous patient cannot leak into the next account',async()=>{
 const cursor='D'.repeat(32);let resolveOld;
 const Profile=component({
  getPatient:async(_token,id)=>id===8?pagedPatient(id,cursor):patient(id),
  getPatientTreatments:async()=>new Promise(resolve=>{resolveOld=resolve})
 });let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes(label)));assert.ok(item,'missing '+label);await renderer.act(async()=>item.props.onPress());};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'old-token',patientId:8,actions}))});
 await press('Diğer tedavileri göster');
 assert.equal(typeof resolveOld,'function');
 await renderer.act(async()=>{tree.update(React.createElement(Profile,{token:'new-token',patientId:9,actions}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{resolveOld({items:[{id:99,treatment_name:'Private old patient treatment',edit_revision:'9'.repeat(64),created_at:'2026-11-18T10:00:00'}],next_cursor:null});await new Promise(resolve=>setImmediate(resolve))});
 const rendered=text(tree.toJSON());
 assert.ok(rendered.includes('Synthetic9'));
 assert.equal(rendered.includes('Private old patient treatment'),false);
 await renderer.act(async()=>tree.unmount());
});

test('rapid double tap on treatment pagination sends only one request',async()=>{
 const cursor='E'.repeat(32),base=pagedPatient(8,cursor);
 let resolvePage,calls=0;
 const Profile=component({getPatient:async()=>base,getPatientTreatments:async()=>{calls++;return new Promise(resolve=>{resolvePage=resolve})}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'owner-token',patientId:8,actions}))});
 const button=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(t=>text(t.children).includes('Diğer tedavileri göster')));
 assert.ok(button);
 await renderer.act(async()=>{button.props.onPress();button.props.onPress();});
 assert.equal(calls,1);
 await renderer.act(async()=>{resolvePage({items:[],next_cursor:null});await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>tree.unmount());
});

test('voice examination stays on the dedicated home feature and stack route',async()=>{
 const Profile=component({getPatient:async()=>patient(8)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Profile,{token:'one',patientId:8,actions}))});
 const voiceEntry=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(t=>text(t.children).trim()==='Sesli Muayene'));
 assert.equal(voiceEntry,undefined,'patient detail must not duplicate the separate voice-exam entry');
 const app=fs.readFileSync(require.resolve('../App.tsx'),'utf8');
 assert.match(app,/VisualFeature title="Sesli Muayene"[\s\S]*?navigate\("VoiceExam"\)/);
 assert.match(app,/Stack\.Screen name="VoiceExam"/);
 await renderer.act(async()=>tree.unmount());
});
