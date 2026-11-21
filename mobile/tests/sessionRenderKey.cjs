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
 assert.ok(!keys.some(value=>value.includes('token')||value.includes('scope')||value.includes('userId')),'React keys must not contain bearer credentials or identity tuples');
 assert.ok(source.includes("import {nextSessionRenderKey} from './sessionRenderKey';"));
 assert.ok(source.includes('const profileRenderIdentity=useRef<{scope:string;key:string}|null>(null);'));
 assert.ok(source.includes('profileRenderIdentity.current.scope!==scope'),'the opaque key must rotate when the account, token or patient scope changes');
});


test('tooth-chart analysis history uses an opaque render key while retaining tooth-scoped remounts',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
 const parsed=ts.createSourceFile('NativeToothChart.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const history=[];
 const visit=node=>{
  if(ts.isJsxSelfClosingElement(node)&&node.tagName.getText(parsed)==='NativePatientHistory'){
   const key=node.attributes.properties.find(item=>ts.isJsxAttribute(item)&&item.name.getText(parsed)==='key');
   history.push(key&&ts.isJsxAttribute(key)&&key.initializer&&ts.isJsxExpression(key.initializer)?key.initializer.expression?.getText(parsed)||'':'');
  }
  ts.forEachChild(node,visit);
 };
 visit(parsed);
 assert.equal(history.length,1,'the selected tooth must own exactly one analysis-history section');
 assert.equal(history[0],'historyRenderKey','the history section must not use a raw token-bearing React key');
 assert.ok(!history[0].includes('token')&&!history[0].includes('scope'),'renderer identity must not contain credentials or the raw identity tuple');
 assert.ok(source.includes('import {nextSessionRenderKey} from "./sessionRenderKey";'));
 assert.ok(source.includes('const historyScope=`${userId}:${token}:${patientId}:${selected}`;'));
 assert.ok(source.includes('historyRenderIdentity.current.scope!==historyScope'),'switching account, session, patient or selected tooth must remount the scoped history section');
});

test('clinical media analysis-upload child uses the opaque account image scope as its key',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 const parsed=ts.createSourceFile('NativePatientMedia.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const uploads=[];
 const visit=node=>{
  if(ts.isJsxSelfClosingElement(node)&&node.tagName.getText(parsed)==='NativeAnalysisUpload'){
   const key=node.attributes.properties.find(item=>ts.isJsxAttribute(item)&&item.name.getText(parsed)==='key');
   uploads.push(key&&ts.isJsxAttribute(key)&&key.initializer&&ts.isJsxExpression(key.initializer)?key.initializer.expression?.getText(parsed)||'':'');
  }
  ts.forEachChild(node,visit);
 };
 visit(parsed);
 assert.equal(uploads.length,1,'the clinical archive owns one analysis composer');
 assert.equal(uploads[0],'imageScope','the upload composer key must not be the bearer-token owner tuple');
 assert.ok(source.includes("const imageScope=useMemo(()=>'clinical-media-scope-'+(++nextClinicalMediaImageScope),[token,userId,patientId]);"),'the opaque scope must rotate on account, session or patient changes');
});