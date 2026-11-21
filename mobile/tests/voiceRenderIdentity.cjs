const fs=require('node:fs');
const ts=require('typescript');
const assert=require('node:assert/strict');
const {test}=require('node:test');

const source=fs.readFileSync(require.resolve('../src/VoiceExamEntry.tsx'),'utf8');
const parsed=ts.createSourceFile('VoiceExamEntry.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
function componentKeys(){
 const result=new Map();
 const visit=node=>{
  if(ts.isJsxSelfClosingElement(node)){
   const name=node.tagName.getText(parsed);
   const key=node.attributes.properties.find(item=>ts.isJsxAttribute(item)&&item.name.getText(parsed)==='key');
   if(key&&ts.isJsxAttribute(key)&&key.initializer&&ts.isJsxExpression(key.initializer))result.set(name,key.initializer.expression?.getText(parsed)||'');
  }
  ts.forEachChild(node,visit);
 };
 visit(parsed);return result;
}

test('native voice patient, recorder and approval remount keys never contain bearer credentials',()=>{
 const keys=componentKeys();
 assert.equal(keys.get('NativePatientSelect'),'patientSelectRenderKey');
 assert.equal(keys.get('NativeVoiceRecorder'),'voiceRecorderRenderKey');
 assert.equal(keys.get('NativeVoiceApproval'),'voiceApprovalRenderKey');
 for(const [component,expression] of keys){
  assert.ok(!/(?:^|[^A-Za-z0-9_])token(?:[^A-Za-z0-9_]|$)/.test(expression),component+' key must not contain an access token');
 }
});

test('opaque voice identities still rotate on account, patient and review scope changes',()=>{
 assert.match(source,/import \{nextSessionRenderKey\} from ["']\.\/sessionRenderKey["']/);
 assert.match(source,/patientSelectRenderKey=useMemo\(\(\)=>nextSessionRenderKey\(\),\[token\]\)/);
 assert.match(source,/voiceRecorderRenderKey=useMemo\(\(\)=>nextSessionRenderKey\(\),\[token,userId,selected\?\.id\]\)/);
 assert.match(source,/voiceApprovalRenderKey=useMemo\(\(\)=>nextSessionRenderKey\(\),\[token,userId,selected\?\.id,review\?\.revision\]\)/);
});

test('native voice consent discloses the same Gemini transcription and Claude review boundary as web',()=>{
 assert.ok(source.includes('Sesin Gemini ile yazıya çevrilmesini'));
 assert.ok(source.includes('geçici metnin klinik bilgiler ve kaynaklarla Claude tarafından değerlendirilmesini'));
 assert.ok(source.includes('bu tam anonimleştirme garantisi değildir'));
 assert.ok(source.includes('Ham ses ve tam konuşma dökümü hasta dosyasına otomatik yazılmaz'));
});
