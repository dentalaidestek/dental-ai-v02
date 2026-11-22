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

test('native voice entry follows the web patient-first hierarchy and privacy guidance',()=>{
 for(const fragment of [
  'KLİNİK ASİSTANINIZ',
  'Görüşmeye odaklanın. Muayene notlarını birlikte düzenleyelim.',
  'Yeni hastayla başla',
  'İsim bilgisi gerekmez',
  'Mevcut hastayı seç',
  'Ad, soyad veya hasta kodu',
  'Mikrofon sizin kontrolünüzde',
  'Hasta seçmek mikrofonu açmaz.',
  'Kaydedilecek alanları son adımda siz seçersiniz.',
  'searchTitle="Mevcut hastayı seç"',
  'searchHint="Sesli muayeneye bağlanacak hastayı bulun"',
  'emptyLabel="Ad, soyad veya hasta kodu ile hasta seçin"'
 ])assert.ok(source.includes(fragment),fragment);
 assert.match(source,/\[\["1","Hasta seç"\],\["2","Görüşmeyi başlat"\],\["3","Kontrol et ve kaydet"\]\]/);
});

test('a patient-specific native voice route opens the examination without a redundant selection step',()=>{
 assert.ok(source.includes('routePatientSelected=typeof initialPatientId==="number"&&selected?.id===initialPatientId'));
 assert.ok(source.includes('const enterExam=startAfterSelection.current||routePatientSelected'));
 assert.ok(source.includes('setStage(enterExam?"exam":"select")'));
});


test('approved anamnesis history keeps bearer credentials out of React cache state',()=>{
 const history=fs.readFileSync(require.resolve('../src/NativePatientVoiceHistory.tsx'),'utf8');
 assert.ok(history.includes("import useSessionRenderKey from './useSessionRenderKey';"));
 assert.ok(history.includes('const scopeKey=useSessionRenderKey(scope);'));
 assert.ok(history.includes('const active=useRef(scopeKey),generation=useRef(0);'));
 assert.ok(history.includes('useState<{scopeKey:string;history:VoiceHistory}|null>'));
 assert.ok(history.includes('data?.scopeKey===scopeKey'));
 assert.ok(!history.includes('useState<{scope:string;history:VoiceHistory}|null>'));
 assert.ok(!history.includes('const active=useRef(scope),'));
});
