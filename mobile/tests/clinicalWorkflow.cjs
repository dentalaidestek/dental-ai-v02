const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const compile=f=>ts.transpileModule(fs.readFileSync(require.resolve(f),'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
const revision='a'.repeat(64),base={analysis_id:1,patient_id:8,patient_anonymous_id:'SYNTHETIC-008',status:'AI_ANALYZED',revision,result:{status:'INITIAL',most_likely:'Synthetic likely condition',findings:['Synthetic string finding'],treatment_options:['Synthetic treatment'],treatment_cautions:['Synthetic caution'],recommended_evaluation:['Synthetic clinical exam'],uncertainty:'Synthetic uncertainty',questions:[{question:'Synthetic question?',type:'TEXT'}]},assets:[],clinical_notes:null,tooth_number:null,job:null};
function api(request=async()=>({})){const exports={};vm.runInNewContext(compile('../src/clinicalApi.ts'),{exports,Error,require:()=>({request})});return exports}
function harness(overrides={},saved){const exports={},storage=new Map(),calls=[],a=api();if(saved)storage.set('dai.clinical.final.1.1',JSON.stringify(saved));const secure={getItemAsync:async k=>storage.get(k)||null,setItemAsync:async(k,v)=>storage.set(k,v),deleteItemAsync:async k=>storage.delete(k)},native={StyleSheet:{create:x=>x},AppState:{currentState:'active',addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Image','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const endpoint={...a,getClinical:async()=>base,submitClinical:async(_t,intent)=>{calls.push(intent);return{ok:true,job:{id:7,kind:'FINAL',status:'QUEUED'}}},saveClinicalNote:async()=>({ok:true}),...overrides};
 const finding={};vm.runInNewContext(compile('../src/findings.ts'),{exports:finding});
 vm.runInNewContext(compile('../src/NativeClinicalReview.tsx'),{exports,setTimeout,clearTimeout,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{useIsFocused:()=>true}:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=> 'synthetic-key'}:n==='./socialDraft'?{chunkedDraftStore:()=>secure}:n==='./clinicalApi'?endpoint:n==='./findings'?finding:{default:props=>React.createElement('Text',null,props.value)}});return{Component:exports.default,calls,storage,endpoint};}
async function open(h){let t;await renderer.act(async()=>t=renderer.create(React.createElement(h.Component,{token:'A',userId:1,analysisId:1})));return t}
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
 const asset={id:4,name:'synthetic.png',image_type:'BITEWING',has_vision:true,url:'/api/mobile/v1/analyses/1/assets/4'};
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
 assert.deepEqual(a.parseClinicalNoteIntent(raw,1,1),{user:1,analysis:1,note:'Synthetic',finding:'',tooth:'36'});
 assert.throws(()=>a.parseClinicalNoteIntent(raw,2,1),/doğrulanamadı/);
 assert.throws(()=>a.parseClinicalNoteIntent(JSON.stringify({user:1,analysis:1,note:'',finding:'',tooth:'59'}),1,1),/doğrulanamadı/);
 assert.equal(a.clinicalNoteLine({user:1,analysis:1,note:'Extra',finding:'Manual',tooth:'36'}),'[Diş 36] Manuel bulgu: Manual — Extra');
});
