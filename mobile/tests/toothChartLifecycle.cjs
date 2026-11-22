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
 const secure={getItemAsync:async key=>{const custom=storage.get('__getItemAsync');return typeof custom==='function'?custom(key):storage.has(key)?storage.get(key):null},setItemAsync:async(key,value)=>storage.set(key,value),deleteItemAsync:async key=>storage.delete(key)};
 const crypto={randomUUID:()=>`synthetic-treatment-request-${String(++sequence).padStart(8,"0")}`};
 vm.runInNewContext(code,{exports,require:name=>{
  if(name==='react')return{...React,default:React};
  if(name==='react-native')return native;
  if(name==='@react-navigation/native')return{useNavigation:()=>({getParent:()=>({getParent:()=>({navigate(){}})})}),useIsFocused:()=>focused};
  if(name==='./api')return{getToothChartFocus:async()=>null,getToothTreatments:async()=>({items:[],next_cursor:null}),...api};
  if(name==='expo-secure-store')return secure;
  if(name==='expo-crypto')return crypto;
  if(name==='./socialDraft')return{chunkedDraftStore:raw=>raw};
  if(name==='./treatmentMutation')return require('../src/treatmentMutation.ts');
  if(name==='./realtime')return{useRealtime:()=>({lastEvent})};
  if(name==='./toothChartPresentation')return require('../src/toothChartPresentation.ts');
  if(name==='./toothChartHistoryPresentation')return require('../src/toothChartHistoryPresentation.ts');
  if(name==='./toothChartConflictPresentation')return require('../src/toothChartConflictPresentation.ts');
  if(name==='./toothSurfaceOptions')return require('../src/toothSurfaceOptions.ts');
  if(name==='./toothChartSurfaceSelection')return require('../src/toothChartSurfaceSelection.ts');
  if(name==='./appResumeRefresh')return require('../src/appResumeRefresh.ts');
  if(name==='./useSessionRenderKey')return require('./helpers/useSessionRenderKeyModule.cjs');
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


test('native tooth chart opens the web-selected permanent tooth with its saved status and note',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const detail=patient(8,'Ada');
 detail.teeth.push({id:2,tooth_number:'36',status:'CARIES',note:'Saved clinical note'});
 const Chart=chartComponent({getPatient:async()=>detail,getToothChartFocus:async()=> '36'});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 const selected=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 36, Çürük');
 assert.ok(selected,'web latest-analysis tooth must be opened automatically');
 assert.equal(selected.props.accessibilityState.selected,true);
 assert.ok(flat(tree.toJSON()).includes('Diş 36'));
 assert.ok(flat(tree.toJSON()).includes('Alt Sol Birinci Molar'));
 const notesTab=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Notlar'));
 assert.ok(notesTab);
 await renderer.act(async()=>notesTab.props.onPress());
 const clinicalNote=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Diş notları');
 assert.equal(clinicalNote.props.value,'Saved clinical note');
 await renderer.act(async()=>tree.unmount());
});

test('native tooth chart switches to primary dentition for a web-selected primary tooth',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const Chart=chartComponent({getPatient:async()=>patient(8),getToothChartFocus:async()=> '55'});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 const selected=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 55, Sağlıklı');
 assert.ok(selected,'primary FDI tooth must be selected');
 assert.equal(selected.props.accessibilityState.selected,true);
 assert.ok(flat(tree.toJSON()).includes('Süt Dişleri'));
 await renderer.act(async()=>tree.unmount());
});


test('a manual dentition toggle is not overridden by a late initial-focus response',async()=>{
 focused=true;lastEvent=null;appListeners=[];const focus=deferred();
 const Chart=chartComponent({getPatient:async()=>patient(8),getToothChartFocus:()=>focus.promise});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const primaryToggle=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Süt Dişleri'));
 assert.ok(primaryToggle);
 await renderer.act(async()=>primaryToggle.props.onPress());
 await renderer.act(async()=>{focus.resolve('36');await flush()});
 const currentPrimaryToggle=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Süt Dişleri'));
 assert.equal(currentPrimaryToggle.props.accessibilityState.selected,true);
 const selectedTeeth=tree.root.findAllByType('Pressable').filter(node=>node.props.accessibilityState?.selected===true&&String(node.props.accessibilityLabel||'').match(/^Diş \d/)&&String(node.props.accessibilityLabel||'').startsWith('Diş '));
 assert.equal(selectedTeeth.length,0,'manual dentition choice must win over the delayed web focus');
 await renderer.act(async()=>tree.unmount());
});

test('a delayed initial-focus response never overrides a tooth selected by the clinician',async()=>{
 focused=true;lastEvent=null;appListeners=[];const focus=deferred();
 const Chart=chartComponent({getPatient:async()=>patient(8),getToothChartFocus:()=>focus.promise});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const tooth=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 11, Sağlıklı');
 assert.ok(tooth);
 await renderer.act(async()=>tooth.props.onPress());
 await renderer.act(async()=>{focus.resolve('36');await flush()});
 const selected=tree.root.findAllByType('Pressable').filter(node=>node.props.accessibilityState?.selected===true&&String(node.props.accessibilityLabel||'').match(/^Diş \d/)&&String(node.props.accessibilityLabel||'').startsWith('Diş '));
 assert.equal(selected.length,1);
 assert.equal(selected[0].props.accessibilityLabel,'Diş 11, Sağlıklı');
 await renderer.act(async()=>tree.unmount());
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
 await renderer.act(async()=>{appListeners.slice().forEach(listener=>listener('background'));appListeners.slice().forEach(listener=>listener('active'))});
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
 await renderer.act(async()=>{appListeners.slice().forEach(listener=>listener('background'));appListeners.slice().forEach(listener=>listener('active'))});
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
  getToothTreatments:async()=>({items:[record],next_cursor:null}),
  updateTreatment:async(...args)=>{calls.push(args);return{ok:true,treatment_id:7,edit_revision:'d'.repeat(64),replayed:false};}
 };
 const Chart=chartComponent(api);let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press('Diş 11, Sağlıklı');await press('Tedavi Geçmişi');await renderer.act(async()=>{await flush();await flush()});await press('Düzenle');
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
 const Chart=chartComponent({getPatient:async()=>({...patient(8),treatments:[legacy]}),getToothTreatments:async()=>({items:[legacy],next_cursor:null}),updateTreatment:async()=>{updates++;return{ok:true,treatment_id:4,edit_revision:'f'.repeat(64),replayed:false}}});
 let tree;
 const press=async(label)=>{const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));assert.ok(item,'missing control '+label);await renderer.act(async()=>item.props.onPress())};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press('Diş 11, Sağlıklı');await press('Tedavi Geçmişi');await renderer.act(async()=>{await flush();await flush()});await press('Düzenle');
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


test('native tooth chart labels patient right and left and preserves web FDI quadrant order',async()=>{
 focused=true;lastEvent=null;appListeners=[];const Chart=chartComponent({getPatient:async()=>patient(8)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const exactText=tree.root.findAllByType('Text').map(node=>flat(node.children));
 assert.equal(exactText.filter(value=>value==='Sağ').length,2,'each jaw must label the patient right side');
 assert.equal(exactText.filter(value=>value==='Sol').length,2,'each jaw must label the patient left side');
 const fdi=tree.root.findAllByType('Pressable').map(node=>node.props.accessibilityLabel).filter(value=>typeof value==='string'&&value.startsWith('Diş ')).map(value=>value.match(/^Diş (\d+)/)?.[1]);
 assert.deepEqual(fdi,['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28','48','47','46','45','44','43','42','41','31','32','33','34','35','36','37','38']);
 await renderer.act(async()=>tree.unmount());
});

test('native tooth detail panel can be closed like the web sheet without changing chart records',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const Chart=chartComponent({getPatient:async()=>patient(8)});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const tooth=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 11, Sağlıklı');
 assert.ok(tooth);
 await renderer.act(async()=>tooth.props.onPress());
 const close=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş panelini kapat');
 assert.ok(close,'web tooth sheet exposes a close action');
 assert.equal(close.props.accessibilityRole,'button');
 assert.ok(close.props.accessibilityHint);
 await renderer.act(async()=>close.props.onPress());
 assert.equal(tree.root.findAllByType('Pressable').filter(node=>node.props.accessibilityLabel==='Diş panelini kapat').length,0);
 const stillOnChart=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 11, Sağlıklı');
 assert.ok(stillOnChart,'closing details must not remove the tooth from the chart');
 assert.equal(stillOnChart.props.accessibilityState.selected,false);
 assert.equal(tree.root.findAllByType('TextInput').filter(node=>node.props.accessibilityLabel==='Diş notları').length,0);
 await renderer.act(async()=>tree.unmount());
});

test('pending treatment intent prevents closing the selected tooth panel',async()=>{
 focused=true;lastEvent=null;appListeners=[];const storage=new Map();
 const Chart=chartComponent({
  getPatient:async()=>patient(8),
  createTreatment:async()=>{throw Object.assign(new Error('Synthetic uncertain response'),{status:503})}
 },storage);
 let tree;
 const press=async(label)=>{
  const item=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel===label||node.findAllByType('Text').some(child=>flat(child.children).includes(label)));
  assert.ok(item,'missing control '+label);
  await renderer.act(async()=>item.props.onPress());
 };
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 await press('Diş 11, Sağlıklı');
 await press('Tedavi Geçmişi');
 const input=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Tedavi adı');
 assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Synthetic treatment'));
 await press('Tedavi Kaydı Ekle');
 await renderer.act(async()=>{await flush();await flush()});
 assert.ok(storage.has('dai.treatment.1.8'),'uncertain treatment intent must remain durable');
 const close=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş panelini kapat');
 assert.ok(close);
 assert.equal(close.props.disabled,true,'a pending durable intent must not be hidden behind a closed tooth panel');
 await press('Diş Bilgisi');
 const status=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş durumu: Çürük');
 const pin=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Mesial yüzeyini seç');
 const note=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Diş klinik notu');
 const save=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children).includes('Durumu Kaydet')));
 assert.equal(status.props.disabled,true,'tooth status cannot change while a treatment receipt is unresolved');
 assert.equal(pin.props.disabled,true,'surface selection cannot change while a treatment receipt is unresolved');
 assert.equal(note.props.editable,false,'clinical notes remain read-only while a treatment receipt is unresolved');
 await press('Notlar');
 const notesInput=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Diş notları');
 assert.equal(notesInput.props.editable,false,'the notes tab must also remain read-only while a treatment receipt is unresolved');
 await press('Diş Bilgisi');
 const saveAfterNotes=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children).includes('Durumu Kaydet')));
 assert.equal(saveAfterNotes.props.disabled,true,'tooth status cannot be saved while a treatment receipt is unresolved');
 await renderer.act(async()=>tree.unmount());
});

test('tooth chart clinical mutation gate stays closed until the durable treatment intent is known',()=>{
 const {toothChartClinicalMutationBlocked}=require('../src/toothChartPresentation.ts');
 const ready={treatmentIntentReady:true,treatmentIntentBlocked:false,treatmentUncertain:false,hasPendingTreatment:false};
 assert.equal(toothChartClinicalMutationBlocked(ready),false);
 for(const patch of [
  {treatmentIntentReady:false},{treatmentIntentBlocked:true},
  {treatmentUncertain:true},{hasPendingTreatment:true}
 ]) assert.equal(toothChartClinicalMutationBlocked({...ready,...patch}),true,JSON.stringify(patch));
});

test('tooth chart remains read-only while SecureStore treatment intent restoration is pending',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const read=deferred(),storage=new Map();
 storage.set('__getItemAsync',()=>read.promise);
 const Chart=chartComponent({getPatient:async()=>patient(8)},storage);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();});
 assert.ok(flat(tree.toJSON()).includes('Güvenli tedavi kaydı kontrol ediliyor'));
 const teeth=tree.root.findAllByType('Pressable').filter(node=>String(node.props.accessibilityLabel||'').match(/^Diş \d/)&&String(node.props.accessibilityLabel||'').startsWith('Diş ')&&/^Diş \d{2},/.test(node.props.accessibilityLabel));
 assert.ok(teeth.length>0);
 assert.ok(teeth.every(node=>node.props.disabled===true),'tooth selection must stay locked until SecureStore restore finishes');
 read.resolve(null);
 await renderer.act(async()=>{await flush();await flush()});
 const available=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 11, Sağlıklı');
 assert.equal(available.props.disabled,false,'the chart unlocks after an empty, successful restore');
 await renderer.act(async()=>tree.unmount());
});

test('tooth chart rejects a patient response outside the requested patient scope',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const Chart=chartComponent({getPatient:async()=>patient(9)});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const content=flat(tree.toJSON());
 assert.ok(content.includes('Sunucu farklı bir hasta kaydı döndürdü.'));
 assert.ok(!content.includes('Synthetic'),"a different patient's chart must never render");
 await renderer.act(async()=>tree.unmount());
});

test('corrupt treatment intent keeps the entire tooth chart read-only',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const storage=new Map([['dai.treatment.1.8','not-json']]);
 const Chart=chartComponent({getPatient:async()=>patient(8)},storage);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 assert.ok(flat(tree.toJSON()).includes('Bekleyen tedavi taslağı okunamadı.'));
 const teeth=tree.root.findAllByType('Pressable').filter(node=>String(node.props.accessibilityLabel||'').match(/^Diş \d/)&&String(node.props.accessibilityLabel||'').startsWith('Diş ')&&/^Diş \d{2},/.test(node.props.accessibilityLabel));
 assert.ok(teeth.length>0);
 assert.ok(teeth.every(node=>node.props.disabled===true));
 await renderer.act(async()=>tree.unmount());
});


test('native tooth history shows web-equivalent surface status, note and timestamp',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const detail=patient(8,'Ada');
 detail.surfaces=[{id:5,tooth_number:'11',surface:'MESIAL',status:'CARIES',note:'Mesial clinical note',updated_at:'2026-11-17T09:15:00'},{id:6,tooth_number:'11',surface:'BUCCAL',status:'ROOT_CANAL',note:'Buccal clinical note',updated_at:'2026-11-17T10:30:00'}];
 const Chart=chartComponent({getPatient:async()=>detail});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 const tooth=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 11, Sağlıklı');
 assert.ok(tooth);
 await renderer.act(async()=>tooth.props.onPress());
 const history=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Tedavi Geçmişi'));
 assert.ok(history);
 await renderer.act(async()=>history.props.onPress());
 const rendered=flat(tree.toJSON());
 assert.match(rendered,/Yüzey durumları/);
 assert.match(rendered,/Mesial/);
 assert.match(rendered,/Çürük/);
 assert.match(rendered,/Mesial clinical note/);
 assert.match(rendered,/Bukkal \/ Vestibül/);
 assert.match(rendered,/Kanal Tedavisi/);
 assert.match(rendered,/Buccal clinical note/);
 assert.match(rendered,/09:15/);
 assert.match(rendered,/10:30/);
 await renderer.act(async()=>tree.unmount());
});



test('native tooth and surface writes carry the exact loaded observation revision',()=>{
 const chart=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
 const api=fs.readFileSync(require.resolve('../src/api.ts'),'utf8');
 assert.match(chart,/expected_revision:currentTooth\?\.revision\?\?null/);
 assert.match(chart,/expected_revision:currentSurface\?\.revision\?\?null/);
 assert.match(api,/expected_revision:string\|null/);
 assert.ok(api.includes('payload.expected_revision!==null&&!/^[a-f0-9]{64}$/.test'));
 assert.ok(api.includes('surface_revisions?:Record<string,string|null>'));
});

test('tooth chart loads the complete treatment history in bounded pages',async()=>{
 focused=true;lastEvent=null;appListeners=[];const calls=[];
 const detail=patient(8);detail.teeth.push({id:2,tooth_number:'36',status:'CARIES',note:''});
 const item=(id,name)=>({id,tooth_number:'36',treatment_name:name,treatment_date:'2026-11-18',material:'',doctor_note:'',result:'',edit_revision:'a'.repeat(64),created_at:'2026-11-18T10:00:00'});
 const cursor='A'.repeat(32);
 const Chart=chartComponent({
  getPatient:async()=>detail,
  getToothChartFocus:async()=>null,
  getToothTreatments:async(_token,patientId,tooth,c)=>{calls.push({patientId,tooth,cursor:c});return c
   ?{items:[item(2,'Older crown treatment')],next_cursor:null}
   :{items:[item(1,'Recent filling treatment')],next_cursor:cursor};}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 const tooth=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş 36, Çürük');
 assert.ok(tooth);
 await renderer.act(async()=>tooth.props.onPress());
 const tab=()=>tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Tedavi Geçmişi'));
 assert.ok(tab());
 await renderer.act(async()=>tab().props.onPress());
 await renderer.act(async()=>{await flush();await flush()});
 assert.deepEqual(calls,[{patientId:8,tooth:'36',cursor:undefined}]);
 assert.match(flat(tree.toJSON()),/Recent filling treatment/);
 assert.doesNotMatch(flat(tree.toJSON()),/Older crown treatment/);
 const more=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Daha eski tedavileri göster'));
 assert.ok(more);
 await renderer.act(async()=>more.props.onPress());
 await renderer.act(async()=>{await flush();await flush()});
 assert.deepEqual(calls[1],{patientId:8,tooth:'36',cursor});
 assert.match(flat(tree.toJSON()),/Recent filling treatment/);
 assert.match(flat(tree.toJSON()),/Older crown treatment/);
 await renderer.act(async()=>tree.unmount());
});

test('a late tooth-history response cannot appear after switching to another FDI tooth',async()=>{
 focused=true;lastEvent=null;appListeners=[];const old=deferred(),calls=[];
 const detail=patient(8);detail.teeth.push(
  {id:2,tooth_number:'36',status:'CARIES',note:''},
  {id:3,tooth_number:'37',status:'HEALTHY',note:''}
 );
 const item=(id,tooth,name)=>({id,tooth_number:tooth,treatment_name:name,edit_revision:'b'.repeat(64),created_at:'2026-11-18T10:00:00'});
 const Chart=chartComponent({
  getPatient:async()=>detail,
  getToothChartFocus:async()=>null,
  getToothTreatments:async(_token,_patientId,tooth)=>{calls.push(tooth);return tooth==='36'?old.promise:{items:[item(2,'37','Only tooth 37 treatment')],next_cursor:null};}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 const select=number=>tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş '+number+', '+(number==='36'?'Çürük':'Sağlıklı'));
 await renderer.act(async()=>select('36').props.onPress());
 const tab=()=>tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Tedavi Geçmişi'));
 await renderer.act(async()=>tab().props.onPress());
 await renderer.act(async()=>select('37').props.onPress());
 await renderer.act(async()=>tab().props.onPress());
 await renderer.act(async()=>{await flush();await flush()});
 assert.deepEqual(calls,['36','37']);
 await renderer.act(async()=>{old.resolve({items:[item(1,'36','Private tooth 36 treatment')],next_cursor:null});await flush();await flush()});
 assert.match(flat(tree.toJSON()),/Only tooth 37 treatment/);
 assert.doesNotMatch(flat(tree.toJSON()),/Private tooth 36 treatment/);
 await renderer.act(async()=>tree.unmount());
});


test('every tooth-chart patient refresh explicitly requests FDI chart collections',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
 const chartReads=source.match(/getPatient\(token,patientId,true\)/g)||[];
 assert.equal(chartReads.length,7,'initial, foreground, realtime, post-mutation and explicit conflict-refresh reads must opt in');
 assert.doesNotMatch(source,/getPatient\(token,patientId\)(?!,true)/,'no chart refresh may silently receive the profile-only payload');
});


test('tooth history tab scopes analyses and cursor-paged treatments to the selected FDI tooth',async()=>{
 focused=true;lastEvent=null;appListeners=[];
 const calls=[];
 const Chart=chartComponent({
  getPatient:async()=>patient(8),
  getToothTreatments:async(_token,_patientId,tooth,cursor)=>{
   calls.push({tooth,cursor:cursor??null});
   return cursor?{items:[],next_cursor:null}:{items:[],next_cursor:'cursor-older'};
  }
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush()});
 const press=async(label)=>{
  const item=tree.root.findAllByType('Pressable').find(node=>
   node.props.accessibilityLabel===label||
   node.findAllByType('Text').some(child=>flat(child.children).includes(label))
  );
  assert.ok(item,'missing control '+label);
  await renderer.act(async()=>item.props.onPress());
 };
 await press('Diş 36, Sağlıklı');
 await press('Tedavi Geçmişi');
 await renderer.act(async()=>{await flush();await flush()});
 const analysisHistory=tree.root.findAllByType('Child').find(node=>node.props.toothNumber==='36');
 assert.ok(analysisHistory,'analysis history must be scoped to the selected FDI tooth');
 assert.equal(analysisHistory.props.patientId,8);
 assert.deepEqual(calls,[{tooth:'36',cursor:null}]);
 await press('Daha eski tedavileri göster');
 assert.deepEqual(calls,[{tooth:'36',cursor:null},{tooth:'36',cursor:'cursor-older'}]);
 await renderer.act(async()=>tree.unmount());
});


test('a stale whole-tooth save requires an explicit refresh and preserves the clinician draft',async()=>{
 focused=false;lastEvent=null;appListeners=[];
 const initial=patient(8,'Ada','HEALTHY',35);
 initial.teeth[0].revision='a'.repeat(64);
 const remote=patient(8,'Ada','FILLING',35);
 remote.teeth[0].revision='b'.repeat(64);
 remote.teeth[0].note='Remote note';
 let reads=0;const writes=[];
 const Chart=chartComponent({
  getPatient:async()=>++reads===1?initial:remote,
  updateTooth:async(...args)=>{
   writes.push(args[3]);
   if(writes.length===1)throw Object.assign(new Error('stale tooth revision'),{status:409});
   return{ok:true};
  }
 });
 let tree;
 const press=async(label)=>{
  const item=tree.root.findAllByType('Pressable').find(node=>
   node.props.accessibilityLabel===label||
   node.findAllByType('Text').some(child=>flat(child.children)===label)
  );
  assert.ok(item,'missing control '+label);
  await renderer.act(async()=>item.props.onPress());
 };
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 await press('Diş 11, Sağlıklı');
 await press('Diş durumu: Çürük');
 await press('Durumu Kaydet');
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(writes.length,1);
 let save=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Durumu Kaydet'));
 assert.ok(save);
 assert.equal(save.props.disabled,true,'a stale revision cannot be submitted again');
 assert.ok(tree.root.findAllByType('Pressable').some(node=>node.props.accessibilityLabel==='Güncel diş kaydını yükle'));
 await press('Güncel diş kaydını yükle');
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(writes.length,1,'refresh must never auto-save or replay the draft');
 assert.match(flat(tree.toJSON()),/Sunucudaki son durum: Dolgu\. Not: Remote note/);
 save=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Durumu Kaydet'));
 assert.equal(save.props.disabled,false,'the explicit refresh enables a deliberate retry');
 await press('Durumu Kaydet');
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(writes.length,2);
 assert.equal(writes[1].expected_revision,'b'.repeat(64),'retry must use the refreshed server revision');
 await renderer.act(async()=>tree.unmount());
});

test('a stale surface save refreshes the correct FDI surface while retaining its independent draft',async()=>{
 focused=false;lastEvent=null;appListeners=[];
 const initial=patient(8,'Ada','HEALTHY',35);
 initial.surfaces=[{id:4,tooth_number:'11',surface:'INCISAL',status:'HEALTHY',note:'Old surface note',revision:'c'.repeat(64)}];
 const remote=patient(8,'Ada','HEALTHY',35);
 remote.surfaces=[{id:4,tooth_number:'11',surface:'INCISAL',status:'FILLING',note:'Remote surface note',revision:'d'.repeat(64)}];
 let reads=0;const writes=[];
 const Chart=chartComponent({
  getPatient:async()=>++reads===1?initial:remote,
  updateToothSurface:async(...args)=>{
   writes.push(args[4]);
   if(writes.length===1)throw Object.assign(new Error('stale surface revision'),{status:409});
   return{ok:true};
  }
 });
 let tree;
 const press=async(label)=>{
  const item=tree.root.findAllByType('Pressable').find(node=>
   node.props.accessibilityLabel===label||
   node.findAllByType('Text').some(child=>flat(child.children)===label)
  );
  assert.ok(item,'missing control '+label);
  await renderer.act(async()=>item.props.onPress());
 };
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 await press('Diş 11, Sağlıklı');
 const incisal=tree.root.findAllByType('Pressable').filter(node=>node.findAllByType('Text').some(child=>flat(child.children)==='İnsizal')).at(-1);
 assert.ok(incisal,'independent incisal surface editor must be available for FDI 11');
 await renderer.act(async()=>incisal.props.onPress());
 const caries=tree.root.findAllByType('Pressable').filter(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Çürük')).at(-1);
 assert.ok(caries,'surface-specific status control must be available');
 await renderer.act(async()=>caries.props.onPress());
 const note=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Yüzey klinik notu');
 assert.ok(note);
 await renderer.act(async()=>note.props.onChangeText('Local surface draft'));
 await press('Yüzeyi Kaydet');
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(writes.length,1);
 const save=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Yüzeyi Kaydet'));
 assert.ok(save);
 assert.equal(save.props.disabled,true,'stale surface revision must block another write');
 await press('Güncel diş kaydını yükle');
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(writes.length,1,'surface refresh must not write the local draft');
 assert.match(flat(tree.toJSON()),/Sunucudaki son durum: Dolgu\. Not: Remote surface note/);
 const preserved=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Yüzey klinik notu');
 assert.equal(preserved.props.value,'Local surface draft');
 const retry=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>flat(child.children)==='Yüzeyi Kaydet'));
 assert.equal(retry.props.disabled,false);
 await press('Yüzeyi Kaydet');
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(writes.length,2);
 assert.equal(writes[1].expected_revision,'d'.repeat(64),'surface retry must use the refreshed surface revision');
 await renderer.act(async()=>tree.unmount());
});


test('a late conflict refresh cannot reopen a tooth panel after the clinician closes it',async()=>{
 focused=false;lastEvent=null;appListeners=[];
 const initial=patient(8,'Ada','HEALTHY',35);
 initial.teeth[0].revision='a'.repeat(64);
 const pendingRefresh=deferred();let reads=0;
 const Chart=chartComponent({
  getPatient:async()=>++reads===1?initial:pendingRefresh.promise,
  updateTooth:async()=>{throw Object.assign(new Error('stale tooth revision'),{status:409});}
 });
 let tree;
 const press=async(label)=>{
  const item=tree.root.findAllByType('Pressable').find(node=>
   node.props.accessibilityLabel===label||
   node.findAllByType('Text').some(child=>flat(child.children)===label)
  );
  assert.ok(item,'missing control '+label);
  await renderer.act(async()=>item.props.onPress());
 };
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Chart,{token:'account-a',patientId:8}));await flush();await flush()});
 await press('Diş 11, Sağlıklı');
 await press('Diş durumu: Çürük');
 await press('Durumu Kaydet');
 await renderer.act(async()=>{await flush();await flush()});
 const refresh=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Güncel diş kaydını yükle');
 assert.ok(refresh);
 await renderer.act(async()=>{refresh.props.onPress();});
 await renderer.act(async()=>{await flush()});
 const close=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Diş panelini kapat');
 assert.ok(close);
 await renderer.act(async()=>close.props.onPress());
 pendingRefresh.resolve(patient(8,'Ada','FILLING',35));
 await renderer.act(async()=>{await flush();await flush()});
 assert.equal(tree.root.findAllByType('Pressable').some(node=>node.props.accessibilityLabel==='Güncel diş kaydını yükle'),false);
 assert.doesNotMatch(flat(tree.toJSON()),/Sunucudaki son durum/);
 await renderer.act(async()=>tree.unmount());
});
