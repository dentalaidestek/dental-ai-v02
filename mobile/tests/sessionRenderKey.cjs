const fs=require('node:fs');
const ts=require('typescript');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const {nextSessionRenderKey}=require('./helpers/sessionRenderKeyModule.cjs');

test('session render keys are opaque, unique and do not encode credentials',()=>{
 const first=nextSessionRenderKey(),second=nextSessionRenderKey();
 assert.match(first,/^dai-session-[0-9a-z]+$/);
 assert.notEqual(first,second);
 for(const secret of ['Bearer synthetic-secret-token','eyJhbGciOiJIUzI1NiJ9.synthetic.signature']) {
  assert.ok(!first.includes(secret));
  assert.ok(!second.includes(secret));
 }
});

test('analysis and clinical viewer components never interpolate credentials into React keys',()=>{
 const files=['NativeDentalAI.tsx','NativeClinicalReview.tsx'];
 for(const name of files){
  const source=fs.readFileSync(require.resolve('../src/'+name),'utf8');
  const parsed=ts.createSourceFile(name,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const keys=[];
  const visit=node=>{
   if(ts.isJsxAttribute(node)&&node.name.getText(parsed)==='key'&&node.initializer&&ts.isJsxExpression(node.initializer))keys.push(node.initializer.expression?.getText(parsed)||'');
   ts.forEachChild(node,visit);
  };
  visit(parsed);
  assert.ok(keys.length>0,name+' should retain keyed identity boundaries');
  assert.ok(keys.every(value=>!/(?:^|[^A-Za-z0-9_])token(?:[^A-Za-z0-9_]|$)/.test(value)),name+' contains a credential-derived React key');
  assert.ok(keys.some(value=>value.includes('renderSessionKey')||value.includes('viewerSessionKey')),name+' must use an opaque session identity');
 }
});

test('all VM component harnesses resolve the opaque session-key helper',()=>{
 const cases=[
  ['analysisRefresh.cjs',"name==='./sessionRenderKey'?sessionRenderKeyExports"],
  ['analysisRecovery.cjs',"name==='./sessionRenderKey'?sessionRenderKeyExports"],
  ['clinicalWorkflow.cjs',"n==='./sessionRenderKey'?sessionRenderKeyExports"],
 ];
 for(const [file,contract] of cases){
  const source=fs.readFileSync(require.resolve('./'+file),'utf8');
  assert.ok(source.includes("require('./helpers/sessionRenderKeyModule.cjs')"),file+' must load the shared TypeScript bridge');
  assert.ok(source.includes(contract),file+' must map the sessionRenderKey import into its VM');
 }
});


test('patient profile child sections use an opaque key across token and patient scope changes',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientProfile.tsx'),'utf8');
 const parsed=ts.createSourceFile('NativePatientProfile.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const keys=[];
 const visit=node=>{
  if(ts.isJsxAttribute(node)&&node.name.getText(parsed)==='key'&&node.initializer&&ts.isJsxExpression(node.initializer))keys.push(node.initializer.expression?.getText(parsed)||'');
  ts.forEachChild(node,visit);
 };
 visit(parsed);
 assert.equal(keys.length,3,'media, analysis history and approved voice history keep explicit remount boundaries');
 assert.ok(keys.every(value=>value==='profileRenderKey'),'profile children must not use the raw token-bearing scope as a React key');
 assert.ok(!keys.some(value=>/\\b(?:token|scope|userId)\\b/.test(value)),'React keys must not contain bearer credentials or identity tuples');
 assert.match(source,/import \\{nextSessionRenderKey\\} from '\\.\\/sessionRenderKey';/);
 assert.match(source,/profileRenderIdentity=useRef<\\{scope:string;key:string\\}\\|null>\\(null\\)/);
 assert.match(source,/profileRenderIdentity\\.current\\.scope!==scope/,'the opaque key must rotate when the account, token or patient scope changes');
});
