const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;

function mountMedia(getMedia, options={}){
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const native=Object.fromEntries(['ActivityIndicator','FlatList','Image','Modal','Pressable','ScrollView','Text','View'].map(x=>[x,x]));
 native.Alert={alert(...args){options.onAlert?.(...args)}};
 const exports={};
 vm.runInNewContext(code,{exports,require:name=>{
  if(name==='react')return {...React,default:React};
  if(name==='react-native')return native;
  if(name==='expo-image-picker')return {};
  if(name==='./api')return {uploadPatientMedia:async()=>{}};
  if(name==='./modernApi')return {getMedia,analyzeSelectedPatientMedia:async()=>({analysis_id:1}),deleteMedia:async(...args)=>{options.onDelete?.(...args)},deleteAllPatientMedia:async(...args)=>{options.onDelete?.(...args)}};
  if(name==='./realtime')return {useRealtime:()=>({lastEvent:null})};
  throw Error('Unexpected import '+name);
 }});
 return exports.default;
}
const visible=node=>typeof node==='string'?node:Array.isArray(node)?node.map(visible).join(''):node?.children?node.children.map(visible).join(''):'';

test('switching accounts starts a new gallery request while the old request is pending',async()=>{
 let resolveOld;
 const calls=[];
 const Media=mountMedia(async(token,id)=>{
  calls.push([token,id]);
  if(token==='old')return new Promise(resolve=>{resolveOld=resolve});
  return {items:[{id:9,url:'https://example.invalid/new.jpg',media_type:'PHOTO'}],next_before:null};
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis:()=>{}}))});
 assert.deepEqual(calls,[['old',1]]);
 await renderer.act(async()=>{tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis:()=>{}}))});
 assert.deepEqual(calls,[['old',1],['new',2]],'new account must not inherit old loading lock');
 await renderer.act(async()=>{resolveOld({items:[{id:1,url:'https://example.invalid/old.jpg',media_type:'PHOTO'}],next_before:null})});
 const images=tree.root.findAllByType('Image');
 assert.ok(images.some(x=>String(x.props.source?.uri).includes('new.jpg')));
 assert.ok(!images.some(x=>String(x.props.source?.uri).includes('old.jpg')),'stale patient media must never render');
 await renderer.act(async()=>tree.unmount());
});


test('uncertain media deletion blocks repeated destructive requests until reconciliation',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/async function remove\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\)return;/);
 assert.match(source,/setUncertain\(true\);setError\(\(e instanceof Error\?e\.message:'Silme durumu doğrulanamadı\.'\)/);
 assert.match(source,/function confirmDelete\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\)return;/);
 assert.match(source,/confirmDelete\(preview\.id\),busy\|\|uncertain/);
 assert.match(source,/confirmDelete\(\),busy\|\|uncertain/);
});

test('clinical gallery offers recovery for failed reads and distinguishes empty from error',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/Galeriyi yeniden yükle/);
 assert.match(source,/Bu hastaya ait klinik görsel bulunmuyor/);
 assert.match(source,/!loading&&!!error&&button\('Galeriyi yeniden yükle'/);
 assert.match(source,/!loading&&!error&&items\.length===0/);
 assert.match(source,/confirmDelete\(\),busy\|\|uncertain\|\|items\.length===0/);
});

test('uncertain media mutations freeze selection and pagination until reconciliation',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/disabled=\{busy\|\|uncertain\} onPress=\{\(\)=>toggle\(item\.id\)\}/);
 assert.match(source,/setSelected\(selected\.length\?\[\]:items\.slice\(0,4\)\.map\(x=>x\.id\)\),busy\|\|uncertain/);
 assert.match(source,/onEndReached=\{\(\)=>\{if\(cursor&&!loading&&!error&&!uncertain\)/);
});


test('account switch never exposes old patient thumbnails during pending new request',async()=>{
 let resolveNext;
 const Media=mountMedia(async(token)=>token==='old'
  ?{items:[{id:1,url:'https://example.invalid/old.jpg',media_type:'PHOTO'}],next_before:null}
  :new Promise(resolve=>{resolveNext=resolve}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis:()=>{}}))});
 assert.ok(tree.root.findAllByType('Image').some(x=>x.props.source?.uri?.includes('old.jpg')));
 await renderer.act(async()=>{tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis:()=>{}}))});
 assert.ok(!tree.root.findAllByType('Image').some(x=>x.props.source?.uri?.includes('old.jpg')));
 await renderer.act(async()=>{resolveNext({items:[],next_before:null})});
 await renderer.act(async()=>tree.unmount());
});


test('clinical modal and destructive actions require the current loaded account',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/visible=\{open&&loadedOwner===owner\}/);
 assert.match(source,/function confirmDelete\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)return;/);
 assert.match(source,/async function analyze\(\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\|\|!selected\.length\)return;/);
});


test('gallery selection and pagination are restricted to the loaded patient scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/function toggle\(id:number\)\{if\(mutation\.current\|\|uncertain\|\|loadedOwner!==owner\|\|!visibleItems\.some\(item=>item\.id===id\)\)return;/);
 assert.match(source,/if\(loadedOwner===owner&&cursor&&!loading&&!error&&!uncertain&&!mutation\.current\)/);
});


test('refresh is blocked during unresolved mutation and paging callback observes current scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/if\(loadLock\.current\|\|\(more&&\(mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)\)\)return;/);
 assert.match(source,/onRefresh=\{\(\)=>\{if\(!mutation\.current&&!uncertain&&loadedOwner===owner\)void loader\.current\(\)\}\}/);
 assert.match(source,/\[token,patientId,cursor,uncertain,loadedOwner\]/);
});


test('delayed delete confirmation from previous account cannot delete old patient media',async()=>{
 let confirmation;
 const deletes=[];
 const Media=mountMedia(async()=>({items:[{id:5,url:'https://example.invalid/file',media_type:'PHOTO'}],next_before:null}),{
  onAlert:(_title,_message,buttons)=>{confirmation=buttons.find(button=>button.text==='Sil')},
  onDelete:(...args)=>deletes.push(args)
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis:()=>{}}))});
 const deleteButton=tree.root.findAllByType('Pressable').find(node=>visible(node).includes('Tüm Görselleri Sil'));
 assert.ok(deleteButton,'destructive action should be available for the loaded patient');
 await renderer.act(async()=>deleteButton.props.onPress());
 assert.ok(confirmation,'delete confirmation should be displayed');
 await renderer.act(async()=>tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis:()=>{}})));
 await renderer.act(async()=>{await confirmation.onPress()});
 assert.deepEqual(deletes,[],'stale confirmation must not send a delete request');
 await renderer.act(async()=>tree.unmount());
});


test('every delayed clinical media action verifies the current patient before network mutations',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/async function remove\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/function confirmDelete\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/async function upload\(\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/async function analyze\(\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/async function pick\(type:'PHOTO'\|'RADIOGRAPH'\)\{\s*if\(!current\(\)\|\|mutation\.current/);
});

test('clinical gallery preview and selection handlers require the current patient scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/function toggle\(id:number\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/onPress=\{\(\)=>\{if\(!current\(\)\|\|loadedOwner!==owner\|\|mutation\.current\|\|uncertain\)return;setPreview\(item\)/);
 assert.match(source,/onPress=\{\(\)=>\{if\(!current\(\)\|\|loadedOwner!==owner\|\|mutation\.current\|\|uncertain\)return;setOpen\(true\)/);
});

test('picker continuation and delayed acknowledgement cannot bypass scope or mutation locks',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/if\(!current\(\)\|\|mutation\.current\|\|uncertain\)return;if\(!permission\.granted\)/);
 assert.match(source,/if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|result\.canceled\)return/);
 assert.match(source,/onPress:\(\)=>\{if\(!current\(\)\|\|mutation\.current\|\|!uncertain\)return;setUncertain\(false\)/);
});
