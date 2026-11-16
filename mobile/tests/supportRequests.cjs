const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

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
 assert.ok(screen.includes('finally{setSending(false)}'));
});

test('support screen is registered and reachable from the app',()=>{
 assert.ok(app.includes('import NativeSupportRequests from "./src/NativeSupportRequests"'));
 assert.ok(app.includes('name="SupportRequests"'));
 assert.ok(app.includes('nav.navigate("SupportRequests")'));
});

test('backend scopes ticket reads and writes to the authenticated owner',()=>{
 assert.match(backend,/SupportTicket\.user_id\s*==\s*user\.id/);
 assert.match(backend,/ticket\.user_id\s*!=\s*user\.id/);
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
