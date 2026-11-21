const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const renderer=require('react-test-renderer');

global.IS_REACT_ACT_ENVIRONMENT=true;
const root=require('node:path').resolve(__dirname,'..');
const compile=(relative)=>ts.transpileModule(fs.readFileSync(require('node:path').join(root,relative),'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}
}).outputText;
const presentation={};
vm.runInNewContext(compile('src/patientAnalysisPresentation.ts'),{exports:presentation});
const historyPresentation={};
vm.runInNewContext(compile('src/patientHistoryPresentation.ts'),{exports:historyPresentation,Date,Math,Number,String,Error,Promise,Array,Object});

const appResumeRefresh={};
vm.runInNewContext(compile('src/appResumeRefresh.ts'),{exports:appResumeRefresh,Date,Math,Number,String,Error,Promise,Array,Object});
const historyImages={};
vm.runInNewContext(compile('src/patientAnalysisHistoryImages.ts'),{
 exports:historyImages,
 require:name=>name==='./api'?{API_BASE:'https://dentalai.tr/api/mobile/v1'}:(()=>{throw new Error('Unexpected history-image import '+name)})(),
 Date,Math,Number,String,Error,Promise,Array,Object
});

function loadHistory(getPatientAnalysisHistoryPage){
 const exports={};
 const native={AppState:{currentState:'active',addEventListener:()=>({remove(){}})},ActivityIndicator:'ActivityIndicator',Image:'Image',Modal:'Modal',Pressable:'Pressable',ScrollView:'ScrollView',Text:'Text',View:'View'};
 const item=(id)=>({id,patient_id:8,patient_name:'Synthetic',tooth_number:'36',status:'FINAL',clinical_notes:'Synthetic',created_at:'2026-11-17T10:00:00Z'});
 vm.runInNewContext(compile('src/NativePatientHistory.tsx'),{
  exports,
  require:name=>{
   if(name==='react')return {...React,default:React};
   if(name==='react-native')return native;
   if(name==='@react-navigation/native')return {useIsFocused:()=>true};
   if(name==='./modernApi')return {getPatientAnalysisHistoryPage};
   if(name==='./analysisApi')return {getAnalysis:async(_token,id)=>({analysis:{id,patient_id:8,status:'FINAL',created_at:'2026-11-17T10:00:00Z'},patient:{id:8,anonymous_id:'SYN-8'},assets:[]})};
   if(name==='./realtime')return {useRealtime:()=>({lastEvent:null})};
   if(name==='./patientAnalysisPresentation')return presentation;
   if(name==='./patientHistoryPresentation')return historyPresentation;
   if(name==='./appResumeRefresh')return appResumeRefresh;
   if(name==='./patientAnalysisHistoryImages')return historyImages;
   throw new Error('Unexpected import '+name);
  },
  Date,Math,Number,String,Error,Promise,Array,Object,Set
 });
 return {History:exports.default,item};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function pressableWithText(tree,label){
 return tree.root.findAllByType('Pressable').find(node=>
  node.findAllByType('Text').some(child=>String(child.props.children)===label)
 );
}

test('failed next-page request retries the same cursor without resetting loaded history',async()=>{
 const calls=[];
 let nextPageAttempts=0;
 const cursor={kind:'stable',value:'YXNkZmdoaWprbG1ub3BxcnN0dXZ3eHl6'};
 const {History,item}=loadHistory(async(_token,patientId,_toothNumber,before)=>{
  calls.push({cursor:before?.value??null,patientId});
  if(before?.value===cursor.value&&nextPageAttempts++===0)throw Error('Synthetic network interruption');
  if(before?.value===cursor.value)return {items:[item(40)],total:2,next:null};
  return {items:[item(41)],total:2,next:cursor};
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(History,{token:'synthetic-token',patientId:8}));await flush()});
 assert.ok(pressableWithText(tree,'Diğer analizleri göster'));
 await renderer.act(async()=>{
  pressableWithText(tree,'Diğer analizleri göster').props.onPress();
  await flush();
 });
 assert.ok(tree.root.findAllByType('Text').some(node=>String(node.props.children).includes('Synthetic network interruption')));
 const retry=pressableWithText(tree,'Yeniden dene');
 assert.ok(retry,'failed continuation must expose a retry action');
 await renderer.act(async()=>{retry.props.onPress();await flush()});
 assert.deepEqual(calls,[{cursor:null,patientId:8},{cursor:'YXNkZmdoaWprbG1ub3BxcnN0dXZ3eHl6',patientId:8},{cursor:'YXNkZmdoaWprbG1ub3BxcnN0dXZ3eHl6',patientId:8}]);
 const labels=tree.root.findAllByType('Text').map(node=>String(node.props.children));
 assert.ok(labels.includes('Analiz #41'),'first page must remain visible');
 assert.ok(labels.includes('Analiz #40'),'retry must append the next page');
 assert.ok(!pressableWithText(tree,'Yeniden dene'));
 await renderer.act(async()=>tree.unmount());
});

test('history presentation fails closed for invalid timestamps and hides tooth on voice reviews',()=>{
 assert.equal(historyPresentation.patientAnalysisHistoryDate('not-a-date'),'Tarih bilgisi yok');
 assert.equal(historyPresentation.patientAnalysisHistoryDate(null),'Tarih bilgisi yok');
 assert.equal(historyPresentation.patientAnalysisHistoryTooth({tooth_number:'36',is_voice_review:true}),null);
 assert.equal(historyPresentation.patientAnalysisHistoryTooth({tooth_number:'36',is_voice_review:false}),'Diş 36');
 assert.equal(historyPresentation.patientAnalysisHistoryStatusTone({status:'FAILED'}),'danger');
 assert.equal(historyPresentation.patientAnalysisHistoryStatusTone({status:'AI_ANALYZED'}),'success');
});
