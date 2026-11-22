const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const sessionRenderKeyExports=require('./helpers/sessionRenderKeyModule.cjs');
const useSessionRenderKeyExports=require('./helpers/useSessionRenderKeyModule.cjs');
const compile=f=>ts.transpileModule(fs.readFileSync(require.resolve(f),'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
const revision='a'.repeat(64),base={analysis_id:1,patient_id:8,patient_anonymous_id:'SYNTHETIC-008',status:'AI_ANALYZED',revision,result:{status:'INITIAL',most_likely:'Synthetic likely condition',findings:['Synthetic string finding'],treatment_options:['Synthetic treatment'],treatment_cautions:['Synthetic caution'],preferred_approach:'Synthetic preferred approach',differential:['Synthetic differential'],recommended_evaluation:['Synthetic clinical exam'],uncertainty:'Synthetic uncertainty',questions:[{question:'Synthetic question?',type:'TEXT'}]},assets:[],clinical_notes:null,tooth_number:null,job:null};
const apiBase=fs.readFileSync(require.resolve('../src/api.ts'),'utf8').match(/export const API_BASE = "([^"]+)"/)?.[1];
assert.ok(apiBase,'canonical mobile API base must be exported');
function api(request=async()=>({})){const exports={};vm.runInNewContext(compile('../src/clinicalApi.ts'),{exports,Error,require:()=>({request,API_BASE:apiBase})});return exports}
function harness(overrides={},saved,initialFocused=true){const exports={},storage=new Map(),calls=[],a=api(),focus={current:initialFocused};if(saved)storage.set('dai.clinical.final.1.1',JSON.stringify(saved));const secure={getItemAsync:async k=>storage.get(k)||null,setItemAsync:async(k,v)=>storage.set(k,v),deleteItemAsync:async k=>storage.delete(k)},native={StyleSheet:{create:x=>x},AppState:{currentState:'active',addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Image','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const endpoint={...a,getClinical:async()=>base,submitClinical:async(_t,intent)=>{calls.push(intent);return{ok:true,job:{id:7,kind:'FINAL',status:'QUEUED'}}},saveClinicalNote:async()=>({ok:true}),...overrides};
 const finding={};vm.runInNewContext(compile('../src/findings.ts'),{exports:finding});const presentation={};vm.runInNewContext(compile('../src/clinicalResultPresentation.ts'),{exports:presentation});
 vm.runInNewContext(compile('../src/NativeClinicalReview.tsx'),{exports,setTimeout,clearTimeout,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{useIsFocused:()=>focus.current}:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=> 'synthetic-key'}:n==='./socialDraft'?{chunkedDraftStore:()=>secure}:n==='./clinicalApi'?endpoint:n==='./findings'?finding:n==='./clinicalResultPresentation'?presentation:n==='./useSessionRenderKey'?useSessionRenderKeyExports:{default:props=>React.createElement('Text',null,props.value)}});return{Component:exports.default,calls,storage,endpoint,focus};}
async function open(h,props={}){let t;await renderer.act(async()=>t=renderer.create(React.createElement(h.Component,{token:'A',userId:1,analysisId:1,...props})));return t}
test('single-tooth analysis uses the owner-scoped mobile route and validates its durable job receipt',async()=>{
 const calls=[];
 const {analyzeTooth}=api(async(...args)=>{calls.push(args);return{ok:true,analysis_id:17,patient_id:8,tooth_fdi:'36',job:{id:7,kind:'PRELIMINARY',status:'QUEUED',retryable:false}}});
 const receipt=await analyzeTooth('synthetic-token',17,'36');
 assert.equal(receipt.job.id,7);assert.equal(calls.length,1);
 assert.equal(calls[0][0],'/analyses/17/tooth/36/analyze');assert.equal(calls[0][1],'synthetic-token');assert.deepEqual(calls[0][2],{method:'POST'});
 await assert.rejects(()=>analyzeTooth('synthetic-token',17,'59'),/Geçersiz FDI/);
 assert.equal(calls.length,1,'invalid FDI must be rejected before the network call');
 const malformed=api(async()=>({ok:true,analysis_id:17,patient_id:8,tooth_fdi:'36',job:{id:0,kind:'PRELIMINARY',status:'QUEUED',retryable:false}}));
 await assert.rejects(()=>malformed.analyzeTooth('synthetic-token',17,'36'),/iş kaydı doğrulanamadı/);
});

test('clinical review wires the per-tooth action through the authenticated clinical API and reloads its durable receipt',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeClinicalReview.tsx'),'utf8');
 assert.match(source,/async function runViewerToothAnalysis\(toothFdi:string\)/);
 assert.match(source,/A\.analyzeTooth\(token,analysisId,toothFdi\)/);
 assert.match(source,/onAnalyzeTooth=\{runViewerToothAnalysis\}/);
 assert.match(source,/started=true;await load\(\)/);
});

test('clinical image source rejects invalid analysis and asset IDs before building a private URL',()=>{
 const {clinicalImage}=api();
 assert.throws(()=>clinicalImage('synthetic-token',0,44),/Geçersiz analiz kimliği/);
 assert.throws(()=>clinicalImage('synthetic-token',17,0),/Geçersiz analiz kimliği/);
 assert.throws(()=>clinicalImage('synthetic-token',17,1.5),/Geçersiz analiz kimliği/);
});
test('legacy radiograph fallback uses a scoped private endpoint and never exposes a storage path',()=>{
 const {legacyClinicalImage}=api();
 const source=legacyClinicalImage('synthetic-token',17);
 assert.equal(source.uri,apiBase+'/analyses/17/legacy-radiograph');
 assert.equal(source.headers.Authorization,'Bearer synthetic-token');
 assert.equal(source.headers.Cookie,'');
 assert.equal(source.cache,'reload');
 assert.throws(()=>legacyClinicalImage('synthetic-token',0),/Geçersiz analiz kimliği/);
 assert.throws(()=>legacyClinicalImage('synthetic-token',1.5),/Geçersiz analiz kimliği/);
});

test('legacy radiograph appears in native clinical review and opens a dedicated full-screen preview',async()=>{
 const h=harness(),t=await open(h,{legacyRadiographAvailable:true});
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 const source=apiBase+'/analyses/1/legacy-radiograph';
 const thumbnail=()=>t.root.findAllByType('Image').find(node=>node.props.source?.uri===source);
 assert.ok(thumbnail(),'legacy image is shown when the server explicitly marks it available');
 assert.equal(thumbnail().props.source.headers.Authorization,'Bearer A');
 assert.equal(thumbnail().props.source.cache,'reload');
 const opener=t.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='Eski kayıtlı radyografiyi büyüt');
 assert.ok(opener,'legacy preview has an accessible open action');
 await renderer.act(async()=>opener.props.onPress());
 const modal=()=>t.root.findAllByType('Modal')[0];
 assert.equal(modal().props.visible,true);
 assert.ok(t.root.findAllByType('Image').some(node=>node.props.style?.flex===1),'full-screen preview renders the private image');
 await renderer.act(async()=>button(t,'Kapat').props.onPress());
 assert.equal(t.root.findAllByType('Modal').length,0,'closing the preview unmounts the modal');
 await renderer.act(async()=>t.unmount());
});

test('legacy radiograph fallback fails closed when modern assets exist or the server flag is false',async()=>{
 const modern=harness({getClinical:async()=>({...base,assets:[{id:44,image_type:'PANORAMIC',has_vision:true,url:'/api/mobile/v1/analyses/1/assets/44'}]})});
 const t=await open(modern,{legacyRadiographAvailable:true});
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 assert.ok(t.root.findAllByType('Image').some(node=>node.props.source?.uri===apiBase+'/analyses/1/assets/44'));
 assert.ok(!t.root.findAllByType('Image').some(node=>node.props.source?.uri===apiBase+'/analyses/1/legacy-radiograph'));
 await renderer.act(async()=>t.unmount());
 const old=harness(),next=await open(old,{legacyRadiographAvailable:false});
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 assert.ok(!next.root.findAllByType('Image').some(node=>node.props.source?.uri===apiBase+'/analyses/1/legacy-radiograph'));
 await renderer.act(async()=>next.unmount());
});

test('legacy radiograph image failure can be retried without changing its authorized endpoint',async()=>{
 const h=harness(),t=await open(h,{legacyRadiographAvailable:true});
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 const source=apiBase+'/analyses/1/legacy-radiograph';
 const thumbnail=()=>t.root.findAllByType('Image').find(node=>node.props.source?.uri===source);
 await renderer.act(async()=>thumbnail().props.onError());
 assert.ok(text(t.toJSON()).includes('Eski radyografi yüklenemedi.'));
 await renderer.act(async()=>button(t,'Görüntüyü Yeniden Yükle').props.onPress());
 assert.ok(!text(t.toJSON()).includes('Eski radyografi yüklenemedi.'));
 assert.ok(thumbnail(),'retry retains the same owner-authorized API route');
 await renderer.act(async()=>t.unmount());
});
test('vision snapshot requests bypass HTTP cache like the web embedded viewer',async()=>{
 const calls=[];
 const {getVision}=api(async(...args)=>{calls.push(args);return{status:'VISION_PENDING'}});
 const result=await getVision('synthetic-token',17,23,'PANORAMIC');
 assert.equal(calls.length,1);
 assert.equal(calls[0][0],'/analyses/17/assets/23/vision');
 assert.equal(calls[0][1],'synthetic-token');
 assert.equal(calls[0][2]?.cache,'no-store');
 assert.deepEqual(Object.keys(calls[0][2]||{}),['cache']);
 assert.equal(result.pending,true);
 assert.deepEqual(Array.from(result.findings||[]),[]);
});
test('clinical image thumbnails use the canonical API base, reload privately and remount on account switch',async()=>{
 const h=harness({getClinical:async()=>({...base,assets:[{id:44,image_type:'PANORAMIC',has_vision:true,url:'/api/mobile/v1/analyses/1/assets/44'}]})});
 const t=await open(h);
 const image=()=>t.root.findAllByType('Image').find(node=>node.props.source?.uri===apiBase+'/analyses/1/assets/44');
 const first=image();
 assert.ok(first,'clinical asset thumbnail is rendered');
 assert.equal(first.props.source.cache,'reload');
 assert.equal(first.props.source.headers.Authorization,'Bearer A');
 const clinicalSource=fs.readFileSync(require.resolve('../src/NativeClinicalReview.tsx'),'utf8');
 assert.ok(clinicalSource.includes("key={viewerSessionKey+':'+analysisId+':'+asset.id}"),'thumbnail Image must remount with an opaque session identity');
 assert.ok(!clinicalSource.includes("key={userId+':'+analysisId+':'+asset.id}")&&!clinicalSource.includes("key={token+':'+analysisId+':'+asset.id}"),'thumbnail key must not expose account identifiers or credentials');
 await renderer.act(async()=>{t.update(React.createElement(h.Component,{token:'B',userId:2,analysisId:1}));});
 const second=image();
 assert.ok(second,'thumbnail remains available after authenticated account change');
 assert.equal(second.props.source.cache,'reload');
 assert.equal(second.props.source.headers.Authorization,'Bearer B');
 await renderer.act(async()=>t.unmount());
});
test('transient initial clinical workspace failure can recover with refresh without remount',async()=>{let attempts=0;const h=harness({getClinical:async()=>{attempts++;if(attempts===1)throw Object.assign(Error('Synthetic temporary service failure'),{status:503});return base}}),t=await open(h);await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});assert.equal(attempts,1);assert.equal(button(t,'Klinik Sonucu Yenile').props.disabled,false);assert.ok(text(t.toJSON()).includes('Synthetic temporary service failure'));await renderer.act(async()=>{button(t,'Klinik Sonucu Yenile').props.onPress();await new Promise(r=>setImmediate(r))});assert.equal(attempts,2);assert.ok(text(t.toJSON()).includes('Synthetic likely condition'));assert.ok(!text(t.toJSON()).includes('Synthetic temporary service failure'));await renderer.act(async()=>t.unmount())});
test('clinical workspace refresh key publishes the latest durable job snapshot to its parent',async()=>{
 let calls=0;const snapshots=[];
 const h=harness({getClinical:async()=>{calls++;return calls===1?{...base,status:'ANALYZING',job:{id:9,kind:'VISION',status:'RUNNING',retryable:false}}:{...base,status:'VISION_READY',job:{id:9,kind:'VISION',status:'DONE',retryable:false}}}});
 const onWorkspaceChange=value=>snapshots.push(value),t=await open(h,{refreshKey:0,onWorkspaceChange});
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 assert.equal(calls,1);assert.equal(snapshots[0].analysis_id,1);assert.equal(snapshots[0].patient_id,8);assert.equal(snapshots[0].job.status,'RUNNING');
 await renderer.act(async()=>{t.update(React.createElement(h.Component,{token:'A',userId:1,analysisId:1,refreshKey:1,onWorkspaceChange}));await new Promise(r=>setImmediate(r))});
 assert.equal(calls,2);assert.equal(snapshots.at(-1).status,'VISION_READY');assert.equal(snapshots.at(-1).job.status,'DONE');
 await renderer.act(async()=>t.unmount());
});
test('hidden clinical workspace defers realtime refresh until the screen is focused',async()=>{
 let calls=0;const h=harness({getClinical:async()=>{calls++;return base}},undefined,false),onWorkspaceChange=()=>{},t=await open(h,{refreshKey:0,onWorkspaceChange});
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});assert.equal(calls,1);
 await renderer.act(async()=>{t.update(React.createElement(h.Component,{token:'A',userId:1,analysisId:1,refreshKey:1,onWorkspaceChange}));await new Promise(r=>setImmediate(r))});
 assert.equal(calls,1);
 h.focus.current=true;
 await renderer.act(async()=>{t.update(React.createElement(h.Component,{token:'A',userId:1,analysisId:1,refreshKey:1,onWorkspaceChange}));await new Promise(r=>setImmediate(r))});
 assert.equal(calls,2);
 await renderer.act(async()=>t.unmount());
});
test('native clinical review displays web string findings, treatment and uncertainty',async()=>{const h=harness(),t=await open(h),content=text(t.toJSON());for(const v of ['Synthetic string finding','Synthetic treatment','Synthetic caution','Synthetic clinical exam','Synthetic uncertainty'])assert.ok(content.includes(v),v);assert.ok(!content.includes('Model güveni: %'));await renderer.act(async()=>t.unmount())});
test('final evaluation requires all answers and clinician consent; double tap queues once',async()=>{const h=harness(),t=await open(h);assert.equal(button(t,'Yeni Bilgilerle Tekrar Analiz Et').props.disabled,true);await renderer.act(async()=>t.root.findByType('TextInput').props.onChangeText('Synthetic clinical answer'));assert.equal(button(t,'Yeni Bilgilerle Tekrar Analiz Et').props.disabled,true);await renderer.act(async()=>t.root.findAllByType('Pressable').find(n=>n.props.accessibilityRole==='checkbox').props.onPress());await renderer.act(async()=>{const b=button(t,'Yeni Bilgilerle Tekrar Analiz Et');b.props.onPress();b.props.onPress();await new Promise(r=>setImmediate(r))});assert.equal(h.calls.length,1);assert.equal(h.calls[0].answers.answer_0,'Synthetic clinical answer');assert.equal(h.calls[0].revision,revision);assert.equal(h.storage.size,0);await renderer.act(async()=>t.unmount())});
test('uncertain final submission retains exact answers and revision across reopen',async()=>{const saved={user:1,analysis:1,revision,answers:{answer_0:'Original synthetic answer'}},calls=[],h=harness({submitClinical:async(_t,intent)=>{calls.push(intent);throw Error('Synthetic uncertain response')}},saved),t=await open(h);await renderer.act(async()=>button(t,'Bekleyen Klinik Cevapları Doğrula').props.onPress());assert.equal(calls[0].revision,revision);assert.equal(calls[0].answers.answer_0,saved.answers.answer_0);assert.ok(h.storage.has('dai.clinical.final.1.1'));await renderer.act(async()=>t.unmount());h.endpoint.submitClinical=async(_t,intent)=>{calls.push(intent);return{ok:true,job:{id:7,kind:'FINAL',status:'DONE'}}};const next=await open(h);await renderer.act(async()=>button(next,'Bekleyen Klinik Cevapları Doğrula').props.onPress());assert.deepEqual(calls[0],calls[1]);assert.equal(h.storage.size,0);await renderer.act(async()=>next.unmount())});
test('a saved clinical intent from another account blocks all final writes',async()=>{const h=harness({}, {user:2,analysis:1,revision,answers:{answer_0:'Other synthetic answer'}}),t=await open(h);assert.equal(h.calls.length,0);assert.ok(text(t.toJSON()).includes('Bekleyen klinik cevap kaydı okunamadı'));await renderer.act(async()=>t.unmount())});
test('uncertain manual note is stored before sending and never auto-retried',async()=>{let calls=0;const h=harness({saveClinicalNote:async()=>{calls++;throw Error('Synthetic ambiguous note')}}),t=await open(h);await renderer.act(async()=>button(t,'Hekim Notu / Diş Seçimi').props.onPress());await renderer.act(async()=>t.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Analiz hekim notu').props.onChangeText('Synthetic note'));await renderer.act(async()=>button(t,'Analize Not Kaydet').props.onPress());assert.equal(calls,1);assert.equal(button(t,'Analize Not Kaydet').props.disabled,true);assert.ok(button(t,'Sunucudaki Notu Kontrol Et'));assert.ok(h.storage.has('dai.clinical.note.1.1'));await renderer.act(async()=>t.unmount())});
test('clinical transport rejects wrong analysis and malformed final receipt',async()=>{const a=api(async()=>({...base,analysis_id:2}));await assert.rejects(()=>a.getClinical('A',1),/doğrulanamadı/);const b=api(async()=>({ok:true,job:{id:0,kind:'FINAL'}}));await assert.rejects(()=>b.submitClinical('A',{user:1,analysis:1,revision,answers:{answer_0:'Synthetic'}}),/doğrulanamadı/);assert.throws(()=>a.parseClinicalIntent(JSON.stringify({user:1,analysis:1,revision,answers:{answer_0:''}}),1,1));});
test('definite stale-source rejection clears old intent and requires fresh clinician answers',async()=>{const saved={user:1,analysis:1,revision,answers:{answer_0:'Old synthetic answer'}},h=harness({submitClinical:async()=>{throw Object.assign(Error('Source changed'),{status:409})}},saved),t=await open(h);await renderer.act(async()=>button(t,'Bekleyen Klinik Cevapları Doğrula').props.onPress());assert.equal(h.storage.size,0);assert.equal(button(t,'Yeni Bilgilerle Tekrar Analiz Et').props.disabled,true);assert.equal(t.root.findByType('TextInput').props.value,'');assert.ok(text(t.toJSON()).includes('Source changed'));await renderer.act(async()=>t.unmount())});


test('tooth chart toggle names its destination and clears selections hidden by the other dentition',async()=>{
 const h=harness(),t=await open(h);
 await renderer.act(async()=>button(t,'Hekim Notu / Diş Seçimi').props.onPress());
 assert.ok(button(t,'Süt Dişlerine Geç'),'permanent dentition is initially shown and toggle names the destination');
 const permanent=t.root.findAllByType('Pressable').find(n=>n.props.accessibilityRole==='checkbox'&&text(n)==='11');
 assert.ok(permanent);
 await renderer.act(async()=>permanent.props.onPress());
 assert.ok(text(t.toJSON()).includes('Seçilen FDI: 11'));
 await renderer.act(async()=>button(t,'Süt Dişlerine Geç').props.onPress());
 assert.ok(button(t,'Kalıcı Dişlere Geç'));
 assert.ok(text(t.toJSON()).includes('Seçilen FDI: Henüz seçilmedi'));
 assert.ok(t.root.findAllByType('Pressable').some(n=>n.props.accessibilityRole==='checkbox'&&text(n)==='51'));
 await renderer.act(async()=>t.unmount());
});

test('clinical result does not expose the raw internal patient database id',async()=>{
 const h=harness(),t=await open(h),rendered=text(t.toJSON());
 assert.ok(rendered.includes('SYNTHETIC-008'));
 assert.ok(!rendered.includes('Hasta #8'));
 assert.ok(!rendered.includes('Hasta kaydı'));
 await renderer.act(async()=>t.unmount());
});


test('clinical workspace rejects duplicate or malformed asset metadata before rendering',async()=>{
 const asset={id:4,image_type:'BITEWING',has_vision:true,url:'/api/mobile/v1/analyses/1/assets/4'};
 const duplicate=api(async()=>({...base,assets:[asset,asset]}));
 await assert.rejects(()=>duplicate.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const malformed=api(async()=>({...base,assets:[{...asset,id:0}]}));
 await assert.rejects(()=>malformed.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const external=api(async()=>({...base,assets:[{...asset,url:'https://example.invalid/private'}]}));
 await assert.rejects(()=>external.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
});

test('clinical workspace rejects malformed job state instead of exposing unsafe retry controls',async()=>{
 const h=api(async()=>({...base,job:{id:7,kind:'FINAL',status:'FAILED',retryable:'yes'}}));
 await assert.rejects(()=>h.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const valid=api(async()=>({...base,job:{id:7,kind:'FINAL',status:'FAILED',retryable:true}}));
 const result=await valid.getClinical('A',1);
 assert.equal(result.job.retryable,true);
});


test('clinical workspace requires a non-empty anonymous patient label',async()=>{
 const missing=api(async()=>{const value={...base};delete value.patient_anonymous_id;return value});
 await assert.rejects(()=>missing.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const empty=api(async()=>({...base,patient_anonymous_id:'  '}));
 await assert.rejects(()=>empty.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const valid=api(async()=>({...base,patient_anonymous_id:'SYNTHETIC-008'}));
 assert.equal((await valid.getClinical('A',1)).patient_anonymous_id,'SYNTHETIC-008');
});


test('NEEDS_INFO status explains the clinical information gap like the web result screen',async()=>{
 const h=harness({getClinical:async()=>({...base,result:{status:'NEEDS_INFO',most_likely:'',questions:[]}})}),t=await open(h),rendered=text(t.toJSON());
 assert.ok(rendered.includes('Kritik klinik bilgiler gerekiyor'));
 assert.ok(rendered.includes('tedavi güvenliğini değiştirebilecek eksik bilgileri'));
 await renderer.act(async()=>t.unmount());
});


test('reopening a clinical review reconciles a note already committed by the server',async()=>{
 const pending={user:1,analysis:1,note:'Synthetic note',finding:'',tooth:'36'};
 const h=harness({getClinical:async()=>({...base,clinical_notes:'[Diş 36] Synthetic note'})});
 h.storage.set('dai.clinical.note.1.1',JSON.stringify(pending));
 const t=await open(h);
 assert.equal(h.storage.has('dai.clinical.note.1.1'),false);
 assert.ok(text(t.toJSON()).includes('Önceki oturumda kaydedilen hekim notu sunucuda doğrulandı.'));
 assert.ok(!text(t.toJSON()).includes('Kaydedilmediğini Doğruladım'));
 await renderer.act(async()=>t.unmount());
});

test('reopening with a note absent from server keeps the exact draft for explicit reconciliation',async()=>{
 const pending={user:1,analysis:1,note:'Synthetic note',finding:'Manual finding',tooth:'36'};
 const h=harness({getClinical:async()=>({...base,clinical_notes:null})});
 h.storage.set('dai.clinical.note.1.1',JSON.stringify(pending));
 const t=await open(h);
 assert.equal(t.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Analiz hekim notu').props.value,'Synthetic note');
 assert.equal(t.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Manuel klinik bulgu').props.value,'Manual finding');
 assert.equal(t.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Analiz hekim notu').props.editable,false);
 assert.equal(t.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Manuel klinik bulgu').props.editable,false);
 assert.ok(button(t,'Sunucudaki Notu Kontrol Et'));
 assert.equal(button(t,'Analize Not Kaydet').props.disabled,true);
 await renderer.act(async()=>button(t,'Sunucudaki Notu Kontrol Et').props.onPress());
 assert.ok(button(t,'Kaydedilmediğini Doğruladım — Aynı Notu Yeniden Dene'));
 await renderer.act(async()=>t.unmount());
});

test('clinical note intent validation is account, analysis and FDI scoped',()=>{
 const a=api();
 const raw=JSON.stringify({user:1,analysis:1,note:'Synthetic',finding:'',tooth:'36'});
 const parsed=a.parseClinicalNoteIntent(raw,1,1);assert.equal(parsed.user,1);assert.equal(parsed.analysis,1);assert.equal(parsed.note,'Synthetic');assert.equal(parsed.finding,'');assert.equal(parsed.tooth,'36');
 assert.throws(()=>a.parseClinicalNoteIntent(raw,2,1),/doğrulanamadı/);
 assert.throws(()=>a.parseClinicalNoteIntent(JSON.stringify({user:1,analysis:1,note:'',finding:'',tooth:'59'}),1,1),/doğrulanamadı/);
 assert.equal(a.clinicalNoteLine({user:1,analysis:1,note:'Extra',finding:'Manual',tooth:'36'}),'[Diş 36] Manuel bulgu: Manual — Extra');
});


test('clinical workspace exposes modality-only asset metadata and rejects filenames or storage paths',async()=>{
 const asset={id:4,image_type:'PERIAPICAL',has_vision:true,url:'/api/mobile/v1/analyses/1/assets/4'};
 const valid=api(async()=>({...base,assets:[asset]}));
 const workspace=await valid.getClinical('A',1);
 assert.deepEqual(Object.keys(workspace.assets[0]).sort(),['has_vision','id','image_type','url']);
 for(const unsafe of [{...asset,name:'patient-secret.png'},{...asset,file_path:'uploads/private.png'},{...asset,image_type:'../private'}]){
  const invalid=api(async()=>({...base,assets:[unsafe]}));
  await assert.rejects(()=>invalid.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 }
});

test('native clinical image cards use modality labels rather than uploaded filenames',async()=>{
 const h=harness({getClinical:async()=>({...base,assets:[{id:4,image_type:'PERIAPICAL',has_vision:true,url:'/api/mobile/v1/analyses/1/assets/4'}]})});
 const t=await open(h),rendered=text(t.toJSON());
 assert.ok(rendered.includes('Periapikal'));
 assert.ok(!rendered.includes('patient-secret.png'));
 await renderer.act(async()=>t.unmount());
});


test('saved clinical note reconciliation recognizes LF and CRLF lines without substring matches',()=>{
 const a=api(),pending={user:1,analysis:1,note:'Synthetic note',finding:'Manual finding',tooth:'36'};
 const line=a.clinicalNoteLine(pending);
 const lf=String.fromCharCode(10),crlf=String.fromCharCode(13)+lf;
 assert.equal(a.clinicalNoteIsPresent(line+lf+'Other note',pending),true);
 assert.equal(a.clinicalNoteIsPresent((line+lf+'Other note').replaceAll(lf,crlf),pending),true);
 assert.equal(a.clinicalNoteIsPresent('prefix '+line,pending),false);
 assert.equal(a.clinicalNoteIsPresent(null,pending),false);
});

test('clinical workspace rejects malformed or oversized result fields before native rendering',async()=>{
 const invalidQuestion=api(async()=>({...base,result:{...base.result,questions:[{question:'Synthetic question?',type:'HTML'}]}}));
 await assert.rejects(()=>invalidQuestion.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const tooLong=api(async()=>({...base,result:{...base.result,preferred_approach:'x'.repeat(4001)}}));
 await assert.rejects(()=>tooLong.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const tooMany=api(async()=>({...base,result:{...base.result,treatment_options:['1','2','3','4']}}));
 await assert.rejects(()=>tooMany.getClinical('A',1),/Klinik sonuç doğrulanamadı/);
 const validFinal=api(async()=>({...base,result:{status:'FINAL',most_likely:'Synthetic likely condition',findings:['Synthetic finding'],treatment_options:['Synthetic treatment'],treatment_cautions:[],preferred_approach:'Synthetic preferred approach',differential:[]}}));
 assert.equal((await validFinal.getClinical('A',1)).result.status,'FINAL');
 const validError=api(async()=>({...base,result:{status:'AI_ERROR',error:'Synthetic provider error'}}));
 assert.equal((await validError.getClinical('A',1)).result.status,'AI_ERROR');
});


test('legacy ANALYSIS_COMPLETE preliminary results keep their web question and consent step',async()=>{
 const h=harness({getClinical:async()=>({...base,result:{...base.result,status:'ANALYSIS_COMPLETE'}})}),t=await open(h);
 const rendered=text(t.toJSON());
 assert.ok(rendered.includes('Hekime Sorular'));
 assert.ok(rendered.includes('Synthetic question?'));
 assert.ok(button(t,'Yeni Bilgilerle Tekrar Analiz Et'));
 await renderer.act(async()=>t.unmount());
});


test('native initial clinical result follows web section order and question guidance',async()=>{
 const h=harness({getClinical:async()=>base}),t=await open(h);
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 const rendered=text(t.toJSON());
 const labels=['En Olası Durum','Önemli Bulgular','Tedavi Seçenekleri','Tedaviye Bağlı Dikkat Edilecekler','Önerilen Yaklaşım','Diğer Olası Tanılar','Hekime Sorular'];
 let previous=-1;
 for(const label of labels){const index=rendered.indexOf(label);assert.ok(index>previous,'missing or out-of-order web section: '+label);previous=index;}
 assert.ok(rendered.includes('Yalnız tedavi sırasını, uygulanabilirliği veya vaka-özel komplikasyon riskini değiştirebilecek eksik bilgiler sorulur.'));
 assert.equal(rendered.includes('Ön Klinik Değerlendirme'),false);
 const question=t.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Klinik cevap 1');
 assert.equal(question.props.placeholder,'Kısa klinik cevap yazın...');
 await renderer.act(async()=>t.unmount());
});

test('native final clinical result matches web order and hides preliminary-only fields',async()=>{
 const finalResult={status:'FINAL',most_likely:'Synthetic final likely condition',findings:['Synthetic final finding'],treatment_options:['Synthetic final treatment'],treatment_cautions:['Synthetic final caution'],preferred_approach:'Synthetic final approach',differential:['Synthetic final differential'],recommended_evaluation:['SHOULD NOT SHOW evaluation'],uncertainty:'SHOULD NOT SHOW uncertainty',preliminary_assessment:'SHOULD NOT SHOW preliminary',questions:[{question:'SHOULD NOT SHOW question',type:'TEXT'}]};
 const h=harness({getClinical:async()=>({...base,result:finalResult})}),t=await open(h);
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 const rendered=text(t.toJSON());
 const labels=['En Olası Durum','Önemli Bulgular','Tedavi Seçenekleri','Tedaviye Bağlı Dikkat Edilecekler','Önerilen Yaklaşım','Diğer Olası Tanılar'];
 let previous=-1;
 for(const label of labels){const index=rendered.indexOf(label);assert.ok(index>previous,'missing or out-of-order final section: '+label);previous=index;}
 assert.ok(rendered.includes('Nihai Klinik Değerlendirme'));
 for(const privateOnly of ['SHOULD NOT SHOW','Belirsizlik','Ön Değerlendirme','Önerilen Klinik Değerlendirmeler','Hekime Sorular'])assert.equal(rendered.includes(privateOnly),false);
 const finalBox=t.root.findAllByType('View').find(node=>node.props.style&&node.props.style.backgroundColor==='#F5F8FF');
 assert.ok(finalBox,'web final-box visual treatment should be present');
 assert.ok(rendered.includes('1.'));
 await renderer.act(async()=>t.unmount());
});
