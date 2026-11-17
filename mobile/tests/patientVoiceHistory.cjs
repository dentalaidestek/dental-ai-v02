const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const presentation={};
const helperCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/patientVoiceHistoryPresentation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(helperCode,{exports:presentation});
const history=(value='Olumsuz beyan: sistemik rahatsızlık yok')=>({ok:true,revision:'a'.repeat(64),notice:'Önceki hekim onaylı sesli muayene kayıtlarıdır.',fields:{medical_history:{value,quote:value,analysis_id:17},medications:{value:'Metformin beyanı',quote:'Metformin kullanıyorum',analysis_id:17},allergies:{value:'Olmadığı belirtildi: penisilin alerjisi',quote:'Alerjim yok',analysis_id:17}}});
function mount(getVoiceHistory){
 const source=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePatientVoiceHistory.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={},native={ActivityIndicator:'ActivityIndicator',Pressable:'Pressable',Text:'Text',View:'View'};
 let event=null;
 vm.runInNewContext(source,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./voiceApi'?{getVoiceHistory}:name==='./realtime'?{useRealtime:()=>({lastEvent:event})}:name==='./patientVoiceHistoryPresentation'?presentation:{default:name.slice(2)}});
 return {Component:exports.default,setEvent:value=>{event=value}};
}
const content=node=>typeof node==='string'?node:Array.isArray(node)?node.map(content).join(''):node?.children?node.children.map(content).join(''):'';
const press=(tree,label)=>tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(item=>content(item)===label));
test('approved anamnesis rows preserve negative statements and stable clinical ordering',()=>{
 const rows=presentation.patientVoiceHistoryRows({allergies:{value:'Alerjim yok',quote:'Alerjim yok',analysis_id:4},medical_history:{value:'Diyabet öyküsü',quote:'Şekerim var',analysis_id:3},medications:{value:'Metformin',quote:'Metformin',analysis_id:3}});
 assert.deepEqual(rows.map(row=>row.key),['medical_history','medications','allergies']);
 assert.equal(rows[2].value,'Alerjim yok');
 assert.equal(rows[0].analysisId,3);
 assert.deepEqual(presentation.patientVoiceHistoryRows({unknown:{value:'private',quote:'private',analysis_id:1}}),[]);
 assert.deepEqual(presentation.patientVoiceHistoryRows(null),[]);
});
test('patient profile shows only server-approved fields with source ids and a current-status warning',async()=>{
 const api=mount(async()=>history());let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('Hekim Onaylı Anamnez'));
 assert.ok(rendered.includes('Olumsuz beyan: sistemik rahatsızlık yok'));
 assert.ok(rendered.includes('Metformin beyanı'));
 assert.ok(rendered.includes('Olmadığı belirtildi: penisilin alerjisi'));
 assert.ok(rendered.includes('Sesli muayene #17'));
 assert.ok(rendered.includes('güncel hastalık'));
 await renderer.act(async()=>tree.unmount());
});
test('empty approved history does not add an empty anamnesis card',async()=>{
 const api=mount(async()=>({ok:true,revision:'a'.repeat(64),notice:'no history',fields:{}}));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(tree.toJSON(),null);
 await renderer.act(async()=>tree.unmount());
});
test('anamnesis request errors expose a retry without showing cached data',async()=>{
 let calls=0;const api=mount(async()=>{calls++;if(calls===1)throw Error('Yetkili hasta geçmişi alınamadı');return history()});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.ok(content(tree.toJSON()).includes('Yetkili hasta geçmişi alınamadı'));
 await renderer.act(async()=>{press(tree,'Yeniden dene').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.ok(content(tree.toJSON()).includes('Hekim Onaylı Anamnez'));
 assert.equal(calls,2);
 await renderer.act(async()=>tree.unmount());
});
test('switching patient invalidates a late anamnesis response from the previous profile',async()=>{
 let resolveOld;const api=mount((_token,id)=>id===8?new Promise(resolve=>{resolveOld=resolve}):Promise.resolve(history('B hesabına ait olmayan farklı hasta verisi')));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'owner-token',patientId:9}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{resolveOld(history('Eski hasta özel anamnez metni'));await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('B hesabına ait olmayan farklı hasta verisi'));
 assert.equal(rendered.includes('Eski hasta özel anamnez metni'),false);
 await renderer.act(async()=>tree.unmount());
});
