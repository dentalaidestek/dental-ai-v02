const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;

function compile(file){return ts.transpileModule(fs.readFileSync(require.resolve(file),'utf8'),{fileName:file,reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}})}
function loadHelper(){
 const file='../src/academicAnswerActions.ts',result=compile(file),errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
 assert.deepEqual(errors,[],file);
 const exports={};vm.compileFunction(result.outputText,['exports'])(exports);return exports;
}
function loadAcademicApi(request){
 const file='../src/academicApi.ts',result=compile(file),errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
 assert.deepEqual(errors,[],file);
 const exports={};vm.compileFunction(result.outputText,['exports','require'])(exports,name=>name==='./api'?{request}:{});return exports;
}
function loadComponent(feedback,share){
 const file='../src/NativeAcademicAnswerActions.tsx',result=compile(file),errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
 assert.deepEqual(errors,[],file);
 const exports={},helper=loadHelper();
 const native={Pressable:'Pressable',Share:{share},Text:'Text',View:'View'};
 vm.compileFunction(result.outputText,['exports','require'])(exports,name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='./academicApi'?{feedback}:name==='./academicAnswerActions'?helper:{});
 return exports.default;
}
const nodeText=node=>typeof node==='string'?node:!node?'':(node.children||[]).map(nodeText).join('');
const press=(tree,label)=>tree.root.findAllByType('Pressable').find(item=>item.props.accessibilityLabel===label);
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('Academic vote helpers normalize legacy values and toggle the selected reaction',()=>{
 const h=loadHelper();
 assert.equal(h.normalizeAcademicVote('like'),'like');
 assert.equal(h.normalizeAcademicVote('dislike'),'dislike');
 assert.equal(h.normalizeAcademicVote('unexpected'),'none');
 assert.equal(h.toggleAcademicVote('none','like'),'like');
 assert.equal(h.toggleAcademicVote('like','like'),'none');
 assert.equal(h.toggleAcademicVote('dislike','like'),'like');
});

test('Academic answer sharing uses the answer or a readable quiz fallback',()=>{
 const h=loadHelper();
 assert.equal(h.academicAnswerShareText({content:'  Grounded answer  ',quiz:null}),'Grounded answer');
 assert.equal(h.academicAnswerShareText({content:'',quiz:{questions:[{number:1,stem:'Question',options:['one','two']}]}}),'1. Question\nA) one\nB) two');
 assert.equal(h.academicAnswerShareText({content:'',quiz:null}),'');
});

test('native Academic reaction saves only the selected vote and updates the local message',async()=>{
 const calls=[],updates=[];
 const Component=loadComponent(async(...args)=>{calls.push(args);return{ok:true,vote:args[3]}},async()=>({action:'dismissed'}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'private-token',course:3,messageId:12,content:'Grounded answer',vote:'none',onVote:v=>updates.push(v)}))});
 await renderer.act(async()=>{press(tree,'Beğen').props.onPress();await flush()});
 assert.deepEqual(calls,[['private-token',3,12,'like']]);
 assert.deepEqual(updates,['like']);
 assert.ok(tree.root.findAllByType('Text').some(item=>nodeText(item)==='✓ Beğendin'));
 await renderer.act(async()=>tree.unmount());
});

test('native Academic reaction toggles off and switches without reloading workspace data',async()=>{
 const calls=[],updates=[];
 const Component=loadComponent(async(...args)=>{calls.push(args[3]);return{ok:true,vote:args[3]}},async()=>({}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'token',course:3,messageId:12,content:'Answer',vote:'like',onVote:v=>updates.push(v)}))});
 await renderer.act(async()=>{press(tree,'Beğen').props.onPress();await flush()});
 await renderer.act(async()=>{press(tree,'Beğenme').props.onPress();await flush()});
 assert.deepEqual(calls,['none','dislike']);
 assert.deepEqual(updates,['none','dislike']);
 await renderer.act(async()=>tree.unmount());
});

test('failed Academic reaction rolls back the optimistic state',async()=>{
 const Component=loadComponent(async()=>{throw Error('offline')},async()=>({}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'token',course:3,messageId:12,content:'Answer',vote:'like',onVote:()=>{}}))});
 await renderer.act(async()=>{press(tree,'Beğenme').props.onPress();await flush()});
 const labels=tree.root.findAllByType('Text').map(nodeText);
 assert.ok(labels.includes('✓ Beğendin'));
 assert.ok(labels.includes('Kaydedilemedi. Tekrar dene.'));
 await renderer.act(async()=>tree.unmount());
});

test('native Academic share opens the system share sheet with the visible answer',async()=>{
 const shared=[],Component=loadComponent(async()=>({ok:true,vote:'none'}),async value=>{shared.push(value);return{action:'sharedAction'}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'token',course:3,messageId:12,content:'Share this answer',vote:'none',onVote:()=>{}}))});
 await renderer.act(async()=>{press(tree,'Yanıtı paylaş').props.onPress();await flush()});
 assert.equal(shared.length,1);
 assert.equal(shared[0].message,'Share this answer');
 assert.equal(shared[0].title,'Dental AI Akademik');
 await renderer.act(async()=>tree.unmount());
});

test('disabled Academic answer actions cannot send feedback or open sharing',async()=>{
 let calls=0,shares=0;
 const Component=loadComponent(async()=>{calls++;return{ok:true,vote:'like'}},async()=>{shares++;return{}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'token',course:3,messageId:12,content:'Answer',vote:'none',disabled:true,onVote:()=>{}}))});
 assert.equal(press(tree,'Beğen').props.disabled,true);
 assert.equal(press(tree,'Yanıtı paylaş').props.disabled,true);
 await renderer.act(async()=>tree.unmount());
 assert.equal(calls,0);assert.equal(shares,0);
});

test('Academic feedback API checks the private route and rejects malformed acknowledgements',async()=>{
 const calls=[],a=loadAcademicApi(async(...args)=>{calls.push(args);return{ok:true,vote:'like'}});
 const result=await a.feedback('private-token',3,12,'like');
 assert.deepEqual(result,{ok:true,vote:'like'});
 assert.equal(calls[0][0],'/academic/courses/3/messages/12/feedback');
 assert.equal(calls[0][1],'private-token');
 assert.deepEqual(calls[0][2],{method:'POST',body:'{"vote":"like"}'});
 await assert.rejects(loadAcademicApi(async()=>({ok:false,vote:'like'})).feedback('token',3,12,'like'));
 await assert.rejects(loadAcademicApi(async()=>({ok:true,vote:'unknown'})).feedback('token',3,12,'like'));
});

test('Academic answer action files have no TypeScript parser diagnostics',()=>{
 for(const file of ['../src/academicAnswerActions.ts','../src/NativeAcademicAnswerActions.tsx']){
  const result=compile(file),errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).map(d=>ts.flattenDiagnosticMessageText(d.messageText,' '));
  assert.deepEqual(errors,[],file+': '+errors.join('; '));
 }
});
