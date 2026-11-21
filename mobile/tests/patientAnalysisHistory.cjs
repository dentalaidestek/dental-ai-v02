const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const renderer=require('react-test-renderer');

global.IS_REACT_ACT_ENVIRONMENT=true;

const presentationExports={};
const presentationSource=fs.readFileSync(require.resolve('../src/patientAnalysisPresentation.ts'),'utf8');
const presentationCode=ts.transpileModule(presentationSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(presentationCode,{exports:presentationExports});
const historyPresentationExports={};
const historyPresentationSource=fs.readFileSync(require.resolve('../src/patientHistoryPresentation.ts'),'utf8');
const historyPresentationCode=ts.transpileModule(historyPresentationSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(historyPresentationCode,{exports:historyPresentationExports,Date,Math,Number,String,Error,Promise,Array,Object});

function loadTypeScriptModule(relative){
 const source=fs.readFileSync(require.resolve(relative),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={};
 vm.runInNewContext(code,{exports,Date,Math,Number,String,Error,Promise,Array,Object});
 return exports;
}
const appResumeRefreshExports=loadTypeScriptModule('../src/appResumeRefresh.ts');
const patientHistoryImageExports={};
const patientHistoryImageSource=fs.readFileSync(require.resolve('../src/patientAnalysisHistoryImages.ts'),'utf8');
const patientHistoryImageCode=ts.transpileModule(patientHistoryImageSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(patientHistoryImageCode,{
 exports:patientHistoryImageExports,
 require:name=>name==='./api'?{API_BASE:'https://dentalai.tr/api/mobile/v1'}:(()=>{throw new Error('Unexpected image helper import '+name)})(),
 Date,Math,Number,String,Error,Promise,Array,Object
});

function loadHistory({assets,legacy=true,fetchPage,getAnalysis}={}){
 let lastEvent=null;
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePatientHistory.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={};
 const item={id:41,patient_id:8,patient_name:'SYNTHETIC',tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:'2026-11-17T10:00:00Z'};
 const native={
  AppState:{currentState:'active',addEventListener:()=>({remove(){}})},
  ActivityIndicator:'ActivityIndicator',Image:'Image',Modal:'Modal',Pressable:'Pressable',
  ScrollView:'ScrollView',Text:'Text',View:'View'
 };
 const modernApi={getPatientAnalysisHistoryPage:fetchPage||(async()=>({items:[item],total:1,next:null}))};
 const analysisApi={getAnalysis:getAnalysis||(async()=>({
  analysis:{id:41,patient_id:8,tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:item.created_at,is_voice_review:false,legacy_radiograph_available:legacy},
  patient:{id:8,anonymous_id:'SYN-8',age:0,chief_complaint:null},
  assets
 }))};
 vm.runInNewContext(code,{
  exports,
  require:name=>{
   if(name==='react')return {...React,default:React};
   if(name==='react-native')return native;
   if(name==='@react-navigation/native')return {useIsFocused:()=>true};
   if(name==='./modernApi')return modernApi;
   if(name==='./analysisApi')return analysisApi;
   if(name==='./realtime')return {useRealtime:()=>({lastEvent})};
   if(name==='./patientAnalysisPresentation')return presentationExports;
   if(name==='./appResumeRefresh')return appResumeRefreshExports;
   if(name==='./patientHistoryPresentation')return historyPresentationExports;
   if(name==='./patientAnalysisHistoryImages')return patientHistoryImageExports;
   throw new Error('Unexpected import '+name);
  },
  Date,Math,Number,String,Error,Promise,Array,Object
 });
 const Component=exports.default;
 Component.setEvent=value=>{lastEvent=value};
 return Component;
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('patient analysis assets are grouped exactly like the web profile',()=>{
 const groups=presentationExports.groupPatientAnalysisAssets([
  {id:1,image_type:'PHOTO'},{id:2,image_type:'OTHER'},{id:3,image_type:'RADIOGRAPH'}
 ]);
 assert.deepEqual(Array.from(groups.clinical,x=>x.id),[1,2]);
 assert.deepEqual(Array.from(groups.radiographs,x=>x.id),[3]);
 assert.equal(presentationExports.shouldShowLegacyPatientRadiograph(true,[{id:3,image_type:'RADIOGRAPH'}]),false);
 assert.equal(presentationExports.shouldShowLegacyPatientRadiograph(true,[{id:1,image_type:'PHOTO'}]),true);
 assert.equal(presentationExports.shouldShowLegacyPatientRadiograph(false,[]),false);
});

test('patient history loads legacy radiograph only through the authenticated protected route',async()=>{
 const History=loadHistory({assets:[{id:7,original_filename:'clinical.png',image_type:'PHOTO',has_vision:false}],legacy:true});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token',patientId:8,onOpenAnalysis:()=>{}}));await flush()});
 const row=tree.root.findAllByType('Pressable')[0];
 await renderer.act(async()=>{row.props.onPress();await flush()});
 const images=tree.root.findAllByType('Image');
 assert.equal(images.length,2,'one clinical asset plus one legacy radiograph should render');
 const legacy=images.find(node=>node.props.source.uri.endsWith('/legacy-radiograph'));
 assert.ok(legacy,'legacy radiograph endpoint must be used instead of a raw storage path');
 assert.equal(legacy.props.source.headers.Authorization,'Bearer synthetic-token');
 const content=JSON.stringify(tree.toJSON());
 assert.ok(content.includes('Yüklenen görüntüler'));
 assert.ok(content.includes('Radyografiler'));
 assert.ok(content.includes('Tedavi önerisi'));
 await renderer.act(async()=>tree.unmount());
});


test('native history cards expose the web detail action and stable status/date labels',async()=>{
 const History=loadHistory({assets:[],legacy:false});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token',patientId:8}));await flush()});
 const texts=tree.root.findAllByType('Text').map(node=>String(node.props.children));
 assert.ok(texts.includes('Analiz #41'));
 assert.ok(texts.includes('Detay'));
 assert.ok(texts.includes('Başarılı'));
 assert.ok(texts.some(value=>value.includes('20.11.2026')||value.includes('17.11.2026')));
 await renderer.act(async()=>tree.unmount());
});

test('existing RADIOGRAPH assets suppress the legacy fallback',async()=>{
 const History=loadHistory({assets:[{id:9,original_filename:'bitewing.png',image_type:'RADIOGRAPH',has_vision:false}],legacy:true});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token',patientId:8}));await flush()});
 const row=tree.root.findAllByType('Pressable')[0];
 await renderer.act(async()=>{row.props.onPress();await flush()});
 const images=tree.root.findAllByType('Image');
 assert.equal(images.length,1);
 assert.ok(images[0].props.source.uri.endsWith('/assets/9'));
 assert.ok(!images.some(node=>node.props.source.uri.includes('/legacy-radiograph')));
 await renderer.act(async()=>tree.unmount());
});


test('private patient-history images revalidate and remount without putting bearer tokens in image keys',async()=>{
 const History=loadHistory({assets:[{id:7,original_filename:'clinical.png',image_type:'PHOTO',has_vision:false}],legacy:true});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token-A',patientId:8}));await flush()});
 const row=tree.root.findAllByType('Pressable')[0];
 await renderer.act(async()=>{row.props.onPress();await flush()});
 const firstImages=tree.root.findAllByType('Image');
 assert.equal(firstImages.length,2);
 const firstKeys=firstImages.map(node=>node.props.testID);
 assert.ok(firstKeys.every(key=>typeof key==='string'&&key.startsWith('patient-analysis-history:')));
 assert.ok(firstKeys.every(key=>!key.includes('synthetic-token-A')));
 assert.ok(firstImages.every(node=>node.props.source.cache==='reload'));
 assert.ok(firstImages.every(node=>node.props.source.headers.Authorization==='Bearer synthetic-token-A'));
 await renderer.act(async()=>{tree.update(React.createElement(History,{token:'synthetic-token-B',patientId:8}));await flush()});
 const nextRow=tree.root.findAllByType('Pressable')[0];
 await renderer.act(async()=>{nextRow.props.onPress();await flush()});
 const secondImages=tree.root.findAllByType('Image');
 assert.equal(secondImages.length,2);
 assert.ok(secondImages.every(node=>node.props.source.headers.Authorization==='Bearer synthetic-token-B'));
 assert.notDeepEqual(secondImages.map(node=>node.props.testID),firstKeys,'account token change must remount every private history image');
 await renderer.act(async()=>tree.unmount());
});

test('private history image helper validates identity and returns only canonical authenticated no-cache routes',()=>{
 const {createPatientAnalysisHistoryImageScope,patientAnalysisHistoryImageKey,patientAnalysisHistoryImageSource}=patientHistoryImageExports;
 const scope=createPatientAnalysisHistoryImageScope();
 assert.match(scope,/^patient-analysis-history-scope-[1-9]\d*$/);
 const key=patientAnalysisHistoryImageKey(scope,41,7);
 assert.ok(!key.includes('synthetic-token'));
 assert.notEqual(key,patientAnalysisHistoryImageKey(createPatientAnalysisHistoryImageScope(),41,7));
 assert.notEqual(key,patientAnalysisHistoryImageKey(scope,41,null));
 assert.notEqual(key,patientAnalysisHistoryImageKey(scope,41,7,1),'image-only retry must remount without changing the analysis request');
 assert.throws(()=>patientAnalysisHistoryImageKey(scope,41,7,-1),/kapsamı/);
 const asset=patientAnalysisHistoryImageSource('synthetic-token',41,7);
 assert.equal(asset.uri,'https://dentalai.tr/api/mobile/v1/analyses/41/assets/7');
 assert.equal(asset.headers.Authorization,'Bearer synthetic-token');
 assert.equal(asset.cache,'reload');
 const legacy=patientAnalysisHistoryImageSource('synthetic-token',41,null);
 assert.equal(legacy.uri,'https://dentalai.tr/api/mobile/v1/analyses/41/legacy-radiograph');
 assert.equal(legacy.cache,'reload');
 assert.throws(()=>patientAnalysisHistoryImageSource('bad token',41,7),/oturumu/);
 assert.throws(()=>patientAnalysisHistoryImageSource('synthetic-token',0,7),/kimliği/);
 assert.throws(()=>patientAnalysisHistoryImageKey('synthetic-token',41,7),/kapsamı/);
});



test('history image retry remounts private assets without repeating the analysis detail request',async()=>{
 let detailCalls=0;
 const History=loadHistory({
  assets:[{id:7,original_filename:'clinical.png',image_type:'PHOTO',has_vision:false}],
  legacy:false,
  getAnalysis:async()=>{
   detailCalls++;
   return {
    analysis:{id:41,patient_id:8,tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:'2026-11-17T10:00:00Z',is_voice_review:false,legacy_radiograph_available:false},
    patient:{id:8,anonymous_id:'SYN-8',age:0,chief_complaint:null},
    assets:[{id:7,original_filename:'clinical.png',image_type:'PHOTO',has_vision:false}]
   };
  }
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token',patientId:8}));await flush()});
 const row=tree.root.findAllByType('Pressable')[0];
 await renderer.act(async()=>{row.props.onPress();await flush()});
 const before=tree.root.findByType('Image').props.testID;
 await renderer.act(async()=>tree.root.findByType('Image').props.onError());
 assert.ok(tree.root.findAllByType('Text').some(node=>node.props.children==='Görselleri yeniden yükle'));
 const retry=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>child.props.children==='Görselleri yeniden yükle'));
 assert.ok(retry);
 await renderer.act(async()=>{retry.props.onPress();await flush()});
 const after=tree.root.findByType('Image');
 assert.notEqual(after.props.testID,before);
 assert.equal(after.props.source.cache,'reload');
 assert.equal(detailCalls,1,'image retry must not fetch analysis detail or repeat inference');
 await renderer.act(async()=>tree.unmount());
});

test('legacy radiograph image retry restores only the private image component',async()=>{
 let detailCalls=0;
 const History=loadHistory({
  assets:[],legacy:true,
  getAnalysis:async()=>{
   detailCalls++;
   return {
    analysis:{id:41,patient_id:8,tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:'2026-11-17T10:00:00Z',is_voice_review:false,legacy_radiograph_available:true},
    patient:{id:8,anonymous_id:'SYN-8',age:0,chief_complaint:null},assets:[]
   };
  }
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token',patientId:8}));await flush()});
 const row=tree.root.findAllByType('Pressable')[0];
 await renderer.act(async()=>{row.props.onPress();await flush()});
 const image=tree.root.findByType('Image'),before=image.props.testID;
 await renderer.act(async()=>image.props.onError());
 assert.ok(tree.root.findAllByType('Text').some(node=>String(node.props.children).includes('Radyografik görüntü alınamadı')));
 const retry=tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>child.props.children==='Görselleri yeniden yükle'));
 assert.ok(retry);
 await renderer.act(async()=>{retry.props.onPress();await flush()});
 const next=tree.root.findByType('Image');
 assert.notEqual(next.props.testID,before);
 assert.ok(next.props.source.uri.endsWith('/legacy-radiograph'));
 assert.equal(detailCalls,1);
 await renderer.act(async()=>tree.unmount());
});

test('an in-flight patient-history read coalesces a realtime refresh and does not double-fetch on initial focus',async()=>{
 let resolveFirst,calls=0;
 const History=loadHistory({
  assets:[],legacy:false,
  fetchPage:async()=>{
   calls++;
   if(calls===1)return new Promise(resolve=>{resolveFirst=resolve});
   return {items:[{id:41,patient_id:8,patient_name:'SYNTHETIC',tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:'2026-11-17T10:00:00Z'}],total:1,next:null};
  }
 });
 const props={token:'synthetic-token',patientId:8};
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,props));await flush()});
 assert.equal(calls,1,'scope initialization and initial focus must share one read');
 History.setEvent({event_type:'ANALYSIS_CREATED',payload:{patient_id:8}});
 await renderer.act(async()=>{tree.update(React.createElement(History,props));await flush()});
 assert.equal(calls,1,'realtime refresh must wait for the current request rather than overlap it');
 await renderer.act(async()=>{resolveFirst({items:[],total:0,next:null});await flush();await flush()});
 assert.equal(calls,2,'one queued first-page refresh must run after the in-flight request settles');
 History.setEvent({event_type:'ANALYSIS_UPDATED',payload:{patient_id:9}});
 await renderer.act(async()=>{tree.update(React.createElement(History,props));await flush()});
 assert.equal(calls,2,'another patient event must not refresh this history');
 await renderer.act(async()=>tree.unmount());
});

test('native analysis status matches the web profile status labels',()=>{
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePatientHistory.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?{AppState:{addEventListener:()=>({remove(){}})},ActivityIndicator:'ActivityIndicator',Image:'Image',Modal:'Modal',Pressable:'Pressable',ScrollView:'ScrollView',Text:'Text',View:'View'}:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./modernApi'?{}:name==='./analysisApi'?{}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='./patientAnalysisPresentation'?presentationExports:name==='./patientHistoryPresentation'?historyPresentationExports:{}});
 assert.equal(exports.analysisStatus({status:'AI_ANALYZED'}),'Başarılı');
 assert.equal(exports.analysisStatus({status:'AI_FINAL'}),'Yarım kaldı');
 assert.equal(exports.analysisStatus({status:'FAILED'}),'Başarısız');
 assert.equal(exports.analysisStatus({status:'DONE',is_voice_review:true}),'Kaydedildi');
});
