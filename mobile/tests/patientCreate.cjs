const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const renderer=require('react-test-renderer');

global.IS_REACT_ACT_ENVIRONMENT=true;

require.extensions['.ts']=(module,filename)=>{
  const source=fs.readFileSync(filename,'utf8');
  module._compile(ts.transpileModule(source,{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020},
  }).outputText,filename);
};

class ApiError extends Error{
  constructor(status,message){super(message);this.status=status;}
}

function component(createPatient){
  const source=fs.readFileSync(require.resolve('../src/NativeNewPatient.tsx'),'utf8');
  const code=ts.transpileModule(source,{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020},
  }).outputText;
  const exports={};
  const native={
    ActivityIndicator:'ActivityIndicator',
    Alert:{alert(){}},
    Pressable:'Pressable',
    ScrollView:'ScrollView',
    Text:'Text',
    TextInput:'TextInput',
    View:'View',
  };
  const endpoints={
    ApiError,
    createPatient:createPatient|| (async()=>({patient:{id:8}})),
    getPatient:async()=>({patient:{id:8}}),
  };
  vm.runInNewContext(code,{
    exports,
    require:name=>name==='react'?{...React,default:React}:
      name==='react-native'?native:
      name==='./api'?endpoints:
      name==='./NativeDateField'?{default:'NativeDateField'}:
      name==='./patientCreateValidation'?require('../src/patientCreateValidation.ts'):
      {},
  });
  return exports.default;
}

const text=node=>typeof node==='string'?node:
  Array.isArray(node)?node.map(text).join(''):
  node?.children?node.children.map(text).join(''):'';

test('native new-patient form blocks an empty phone before creating a record',async()=>{
  let calls=0;
  const Screen=component(async()=>{calls++;return {patient:{id:8}}});
  let tree;
  await renderer.act(async()=>{tree=renderer.create(React.createElement(Screen,{token:'synthetic-token',onCreated(){}}))});
  const phone=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Telefon *');
  assert.ok(phone,'phone must be marked required like the web form');
  assert.equal(phone.props.maxLength,11);
  assert.equal(phone.props.autoComplete,'tel');
  const submit=()=>tree.root.findAllByType('Pressable').find(node=>text(node).includes('Hastayı Kaydet'));
  await renderer.act(async()=>submit().props.onPress());
  assert.equal(calls,0,'empty phone must not reach the API');
  assert.ok(text(tree.toJSON()).includes('Telefon numarası zorunludur.'));
  await renderer.act(async()=>tree.unmount());
});

test('native new-patient form sanitizes and submits a valid Turkish phone number',async()=>{
  const calls=[],created=[];
  const Screen=component(async(_token,payload)=>{calls.push(payload);return {patient:{id:8}}});
  let tree;
  await renderer.act(async()=>{tree=renderer.create(React.createElement(Screen,{token:'synthetic-token',onCreated:p=>created.push(p.id)}))});
  const fill=async(label,value)=>{
    const input=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel===label);
    assert.ok(input,'missing '+label);
    await renderer.act(async()=>input.props.onChangeText(value));
  };
  await fill('Ad *','Ada');
  await fill('Soyad *','Kaya');
  await fill('Telefon *','0555-123-45-67');
  const phone=tree.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Telefon *');
  assert.equal(phone.props.value,'05551234567');
  await renderer.act(async()=>tree.root.findAllByType('Pressable').find(node=>text(node).includes('Hastayı Kaydet')).props.onPress());
  assert.equal(calls.length,1);
  assert.equal(calls[0].phone,'05551234567');
  assert.deepEqual(created,[8]);
  await renderer.act(async()=>tree.unmount());
});
