const fs=require('node:fs');
const ts=require('typescript');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const useSessionRenderKey=require('./helpers/useSessionRenderKeyModule.cjs').default;
const {nextSessionRenderKey,resolveSessionRenderIdentity}=require('./helpers/sessionRenderKeyModule.cjs');

test('session render keys are opaque, unique and do not encode credentials',()=>{
 const first=nextSessionRenderKey(),second=nextSessionRenderKey();
 assert.match(first,/^dai-session-[0-9a-z]+$/);
 assert.notEqual(first,second);
 for(const secret of ['Bearer synthetic-secret-token','eyJhbGciOiJIUzI1NiJ9.synthetic.signature']) {
  assert.ok(!first.includes(secret));
  assert.ok(!second.includes(secret));
 }
});

test('session scope changes rotate an opaque key without exposing the scope',()=>{
 const first=resolveSessionRenderIdentity(null,'user:7:Bearer synthetic-secret-token');
 const stable=resolveSessionRenderIdentity(first,'user:7:Bearer synthetic-secret-token');
 const rotated=resolveSessionRenderIdentity(first,'user:7:Bearer replacement-secret-token');
 assert.strictEqual(stable,first,'a stable scope must retain its renderer identity');
 assert.notEqual(rotated.key,first.key,'a new session must remount scoped children');
 assert.match(first.key,/^dai-session-[0-9a-z]+$/);
 assert.match(rotated.key,/^dai-session-[0-9a-z]+$/);
 for(const value of [first.key,rotated.key]){
  assert.ok(!value.includes('synthetic-secret-token'));
  assert.ok(!value.includes('replacement-secret-token'));
  assert.ok(!value.includes('Bearer'));
 }
});

test('all native screen React keys exclude bearer credentials',()=>{
 const files=["App.tsx","ChatAttachmentComposer.tsx","ChatImageViewer.tsx","ModernScreens.tsx","NativeAcademic.tsx","NativeAcademicAnswerActions.tsx","NativeAcademicComposer.tsx","NativeAcademicFile.tsx","NativeAcademicSource.tsx","NativeAccount.tsx","NativeAnalysisUpload.tsx","NativeAnswerText.tsx","NativeAuth.tsx","NativeChatDocument.tsx","NativeChatTools.tsx","NativeClinicalReview.tsx","NativeConsultationRequest.tsx","NativeDateField.tsx","NativeDentalAI.tsx","NativeExpertPerformance.tsx","NativeExpertProfile.tsx","NativeImageEditor.tsx","NativeNewPatient.tsx","NativePatientAppointment.tsx","NativePatientHistory.tsx","NativePatientMedia.tsx","NativePatientProfile.tsx","NativePatientSelect.tsx","NativePatientVoiceHistory.tsx","NativeProfessional.tsx","NativeProgram.tsx","NativePublications.tsx","NativePushSettings.tsx","NativeRelationships.tsx","NativeSocialAdmin.tsx","NativeSocialMediaViewer.tsx","NativeSupportRequests.tsx","NativeTimeField.tsx","NativeToothChart.tsx","NativeToothVisual.tsx","NativeVisionViewer.tsx","NativeVoiceApproval.tsx","NativeVoiceDeviceCheck.tsx","NativeVoiceRecorder.tsx","SocialScreens.tsx"];
 for(const name of files){
  const relative=name==='App.tsx'?'../App.tsx':'../src/'+name;
  const source=fs.readFileSync(require.resolve(relative),'utf8');
  const parsed=ts.createSourceFile(name,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const keys=[];
  const visit=node=>{
   if(ts.isJsxAttribute(node)&&node.name.getText(parsed)==='key'&&node.initializer&&ts.isJsxExpression(node.initializer))
    keys.push(node.initializer.expression?.getText(parsed)||'');
   ts.forEachChild(node,visit);
  };
  visit(parsed);
  const credentialKey=keys.find(value=>/(?:^|[^A-Za-z0-9_])(token|accessToken|sessionToken|authorization|bearer)(?:[^A-Za-z0-9_]|$)/i.test(value));
  assert.equal(credentialKey,undefined,name+' must not put credentials into a React key');
 }
 const hook=fs.readFileSync(require.resolve('../src/useSessionRenderKey.ts'),'utf8');
 assert.ok(hook.includes('resolveSessionRenderIdentity'));
 assert.ok(hook.includes('return identity.current.key'));
 const app=fs.readFileSync(require.resolve('../App.tsx'),'utf8');
 assert.ok(app.includes('function SessionScope('),'navigation route wrappers must use an opaque session scope');
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


test('voice entry VM harnesses map the opaque session-key helper in every rendered path',()=>{
 const source=fs.readFileSync(require.resolve('./voiceWorkflow.cjs'),'utf8');
 assert.ok(source.includes("const sessionRenderKeyExports=require('./helpers/sessionRenderKeyModule.cjs');"));
 const mappings=source.split("n.startsWith('./sessionRenderKey')?sessionRenderKeyExports").length-1;
 assert.equal(mappings,6,'all voice and approval VM loaders must resolve extensionless and explicit TypeScript helper imports');
 assert.ok(source.includes("assert.equal(typeof sessionRenderKeyExports.nextSessionRenderKey,'function'"),'the VM suite must fail early if the production helper bridge is not callable');
});

test('patient profile child sections use an opaque key across token and patient scope changes',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientProfile.tsx'),'utf8');
 const parsed=ts.createSourceFile('NativePatientProfile.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const keys=[];
 const visit=node=>{
  // Only the three remount-boundary children matter here; .map() list-item keys are legitimate.
  if(ts.isJsxSelfClosingElement(node)&&['NativePatientMedia','NativePatientHistory','NativePatientVoiceHistory'].includes(node.tagName.getText(parsed))){
   const key=node.attributes.properties.find(item=>ts.isJsxAttribute(item)&&item.name.getText(parsed)==='key');
   keys.push(key&&ts.isJsxAttribute(key)&&key.initializer&&ts.isJsxExpression(key.initializer)?key.initializer.expression?.getText(parsed)||'':'');
  }
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

test('React session-key hook keeps identity stable and rotates it without exposing credentials',()=>{
 const Probe=({scope})=>React.createElement('Text',{value:useSessionRenderKey(scope)});
 let tree;
 renderer.act(()=>{tree=renderer.create(React.createElement(Probe,{scope:'account:1:Bearer synthetic-first-token'}))});
 const first=tree.root.findByType('Text').props.value;
 renderer.act(()=>tree.update(React.createElement(Probe,{scope:'account:1:Bearer synthetic-first-token'})));
 assert.equal(tree.root.findByType('Text').props.value,first,'the same session scope must keep its renderer identity');
 renderer.act(()=>tree.update(React.createElement(Probe,{scope:'account:1:Bearer synthetic-second-token'})));
 const second=tree.root.findByType('Text').props.value;
 assert.notEqual(second,first,'a changed session scope must remount scoped children');
 assert.match(first,/^dai-session-[0-9a-z]+$/);
 assert.match(second,/^dai-session-[0-9a-z]+$/);
 assert.ok(!first.includes('Bearer')&&!first.includes('synthetic-first-token'));
 assert.ok(!second.includes('Bearer')&&!second.includes('synthetic-second-token'));
 renderer.act(()=>tree.unmount());
});


test('patient, Program and Academic renderers share the production opaque-key hook contract',()=>{
 const app=fs.readFileSync(require.resolve('../App.tsx'),'utf8');
 const program=fs.readFileSync(require.resolve('../src/NativeProgram.tsx'),'utf8');
 const academic=fs.readFileSync(require.resolve('../src/NativeAcademic.tsx'),'utf8');
 const programHarness=fs.readFileSync(require.resolve('./programParity.cjs'),'utf8');
 const academicHarness=fs.readFileSync(require.resolve('./academicWorkflow.cjs'),'utf8');
 assert.ok(app.includes('NativePatientProfile key={profileRenderKey}'));
 assert.ok(program.includes("import useSessionRenderKey from './useSessionRenderKey';"));
 assert.ok(academic.includes("import useSessionRenderKey from './useSessionRenderKey';"));
 assert.ok(programHarness.includes("name==='./useSessionRenderKey'?require('./helpers/useSessionRenderKeyModule.cjs')"));
 assert.ok(academicHarness.includes("n==='./useSessionRenderKey'?require('./helpers/useSessionRenderKeyModule.cjs')"));
});
