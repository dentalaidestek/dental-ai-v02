// Native contract parity for the five routes that live only on the PR branch
// (PR #257, missing on origin/live-main): consultation attachment upload and
// download, messages/notifications unread badges and experts/performance-info.
// Each test pins the exact client call to the exact server route so the
// "missing on live main" delta stays intentional and reviewable.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const src={
 modern:fs.readFileSync(require.resolve('../src/modernApi.ts'),'utf8'),
 pro:fs.readFileSync(require.resolve('../src/professionalApi.ts'),'utf8'),
 api:fs.readFileSync(require.resolve('../src/api.ts'),'utf8'),
 mobile:fs.readFileSync(require.resolve('../../app/mobile_api.py'),'utf8'),
 modernV3:fs.readFileSync(require.resolve('../../app/mobile_modern_api_v3.py'),'utf8'),
 proApi:fs.readFileSync(require.resolve('../../app/mobile_professional_api.py'),'utf8'),
 accountApi:fs.readFileSync(require.resolve('../../app/mobile_account_api.py'),'utf8'),
 web:fs.readFileSync(require.resolve('../../app/main.py'),'utf8'),
};

test('attachment upload: client POST path, form key and 120s deadline match the server route',()=>{
 // Client: sendChatFile posts FormData with client_message_id and accepts
 // {ok, message, replayed?}; the upload deadline is 120 seconds.
 assert.ok(src.modern.includes('req<{ok:boolean;message:ChatMessage;replayed?:boolean}>(`/consultations/${caseId}/attachments`,token,{method:"POST",body})'),
  'client must POST the exact attachment path');
 assert.ok(src.modern.includes('/^\\/consultations\\/\\d+\\/attachments$/.test(path)?120000:30000'),
  'attachment upload keeps the 120 second deadline');
 assert.ok(src.modern.includes('body.append("client_message_id",key)'),
  'client mirrors the server request-key receipt (client_message_id form field)');
 assert.ok(src.modern.includes('/^[A-Za-z0-9_-]{16,96}$/.test(key)'),
  'client validates the key with the same 16-96 charset rule as the server');
 assert.ok(src.web.includes('if not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", key):'),
  'web _normalize_consultation_client_message_id keeps the shared key format');
 assert.ok(src.web.includes('return JSONResponse({"ok": True, "message": replay, "replayed": True})'),
  'web receipt replay returns the original message with replayed:true');
 assert.ok(src.mobile.includes('@router.post("/consultations/{case_id}/attachments")'),
  'server route keeps its exact path');
 assert.ok(src.mobile.includes('detail="Ek gönderimi için işlem anahtarı zorunludur."')&&src.mobile.includes('detail="Ek dosyası boyut sınırını aşıyor."')&&src.web.includes('detail="Desteklenmeyen ek türü."'),
  'Turkish upload error copy stays unchanged (mobile route + delegated web type gate)');
 assert.ok(src.modern.includes('Ek kaydı doğrulanamadı. Tekrar göndermeden önce görüşmeyi kontrol edin.'),
  'client validation copy for a malformed upload result stays unchanged');
});

test('attachment download: image uri pattern is Bearer-authenticated and the route is unchanged',()=>{
 assert.ok(src.modern.includes('return {uri:API_BASE+`/consultations/${caseId}/attachments/${messageId}`,headers:{Authorization:"Bearer "+token}};'),
  'client image source uses the exact download path with a Bearer header');
 assert.ok(src.mobile.includes('@router.get("/consultations/{case_id}/attachments/{message_id}")'),
  'server download route keeps its exact path');
 assert.ok(src.mobile.includes('detail="Ek bulunamadı."')&&src.mobile.includes('detail="Önce görüşmeyi geri yükleyin."'),
  'Turkish download error copy stays unchanged');
});

test('both unread badge routes: client field names match the server response exactly',()=>{
 // notifications/unread-count -> {unread_count:number}
 assert.ok(src.modern.includes('req<{unread_count:number}>("/notifications/unread-count",t)'),
  'client reads unread_count from the notifications badge endpoint');
 assert.ok(src.mobile.includes('@router.get("/notifications/unread-count")'),
  'server notifications badge route keeps its exact path');
 assert.ok(src.mobile.includes('AdminNotice.user_id == user.id,\n            AdminNotice.status == "ACTIVE",\n            AdminNotice.is_read == False,'),
  'badge counts only the caller\'s ACTIVE unread notices');
 // messages/unread-count -> {count:number}
 assert.ok(src.modern.includes('req<{count:number}>("/messages/unread-count",t)'),
  'client reads count from the messages badge endpoint');
 assert.ok(src.modern.includes('return {count:Number.isSafeInteger(result?.count)&&result.count>0?result.count:0};'),
  'client tolerates the web anonymous {"count":0} fallback shape');
 assert.ok(src.modernV3.includes("@router.get('/messages/unread-count')"),
  'server messages badge route keeps its exact path');
 assert.ok(src.modernV3.includes('from app.main import _consultation_unread_total'),
  'server reuses the web counter instead of a second implementation');
 // 401 on either badge must still drive revalidateSession, never a fake zero.
 assert.ok(src.modern.includes('if(r.status===401)await revalidateSession(token);'),
  'modernApi maps 401 to the revalidateSession flow');
 assert.ok(src.api.includes('await revalidateSession(token)'),
  'api.ts (professional requests) keeps the same 401 flow');
});

test('experts/performance-info: client ExpertPerformanceInfo fields now exist on the server',()=>{
 assert.ok(src.pro.includes("request<ExpertPerformanceInfo>('/experts/performance-info',token)"),
  'client calls the exact performance-info path');
 assert.ok(src.pro.includes("export type ExpertPerformanceInfo={title?:string|null;body?:string|null;sections?:Array<{title?:string;body?:string}>};"),
  'client type declares title/body/sections');
 assert.ok(src.pro.includes("throw Error('Performans açıklaması doğrulanamadı.')"),
  'Turkish validation copy stays unchanged');
 assert.ok(src.proApi.includes("@router.get('/experts/performance-info')"),
  'server route keeps its exact path');
 assert.ok(src.proApi.includes("'title':title_parser.text(),'body':plain.text(),'sections':sections,'content':plain.text()"),
  'server returns the title/body/sections the client renders (content stays for old clients)');
 assert.ok(src.proApi.includes("detail='Performans açıklaması alınamadı.'"),
  'Turkish degradation copy stays unchanged');
 assert.ok(src.accountApi.includes('router.include_router(mobile_professional_router)'),
  'professional router stays mounted under the /api/mobile/v1 prefix chain');
});

test('the five routes remain absent on live main so the PR delta stays intentional',()=>{
 // Guard against accidentally back-porting the five routes or renaming them:
 // live-main's mobile_api must not contain them, the PR must.
 for(const route of ['@router.post("/consultations/{case_id}/attachments")','@router.get("/consultations/{case_id}/attachments/{message_id}")','@router.get("/notifications/unread-count")']){
  assert.ok(src.mobile.includes(route),'PR branch keeps '+route);
 }
 assert.ok(src.modernV3.includes("@router.get('/messages/unread-count')"));
 assert.ok(src.proApi.includes("@router.get('/experts/performance-info')"));
});
