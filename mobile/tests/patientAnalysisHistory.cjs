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

function loadHistory({assets,legacy=true}){
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePatientHistory.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={};
 const item={id:41,patient_id:8,patient_name:'SYNTHETIC',tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:'2026-11-17T10:00:00Z'};
 const native={
  AppState:{addEventListener:()=>({remove(){}})},
  ActivityIndicator:'ActivityIndicator',Image:'Image',Modal:'Modal',Pressable:'Pressable',
  ScrollView:'ScrollView',Text:'Text',View:'View'
 };
 const modernApi={getAnalysisHistory:async()=>({items:[item],next_before:null})};
 const analysisApi={getAnalysis:async()=>({
  analysis:{id:41,patient_id:8,tooth_number:'11',clinical_notes:'Synthetic note',status:'FINAL',created_at:item.created_at,is_voice_review:false,legacy_radiograph_available:legacy},
  patient:{id:8,anonymous_id:'SYN-8',age:0,chief_complaint:null},
  assets
 })};
 vm.runInNewContext(code,{
  exports,
  require:name=>{
   if(name==='react')return {...React,default:React};
   if(name==='react-native')return native;
   if(name==='@react-navigation/native')return {useIsFocused:()=>true};
   if(name==='./modernApi')return modernApi;
   if(name==='./analysisApi')return analysisApi;
   if(name==='./realtime')return {useRealtime:()=>({lastEvent:null})};
   if(name==='./patientAnalysisPresentation')return presentationExports;
   if(name==='./patientHistoryPresentation')return historyPresentationExports;
   throw new Error('Unexpected import '+name);
  },
  Date,Math,Number,String,Error,Promise,Array,Object
 });
 return exports.default;
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

test('native analysis status matches the web profile status labels',()=>{
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePatientHistory.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?{AppState:{addEventListener:()=>({remove(){}})},ActivityIndicator:'ActivityIndicator',Image:'Image',Modal:'Modal',Pressable:'Pressable',ScrollView:'ScrollView',Text:'Text',View:'View'}:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./modernApi'?{}:name==='./analysisApi'?{}:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='./patientAnalysisPresentation'?presentationExports:name==='./patientHistoryPresentation'?historyPresentationExports:{}});
 assert.equal(exports.analysisStatus({status:'AI_ANALYZED'}),'Başarılı');
 assert.equal(exports.analysisStatus({status:'AI_FINAL'}),'Yarım kaldı');
 assert.equal(exports.analysisStatus({status:'FAILED'}),'Başarısız');
 assert.equal(exports.analysisStatus({status:'DONE',is_voice_review:true}),'Kaydedildi');
});
