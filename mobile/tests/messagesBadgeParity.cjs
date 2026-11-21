const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const src=f=>fs.readFileSync(require.resolve('../src/'+f),'utf8');
const app=()=>fs.readFileSync(require.resolve('../App.tsx'),'utf8');
test('modernApi maps bare 404 Not Found to Turkish like api.ts',()=>{
 const modern=src('modernApi.ts');
 // Live probe 2026-11-21: POST /consultations/{id}/attachments -> 404 on dentalai.tr
 // (deployed mobile router predates the media route); the composer error showed raw
 // English "Not Found" because modernApi lacked api.ts's Turkish mapping.
 assert.ok(modern.includes('rawDetail==="Not Found"'),'modernApi must detect the bare FastAPI 404 detail');
 assert.ok(modern.includes('Sunucuda istenen kayıt bulunamadı (404)'),'the mapped message must match api.ts');
 assert.ok(modern.includes('Uygulama ile sunucu sürümü uyumsuz olabilir'),'the mapping must explain the version mismatch');
});
test('messages tab badge mirrors the web paintMessageBadge contract',()=>{
 const source=app(),modern=src('modernApi.ts');
 // Web base.html: /messages/unread-count -> {count}; badge hides under 1, caps at 99+,
 // bumps on incoming consultation messages, clears when the tab is opened.
 assert.ok(modern.includes('"/messages/unread-count"'),'mobile unread count must call the web-parity endpoint');
 assert.ok(source.includes('getMessagesUnreadCount(token)'),'the badge seeds from the unread endpoint');
 assert.ok(source.includes('tabBarBadge:msgUnread>0?(msgUnread>99?"99+":msgUnread):undefined'),'badge hides under 1 and caps at 99+ like paintMessageBadge');
 assert.ok(source.includes('backgroundColor:"#D92D20"'),'the badge is red like the web count bubble');
 assert.ok(source.includes('type==="MESSAGE_CREATED"&&Number(lastEvent.payload?.case_id||0)>0&&!messagesFocused.current'),'only consultation messages bump while the tab is closed');
 assert.ok(source.includes('onClear={()=>setMsgUnread(0)}'),'opening the tab clears the badge');
 assert.ok(app().includes('function MessagesTabScreen'),'the messages tab wraps consultations with focus tracking');
});
test('attachment preview is the compact web card, not a full-width image stack',()=>{
 const composer=src('ChatAttachmentComposer.tsx');
 // Web case room: attachmentPreview card = [attachmentThumb][attachmentName][× cancel]
 // with send as a compact primary action, never a stretched preview.
 assert.ok(composer.includes('accessibilityLabel="Seçimi kaldır"'),'the cancel control matches attachmentCancel (Dosyayı kaldır)');
 assert.ok(composer.includes('✎ Görseli düzenle'),'image annotate entry stays available');
 assert.ok(composer.includes('accessibilityLabel="Eki gönder"'),'send stays a labeled primary action');
 assert.ok(composer.includes('width:64,height:64,borderRadius:12'),'thumbnail is a compact square like the web card');
 assert.ok(composer.includes('numberOfLines={1}'),'long file names truncate inside the card');
 assert.ok(!composer.includes('resizeMode="contain" style={{height:130'),'the stretched 130px preview is gone');
 assert.ok(composer.includes('Seçilen ek bu görüşmeye gönderilecek.'),'user copy explains the pending attachment');
});
test('backend exposes the mobile unread route reusing the web counter',()=>{
 const backend=fs.readFileSync(require.resolve('../../app/mobile_modern_api_v3.py'),'utf8');
 const web=fs.readFileSync(require.resolve('../../app/main.py'),'utf8');
 assert.ok(backend.includes("@router.get('/messages/unread-count')"),'mobile v1 router must expose the web-parity unread route');
 assert.ok(backend.includes('_consultation_unread_total'),'it must reuse the web counter, not a second implementation');
 assert.ok(web.includes('def consultation_unread_count'), 'the web route stays the canonical source');
});
