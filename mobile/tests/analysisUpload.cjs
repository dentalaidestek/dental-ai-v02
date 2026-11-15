const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const compile=f=>ts.transpileModule(fs.readFileSync(require.resolve(f),'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join(''),button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
const image={uri:'file:///cache/dai-analysis-synthetic.png',name:'synthetic.png',type:'image/png'},intent={userId:1,patientId:8,requestKey:'synthetic-upload-key-001',toothNumber:'36',clinicalNotes:'Synthetic clinical note',images:[image]},receipt={analysis_id:41,patient_id:8,job_id:5,status:'VISION_PENDING'};
function ui(overrides={},raw=null){const exports={},storage=new Map(),calls=[],model=require('../src/analysisUpload.ts');if(raw)storage.set('dai.analysis.upload.1.8',raw);const secure={getItemAsync:async k=>storage.get(k)||null,setItemAsync:async(k,v)=>storage.set(k,v),deleteItemAsync:async k=>storage.delete(k)},native={StyleSheet:{create:x=>x},...Object.fromEntries(['ActivityIndicator','Image','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))},api={...model,analysisUploadReceipt:async()=>null,uploadAnalysis:async(_t,v,progress)=>{calls.push(v);progress(100);return receipt},...overrides};
 vm.runInNewContext(compile('../src/NativeAnalysisUpload.tsx'),{exports,Error,AbortController,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=> '00000000-0000-4000-8000-000000000001'}:n==='./socialDraft'?{chunkedDraftStore:()=>secure}:n==='./analysisUpload'?api:n==='./nativeAnalysisFiles'?{cacheAnalysisImages:async items=>items.map((_,i)=>({...image,uri:image.uri+i,name:'synthetic-'+i+'.png'})),clearAnalysisImages:async()=>{},validateCachedAnalysisImages:async()=>{}}:n==='expo-image-picker'?{requestMediaLibraryPermissionsAsync:async()=>({granted:true}),launchImageLibraryAsync:async()=>({canceled:false,assets:[{uri:image.uri,fileName:image.name,mimeType:image.type},{uri:image.uri+'2',fileName:'second.png',mimeType:image.type}]})}:{} });return{Component:exports.default,calls,storage,api};}
async function mount(h,onCreated=async()=>{},existingMediaIds=[],onExistingMediaIdsLoaded){let t;await renderer.act(async()=>t=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,onCreated,existingMediaIds,onExistingMediaIdsLoaded})));return t}
test('native analysis composer sends multiple images, FDI and clinical notes with one stable key',async()=>{const h=ui(),opened=[],t=await mount(h,async id=>opened.push(id));await renderer.act(async()=>button(t,'Galeriden Ekle').props.onPress());await renderer.act(async()=>{t.root.findByProps({accessibilityLabel:'Analiz FDI diş numaraları'}).props.onChangeText('36,46');t.root.findByProps({accessibilityLabel:'Analiz klinik bilgileri'}).props.onChangeText('Synthetic history')});await renderer.act(async()=>{const b=button(t,'Analizi Başlat');b.props.onPress();b.props.onPress();await new Promise(r=>setImmediate(r))});assert.equal(h.calls.length,1);assert.equal(h.calls[0].images.length,2);assert.equal(h.calls[0].toothNumber,'36,46');assert.equal(h.calls[0].clinicalNotes,'Synthetic history');assert.deepEqual(opened,[41]);assert.equal(h.storage.size,0);await renderer.act(async()=>t.unmount())});
test('saved uncertain upload checks server receipt before sending any bytes on reopen',async()=>{const h=ui({analysisUploadReceipt:async()=>receipt},JSON.stringify(intent)),opened=[],t=await mount(h,async id=>opened.push(id));assert.equal(h.calls.length,0);assert.deepEqual(opened,[41]);assert.equal(h.storage.size,0);await renderer.act(async()=>t.unmount())});
test('explicit retry keeps the same stored upload intent after a lost response',async()=>{const sent=[],h=ui({uploadAnalysis:async(_t,v)=>{sent.push(v);throw Error('Synthetic connection loss')}},JSON.stringify(intent)),t=await mount(h);await renderer.act(async()=>button(t,'Aynı Yüklemeyi Sürdür').props.onPress());assert.equal(sent.length,1);assert.equal(sent[0].requestKey,intent.requestKey);assert.equal(sent[0].clinicalNotes,intent.clinicalNotes);assert.ok(h.storage.has('dai.analysis.upload.1.8'));assert.equal(button(t,'Galeriden Ekle').props.disabled,true);await renderer.act(async()=>t.unmount())});
test('corrupt saved intent blocks a new upload instead of silently discarding it',async()=>{const h=ui({},'not-json'),t=await mount(h);assert.equal(button(t,'Galeriden Ekle').props.disabled,true);assert.equal(button(t,'Analizi Başlat').props.disabled,true);assert.equal(h.calls.length,0);await renderer.act(async()=>t.unmount())});
test('receipt survives a failed result read with an explicit existing-analysis open action',async()=>{const h=ui({analysisUploadReceipt:async()=>receipt},JSON.stringify(intent)),t=await mount(h,async()=>{throw Error('Synthetic result read failed')});assert.ok(button(t,'Analiz #41 Kaydını Aç'));assert.ok(text(t.toJSON()).includes('Synthetic result read failed'));assert.equal(h.calls.length,0);await renderer.act(async()=>t.unmount())});
test('analysis upload intent rejects another patient and invalid primary FDI',()=>{const api=require('../src/analysisUpload.ts');assert.throws(()=>api.parseUploadIntent(JSON.stringify(intent),1,9));assert.throws(()=>api.validateUploadFields('59','Synthetic'));assert.throws(()=>api.validateUploadFields('36,36','Synthetic'));assert.doesNotThrow(()=>api.validateUploadFields('36,55','Synthetic'))});
test('native XHR uploads actual multipart files, reports bytes and aborts without losing intent',async()=>{const exports={},parts=[],calls=[];let xhr,timer;class Form{append(k,v){parts.push([k,v])}}class XHR{constructor(){xhr=this;this.upload={}}open(...v){calls.push(v)}setRequestHeader(k,v){calls.push([k,v])}send(){this.upload.onprogress({lengthComputable:true,loaded:20,total:40});this.status=200;this.responseText=JSON.stringify(receipt);this.onload()}abort(){this.onabort?.()}}const {ApiError}=require('../src/api.ts');vm.runInNewContext(compile('../src/analysisUpload.ts'),{exports,Error,FormData:Form,XMLHttpRequest:XHR,setTimeout:fn=>{timer=fn;return 1},clearTimeout(){},require:n=>n==='./api'?{ApiError}:n==='./analysisApi'?require('../src/analysisApi.ts'):{revalidateSession:async()=>{}}});const progress=[],r=await exports.uploadAnalysis('token',intent,p=>progress.push(p));assert.equal(r.analysis_id,41);assert.equal(progress[0],50);assert.equal(parts.filter(p=>p[0]==='images').length,1);assert.equal(parts.find(p=>p[0]==='request_key')[1],intent.requestKey);assert.equal(xhr.withCredentials,false);assert.ok(calls.some(p=>p[0]==='Cookie'&&p[1]===''));XHR.prototype.send=function(){};const pending=exports.uploadAnalysis('token',intent,()=>{});timer();await assert.rejects(pending,/sonucu belirsiz/)});
test('leaving during the read-only receipt lookup never starts a later upload',async()=>{let release;const pending=new Promise(r=>release=r),h=ui({analysisUploadReceipt:async()=>pending}),t=await mount(h);await renderer.act(async()=>button(t,'Galeriden Ekle').props.onPress());await renderer.act(async()=>{button(t,'Analizi Başlat').props.onPress();await new Promise(r=>setImmediate(r))});await renderer.act(async()=>t.unmount());release(null);await new Promise(r=>setImmediate(r));assert.equal(h.calls.length,0);assert.ok(h.storage.has('dai.analysis.upload.1.8'))});
test('clinical cache cleanup never deletes the original selected file',async()=>{const exports={},deleted=[];const fsapi={cacheDirectory:'file:///cache/',getInfoAsync:async()=>({exists:true,size:1024}),copyAsync:async()=>{},deleteAsync:async uri=>deleted.push(uri)};vm.runInNewContext(compile('../src/nativeAnalysisFiles.ts'),{exports,Error,require:n=>n==='expo-file-system/legacy'?fsapi:n==='expo-crypto'?{randomUUID:()=> 'synthetic-cache-key'}:require('../src/analysisApi.ts')});const cached=await exports.cacheAnalysisImages([image]);assert.ok(cached[0].uri.startsWith('file:///cache/dai-analysis-'));await exports.clearAnalysisImages([{...image,uri:'file:///photos/original.png'},...cached]);assert.equal(deleted.length,1);assert.equal(deleted[0],cached[0].uri)});
test('persisted clinical upload cannot fetch an external URI as a local attachment',()=>{const api=require('../src/analysisUpload.ts');for(const uri of ['https://external.invalid/private.png','file:///cache/../private.png'])assert.throws(()=>api.parseUploadIntent(JSON.stringify({...intent,images:[{...image,uri}]}),1,8),/yerel uygulama/)});

test('mixed analysis intent accepts saved media plus new files and keeps old new-only drafts compatible',()=>{
 const api=require('../src/analysisUpload.ts');
 const mixed={...intent,existingMediaIds:[31,32]};
 assert.deepEqual(Array.from(api.parseUploadIntent(JSON.stringify(mixed),1,8).existingMediaIds),[31,32]);
 assert.deepEqual(Array.from(api.parseUploadIntent(JSON.stringify(intent),1,8).existingMediaIds),[]);
 for(const ids of [[31,31],[0],['31'],[31,32,33,34,35]])assert.throws(()=>api.parseUploadIntent(JSON.stringify({...mixed,existingMediaIds:ids}),1,8));
 assert.throws(()=>api.parseUploadIntent(JSON.stringify({...mixed,existingMediaIds:[31,32,33],images:[image,image]}),1,8),/toplamı 1 ile 4/);
 assert.doesNotThrow(()=>api.parseUploadIntent(JSON.stringify({...mixed,existingMediaIds:[31],images:[]}),1,8));
});
test('native composer can analyze saved gallery media without requiring a new file',async()=>{
 const h=ui(),opened=[],t=await mount(h,async id=>opened.push(id),[31,32]);
 const send=button(t,'Analizi Başlat');assert.ok(send&&!send.props.disabled);
 await renderer.act(async()=>{send.props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(h.calls.length,1);assert.deepEqual(Array.from(h.calls[0].existingMediaIds),[31,32]);assert.equal(h.calls[0].images.length,0);assert.deepEqual(opened,[41]);
 await renderer.act(async()=>t.unmount());
});
test('mixed composer limits new picker slots by already selected saved media',async()=>{
 const h=ui(),t=await mount(h,async()=>{},[31,32]);
 await renderer.act(async()=>button(t,'Galeriden Ekle').props.onPress());
 assert.equal(h.calls.length,0);
 assert.ok(text(t.toJSON()).includes('2 kayıtlı klinik görüntü seçildi'));
 await renderer.act(async()=>{button(t,'Analizi Başlat').props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].existingMediaIds.length,2);assert.equal(h.calls[0].images.length,2);
 await renderer.act(async()=>t.unmount());
});
test('native multipart upload sends saved media IDs in the same request as new image bytes',async()=>{
 const exports={},parts=[];let xhr;
 class Form{append(key,value){parts.push([key,value])}}
 class XHR{constructor(){xhr=this;this.upload={}}open(){}setRequestHeader(){}send(){this.status=200;this.responseText=JSON.stringify(receipt);this.onload()}abort(){this.onabort?.()}}
 const {ApiError}=require('../src/api.ts');
 vm.runInNewContext(compile('../src/analysisUpload.ts'),{exports,Error,FormData:Form,XMLHttpRequest:XHR,setTimeout:()=>1,clearTimeout(){},require:n=>n==='./api'?{ApiError}:n==='./analysisApi'?require('../src/analysisApi.ts'):{revalidateSession:async()=>{}}});
 await exports.uploadAnalysis('token',{...intent,existingMediaIds:[31,32]},()=>{});
 assert.equal(parts.find(x=>x[0]==='existing_media_ids')[1],'31,32');
 assert.equal(parts.filter(x=>x[0]==='images').length,1);
 assert.equal(xhr.withCredentials,false);
});

test('recovered upload draft reports its original saved-media IDs to the gallery preview',async()=>{
 const saved={...intent,existingMediaIds:[31,32]},h=ui({},JSON.stringify(saved)),loaded=[];
 const t=await mount(h,async()=>{},[99],ids=>loaded.push(Array.from(ids)));
 assert.deepEqual(loaded,[[31,32]]);
 assert.ok(text(t.toJSON()).includes('2 kayıtlı klinik görüntü seçildi'));
 await renderer.act(async()=>t.unmount());
});
test('definitive missing saved-media response releases the stale local intent',async()=>{
 const h=ui({uploadAnalysis:async()=>{throw Object.assign(new Error('saved media missing'),{status:404})}},null),t=await mount(h,async()=>{},[31]);
 await renderer.act(async()=>{button(t,'Analizi Başlat').props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(h.storage.size,0);
 assert.ok(text(t.toJSON()).includes('saved media missing'));
 await renderer.act(async()=>t.unmount());
});
