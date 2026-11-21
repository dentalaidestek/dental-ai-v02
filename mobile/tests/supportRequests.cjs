const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

const root=path.join(__dirname,'..');
const api=fs.readFileSync(path.join(root,'src/modernApi.ts'),'utf8');
const screen=fs.readFileSync(path.join(root,'src/NativeSupportRequests.tsx'),'utf8');
const app=fs.readFileSync(path.join(root,'App.tsx'),'utf8');
const backend=fs.readFileSync(path.join(root,'../app/mobile_api.py'),'utf8');

test('native support client exposes authenticated list/create/detail/read/reply contracts',()=>{
 for(const name of ['getSupportTickets','createSupportTicket','getSupportTicket','markSupportTicketRead','replySupportTicket'])
  assert.match(api,new RegExp('export const '+name+'\\b'));
 for(const route of ['/support/tickets','/support/tickets/','/read','/reply'])
  assert.ok(api.includes(route),route);
});

test('native support screen implements status filters, empty state and retryable mutations',()=>{
 for(const label of ['Destek Taleplerim','Yeni destek talebi','Geçmiş talepler','Yanıtınızı bekliyor','Destek ekibinin yeni yanıtı bekleniyor'])
  assert.ok(screen.includes(label),label);
 assert.ok(screen.includes('createKey||'));
 assert.ok(screen.includes('replyKey||'));
 assert.ok(screen.includes('import * as SecureStore from "expo-secure-store"'));
 assert.ok(screen.includes('import{useRealtime}from"./realtime"'));
 assert.ok(screen.includes("SecureStore.setItemAsync(createPendingKey"));
 assert.ok(screen.includes("SecureStore.setItemAsync(storageKey"));
 assert.ok(screen.includes("SecureStore.getItemAsync(createPendingKey"));
 assert.ok(screen.includes("finally{if(isCurrent(owner))setSending(false)}"));
});

test('support screen is registered and reachable from the app',()=>{
 assert.ok(app.includes('import NativeSupportRequests from "./src/NativeSupportRequests"'));
 assert.ok(app.includes('name="SupportRequests"'));
 assert.ok(app.includes('nav.navigate("SupportRequests")'));
});

test('backend scopes ticket reads and writes to the authenticated owner',()=>{
 assert.match(backend,/SupportTicket\.user_id\s*==\s*user\.id/);
 // Ownership moved into the _mobile_support_ticket_owned helper (user_id parameter; also validates REPORT reporter ownership).
 assert.match(backend,/def _mobile_support_ticket_owned\(session: Session, ticket: SupportTicket, user_id: int\) -> bool:/);
 assert.match(backend,/if ticket\.user_id != user_id:/);
 assert.ok(backend.includes('if not ticket or not _mobile_support_ticket_owned(session, ticket, user.id):'),'detail/read/reply endpoints must use the owner helper');
 assert.match(backend,/SupportTicket\.source_type\s*==\s*"SUPPORT"/);
});

test('backend persists idempotency receipts and enforces one reply per support turn',()=>{
 assert.ok(backend.includes('class MobileSupportMutationReceipt(SQLModel, table=True)'));
 assert.ok(backend.includes('_support_mutation_replay'));
 assert.ok(backend.includes('_support_user_can_reply(session, ticket)'));
 assert.ok(backend.includes('with_for_update()'));
});

test('support mutation endpoints reject unauthenticated requests and oversized content',()=>{
 assert.ok(backend.includes('user: User = Depends(_mobile_user)'));
 assert.ok(backend.includes('len(subject) > 160'));
 assert.ok(backend.includes('len(message) > 4000'));
});

test('native support exposes optional expert conversation linking and persists its selection',()=>{
 assert.ok(api.includes('getSupportConversationOptions'));
 assert.ok(api.includes('case_id:caseId??null'));
 assert.ok(screen.includes('İlgili uzman konuşması (isteğe bağlı)'));
 assert.ok(screen.includes('case_id:caseId??null'));
 assert.ok(screen.includes('createSupportTicket(token,subject,message,key,caseId)'));
 assert.ok(screen.includes('Konuşma yalnızca destek ekibiyle ilişkilendirilir'));
});
test('native support exposes reports and cursor pagination for tickets and messages',()=>{
 assert.ok(api.includes('getSupportReports'));
 assert.ok(api.includes('getSupportTickets=async(t:string,before?:number)'));
 // 'before_id='+'before' was a literal-concat artifact; the intent is that the cursor is forwarded
 // from the `before` argument, which the client builds as "&before_id="+before / "?before_id="+before.
 assert.ok(api.includes('"&before_id="+before'));
 assert.ok(api.includes('"?before_id="+before'));
 assert.ok(screen.includes('Bildirimlerim'));
 assert.ok(screen.includes('Daha eski destek taleplerini yükle'));
 assert.ok(screen.includes('Daha eski mesajları yükle'));
 assert.ok(backend.includes('/support/reports'));
 assert.ok(backend.includes('/support/conversation-options'));
 assert.ok(backend.includes('next_before_id'));
});

test('support notifications open the exact ticket through the authenticated owner-scoped detail API',()=>{
 assert.match(screen,/initialTicketId\?:number/);
 assert.match(screen,/Number\.isSafeInteger\(initialTicketId\)/);
 assert.ok(screen.includes('void open(initialTicketId)'));
 assert.ok(screen.includes('getSupportTicket(token,id)'));
 assert.ok(app.includes('initialTicketId={route.params?.ticketId}'));
});

test('support recovery storage is isolated by account and ticket',()=>{
 const scopeSource=fs.readFileSync(path.join(root,'src/supportDraftScope.ts'),'utf8');
 const compiled=ts.transpileModule(scopeSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const scopeModule={exports:{}};
 vm.runInNewContext(compiled,{module:scopeModule,exports:scopeModule.exports});
 const scope=scopeModule.exports;
 const createA=scope.supportCreateIntentStorageKey(7),createB=scope.supportCreateIntentStorageKey(8);
 const replyA=scope.supportReplyIntentStorageKey(7,42),replyB=scope.supportReplyIntentStorageKey(8,42);
 const replyOtherTicket=scope.supportReplyIntentStorageKey(7,43);
 assert.notEqual(createA,createB);
 assert.notEqual(replyA,replyB);
 assert.notEqual(replyA,replyOtherTicket);
 assert.ok(!createA.includes('secret-token'));
 assert.throws(()=>scope.supportCreateIntentStorageKey(0),/Geçersiz/);
 assert.throws(()=>scope.supportReplyIntentStorageKey(7,-1),/Geçersiz/);
 const intent={version:2,user_id:7,kind:'CREATE',key:'support_m1abcde_12345678',subject:'Konu',message:'Özel destek metni',case_id:null};
 assert.equal(scope.isSupportPendingIntentForUser(intent,7,'CREATE'),true);
 assert.equal(scope.isSupportPendingIntentForUser(intent,8,'CREATE'),false);
 assert.equal(scope.isSupportPendingIntentForUser({...intent,user_id:8},7,'CREATE'),false);
 const reply={version:2,user_id:7,kind:'REPLY',ticket_id:42,key:'support_m1abcde_12345678',message:'Yanıt'};
 assert.equal(scope.isSupportPendingIntentForUser(reply,7,'REPLY',42),true);
 assert.equal(scope.isSupportPendingIntentForUser(reply,7,'REPLY',43),false);
});

test('support screen ignores legacy unscoped drafts and restores only versioned scoped intents',()=>{
 assert.ok(screen.includes('supportCreateIntentStorageKey(userId)'));
 assert.ok(screen.includes('supportReplyIntentStorageKey(userId,selected)'));
 assert.ok(screen.includes('isSupportPendingIntentForUser(d,userId,"CREATE")'));
 assert.ok(screen.includes('isSupportPendingIntentForUser(d,userId,"REPLY",selected)'));
 assert.equal(screen.includes('"dai.support.create.pending"'),false);
 assert.equal(screen.includes('"dai.support.reply.pending."+selected'),false);
 assert.ok(app.includes('userId={user.id}'));
});

test('support pending mutations cannot silently change payload under the same idempotency key',()=>{
 assert.ok(screen.includes('editable={!createKey}'));
 assert.ok(screen.includes('editable={!replyKey}'));
 assert.ok(screen.includes('Aynı talebi güvenle tekrar dene'));
 assert.ok(screen.includes('Aynı yanıtı güvenle tekrar dene'));
 assert.equal(screen.includes('setCreateKey("");void SecureStore.deleteItemAsync'),false);
 assert.equal(screen.includes('setReplyKey("");void SecureStore.deleteItemAsync'),false);
});

test('support list and detail ignore late responses from an old session or selected ticket',()=>{
 assert.ok(screen.includes('scopeRef.current=scope'));
 assert.ok(screen.includes('if(!isCurrent(owner)||request!==listRequest.current)return'));
 assert.ok(screen.includes('if(!isCurrent(owner)||request!==detailRequest.current||selectedRef.current!==id)return'));
 assert.ok(screen.includes('request===detailRequest.current&&selectedRef.current===id'));
});
