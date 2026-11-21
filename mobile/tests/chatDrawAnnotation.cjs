const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const src=f=>fs.readFileSync(require.resolve('../src/'+f),'utf8');
test('chat image editor reproduces the web canvas annotation composite contract',()=>{
 const editor=src('NativeImageEditor.tsx');
 // Web: canvas composited over the image, exported as JPEG quality .9, file isaretlenmis-gorsel.jpg (expert_case_room.html buildEditedFile).
 assert.ok(editor.includes('name:"isaretlenmis-gorsel.jpg"'),'composite filename must match the web room');
 assert.ok(editor.includes('format:"jpg"')&&editor.includes('quality:.9'),'composite must be JPEG quality .9 like web toBlob(...,0.9)');
 assert.ok(editor.includes('captureRef'),'composite must snapshot the staged image+strokes like web canvas drawImage');
 assert.ok(editor.includes('↶ Geri al')&&editor.includes('⌫ Temizle'),'undo and clear tools match the web annotation dialog');
 assert.ok(editor.includes('Görseli Düzenle'),'editor title matches the web Görseli Düzenle dialog');
 assert.ok(editor.includes('useState("#ef4444")'),'default pen color matches the web color input value #ef4444');
 assert.ok(editor.includes('✎ Kalem'),'pen tool chip matches the web editor tools row');
 assert.ok(editor.includes('accessibilityLabel="Gönder"'),'send control matches the web image-editor-send Gönder');
 assert.ok(editor.includes('>Kapat</Text>'),'close control matches the web dialog Kapat');
 assert.ok(editor.includes('clampChatPoint'),'pen points are clamped to the image box');
 assert.ok(editor.includes('pointCount.current>=2000'),'pen stroke budget guards runaway input');
 assert.ok(editor.includes('Asıl görüntü korunur'),'user copy states the original image is preserved, like the web room');
});
test('web composite resolution cap matches EDITOR_MAX_DIMENSION 4096',()=>{
 const chat=src('chatFiles.ts');
 assert.ok(chat.includes('exportScale=Math.min(1,4096/Math.max(naturalWidth,naturalHeight))'),'export cap must equal the web 4096 EDITOR_MAX_DIMENSION');
});
test('case room opens the drawing editor from ✎ İşaretle and replies to the original image',()=>{
 const screens=src('ModernScreens.tsx');
 assert.ok(screens.includes('accessibilityLabel="Görüntüye işaretleme ekle" onPress={()=>setDrawMessage(item)}'),'✎ İşaretle must open the drawing editor like the web annotation-launch');
 assert.ok(screens.includes('source={chatImageSource(token,id,drawMessage.id)}'),'editor loads the same authorized image the room renders');
 assert.ok(screens.includes('onPrepared={file=>{setReplyTo(drawMessage.id);setPreparedAttachment({file,nonce:file.uri,scope:activeScope.current});setDrawMessage(null)}}'),'annotated composite is queued as a reply to the original image, like web sendAttachment replyId');
 assert.ok(screens.includes('import NativeImageEditor from "./NativeImageEditor";'),'editor component is wired into the room');
 // Note annotate stays available behind ✎ Not with the same delegated web endpoint.
 assert.ok(screens.includes('accessibilityLabel="Görüntüye not işaretleme ekle"'),'note annotate keeps a distinct entry');
 assert.ok(screens.includes('{action:"annotate",message_id:target.id,annotation_json}'),'note annotate still delegates to the web annotation message lifecycle');
 assert.ok(screens.includes('✎ İşaretle'),'primary annotate entry keeps the web label');
});
test('api reply contract keeps reply_to_message_id and the idempotency key for composites',()=>{
 const api=src('modernApi.ts');
 assert.ok(api.includes('body.append("reply_to_message_id",String(replyTo))'),'composite upload carries the web reply field');
 assert.ok(api.includes('body.append("client_message_id",key)'),'composite upload carries the idempotency key');
 assert.ok(api.includes('/^image\\/(jpeg|png|webp)$/.test(file.type)'),'JPEG composite passes the image type gate');
});
