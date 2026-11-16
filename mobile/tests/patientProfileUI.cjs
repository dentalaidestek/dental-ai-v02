const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const presentationExports={};
const presentationCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/patientProfilePresentation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(presentationCode,{exports:presentationExports});
function component(api,file='NativePatientProfile',storage=new Map()){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/'+file+'.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const intentExports={};
 const intentCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/treatmentMutation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 vm.runInNewContext(intentCode,{exports:intentExports,Error,JSON,Date,Number,RegExp});
 const secure={getItemAsync:async key=>storage.get(key)||null,setItemAsync:async(key,value)=>storage.set(key,value),deleteItemAsync:async key=>storage.delete(key)};
 let sequence=0;
 const native={StyleSheet:{create:s=>s},AppState:{addEventListener:()=>({remove(){}})},Platform:{OS:'android'},Alert:{alert(){}},...Object.fromEntries(['Modal','ActivityIndicator','KeyboardAvoidingView','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(s=>[s,s]))},exports={};
 const endpoints={getPatient:async()=>patient(8),createTreatment:async()=>({ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false}),updateTreatment:async()=>({ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false}),...api};
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./api'?endpoints:name==='./clinicalDate'?{clinicalDate:(y,m,d)=>`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`,parseClinicalDate:value=>/^\d{4}-\d{2}-\d{2}$/.test(value)}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='expo-secure-store'?secure:name==='expo-crypto'?{randomUUID:()=>`synthetic-treatment-request-${String(++sequence).padStart(8,'0')}`}:name==='./socialDraft'?{chunkedDraftStore:raw=>raw}:name==='./treatmentMutation'?intentExports:name==='./patientProfilePresentation'?presentationExports:{default:'Child'}});
 const Original=exports.default;
 const Wrapped=props=>React.createElement(Original,{userId:1,...props});
 Wrapped.storage=storage;
 return Wrapped;
}
const actions=Object.fromEntries(['chart','analysis','appointment','expert','voice','analysisResult','deleted'].map(k=>[k,()=>{}]));
const patient=id=>({patient:{id,first_name:'Synthetic'+id,last_name:'Test',anonymous_id:'SYN-'+id,chief_complaint:'Complaint',age:0},edit_revision:'a'.repeat(64),teeth:[],surfaces:[],treatments:[{id:1,treatment_name:'Root canal',material:'Synthetic material',result:'Synthetic result',doctor_note:'Synthetic note',edit_revision:'c'.repeat(64)}],media:[]});
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
