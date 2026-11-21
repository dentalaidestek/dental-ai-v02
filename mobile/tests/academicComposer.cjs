const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const source=fs.readFileSync(path.join(__dirname,'../src/NativeAcademicComposer.tsx'),'utf8');
const compiled=ts.transpileModule(source,{fileName:'NativeAcademicComposer.tsx',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const composerExports={};
const native={Pressable:'Pressable',Text:'Text',TextInput:'TextInput',View:'View',StyleSheet:{create:value=>value}};
vm.runInNewContext(compiled,{exports:composerExports,require:name=>name==='react'?{...React,default:React}:native});
const Composer=composerExports.default;

test('Academic composer enforces the web 8000-character limit and exposes accessible send controls',async()=>{
 let value='';const changes=[];
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Composer,{value,onChangeText:next=>{value=next;changes.push(next)},onSend:()=>{},disabled:false}))});
 const input=tree.root.findByType('TextInput'),send=tree.root.findByType('Pressable');
 assert.equal(input.props.accessibilityLabel,'Akademik soru');
 assert.equal(input.props.maxLength,8000);
 assert.equal(input.props.multiline,true);
 assert.equal(input.props.editable,true);
 assert.equal(send.props.accessibilityRole,'button');
 assert.equal(send.props.accessibilityLabel,'Akademik soruyu gönder');
 assert.equal(send.props.disabled,true);
 await renderer.act(async()=>input.props.onChangeText('Notlarımdan açıkla'));
 assert.deepEqual(changes,['Notlarımdan açıkla']);
 await renderer.act(async()=>tree.update(React.createElement(Composer,{value,onChangeText:next=>{value=next},onSend:()=>{},disabled:false})));
 assert.equal(tree.root.findByType('Pressable').props.disabled,false);
 await renderer.act(async()=>tree.unmount());
});

test('Academic composer sends only a non-empty enabled draft',async()=>{
 let sent=0,tree;
 const props={value:'  ',onChangeText:()=>{},onSend:()=>{sent++},disabled:false};
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Composer,props))});
 const send=tree.root.findByType('Pressable');
 assert.equal(send.props.disabled,true);
 await renderer.act(async()=>tree.update(React.createElement(Composer,{...props,value:'Konu özeti'})));
 const enabled=tree.root.findByType('Pressable');
 assert.equal(enabled.props.disabled,false);
 await renderer.act(async()=>enabled.props.onPress());
 assert.equal(sent,1);
 await renderer.act(async()=>tree.update(React.createElement(Composer,{...props,value:'Konu özeti',disabled:true})));
 const locked=tree.root.findByType('Pressable');
 assert.equal(locked.props.disabled,true);
 assert.equal(tree.root.findByType('TextInput').props.editable,false);
 await renderer.act(async()=>locked.props.onPress());
 assert.equal(sent,1);
 await renderer.act(async()=>tree.unmount());
});
