const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const src=f=>fs.readFileSync(require.resolve('../src/'+f),'utf8');
test('case chat composer mirrors the web room: plus attach toggle, round blue send arrow',()=>{
 const screens=src('ModernScreens.tsx');
 // Web composer: expert-media-composer + Dosya ekle, then expert-send-circle ↑.
 assert.ok(screens.includes('accessibilityLabel="Dosya ekle"'),'plus attach button must exist like the web room');
 assert.ok(screens.includes('accessibilityLabel="Gönder"'),'send button must expose the web aria-label');
 assert.ok(screens.includes('<Text style={s.sendArrow}>↑</Text>'),'send control must be the web round arrow, not a Gönder text pill');
 assert.ok(!screens.includes('"Gönder"</Text>'),'the old Gönder text pill must be removed');
 assert.ok(screens.includes('optionsOpen={attachOpen}'),'attachment options must follow the plus toggle');
 // Web tokens: #eff6ff plus circle, #2563eb send circle, 42px round.
 assert.ok(screens.includes('plusBtn:{width:42,height:42,minWidth:42,borderRadius:21,backgroundColor:"#eff6ff"'),'plus button uses the web circle style');
 assert.ok(screens.includes('send:{width:42,height:42,minWidth:42,borderRadius:21,backgroundColor:"#2563eb"'),'send circle uses the web blue');
 assert.ok(screens.includes('[attachOpen,setAttachOpen]=useState(false)'),'plus toggle state must exist');
});
test('attachment options collapse behind the plus button without losing pending panels',()=>{
 const composer=src('ChatAttachmentComposer.tsx');
 assert.ok(composer.includes('optionsOpen=true'),'optionsOpen prop defaults open for other callers');
 assert.ok(composer.includes('{optionsOpen&&<View style={{flexDirection:"row",flexWrap:"wrap"}}>'),'photo/camera/pdf row is behind the toggle');
 assert.ok(composer.includes('if(!optionsOpen&&!file&&!pendingId&&!error&&!recoveryBlocked&&!uncertain&&!(busy||restoring))return null;'),'quiet closed state renders nothing, like the web room');
 // Pending/preview/error panels stay available while closed.
 assert.ok(composer.includes('{pendingId&&file&&<Text'),'pending attachment notice survives the collapse');
 assert.ok(composer.includes('{!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}'),'error text survives the collapse');
});
test('api maps a bare 404 Not Found to the shared server-route compatibility hint',()=>{
 const api=src('api.ts'),modern=src('modernApi.ts'),compatibility=src('apiCompatibility.ts');
 assert.ok(api.includes('rawDetail==="Not Found"'),'English FastAPI detail is detected');
 assert.ok(api.includes('MISSING_API_ROUTE_MESSAGE'),'primary API uses the shared hint');
 assert.ok(modern.includes('MISSING_API_ROUTE_MESSAGE'),'modern API uses the same hint');
 assert.ok(compatibility.includes('Sunucuda istenen API rotası bulunamadı (404)'),'users are told that the server route is missing');
 assert.ok(!compatibility.includes('uygulamayı güncelle'),'do not send users to update the app for a server route gap');
});
test('academic course create treats 404 as a definitive failure and unlocks the form',()=>{
 const academic=src('NativeAcademic.tsx');
 assert.ok(academic.includes("else if(status===404){void SecureStore.deleteItemAsync(createKey).catch(()=>{});setUncertain(null);setError('Sunucu ders oluşturma özelliğini desteklemiyor (404)"),'create 404 clears the uncertain lock with a clear message');
 assert.ok(academic.includes("else if(status===404){void SecureStore.deleteItemAsync(createKey).catch(()=>{});setUncertain(null);setError('Sunucuda bu istek için makbuz bulunamadı (404)"),'receipt-check 404 also unlocks');
 // Uncertainty is still kept for genuinely unknown outcomes.
 assert.ok(academic.includes('setUncertain(pending)}}}'),'unknown failures keep the idempotent uncertain flow');
});

test('missing attachment and receipt routes block retries while preserving the same pending intent',()=>{
 const composer=src('ChatAttachmentComposer.tsx');
 assert.ok(composer.includes('isMissingApiRoute404(receiptError)'),'restore must recognize a missing receipt route');
 assert.ok(composer.includes('isMissingApiRoute404(e)||isMissingApiRoute404(receiptFailure)'),'send and receipt failures must both recognize a missing route');
 assert.ok(composer.includes('setRecoveryBlocked(true)'),'missing routes must block a new attachment send');
 assert.ok(composer.includes('Bekleyen dosya ve aynı istek anahtarı güvenli alanda korunuyor'),'the same pending intent must remain available for post-deploy reconciliation');
 assert.ok(composer.includes('pendingMeta&&!file&&!recoveryBlocked'),'the ordinary retry notice must not appear when the server route is absent');
 assert.ok(composer.includes('Sunucu vaka eki gönderim/makbuz API rotasını desteklemiyor (404)'),'the clinician must see a server-side compatibility message');
});
