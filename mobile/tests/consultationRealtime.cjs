const ts=require("typescript"),fs=require("node:fs"),assert=require("node:assert/strict"),{test}=require("node:test");
require.extensions[".ts"]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const {applyConsultationInboxEvent,applyConsultationChatEvent,mergeConsultationMessages}=require("../src/consultationRealtime.ts");
const row=(overrides={})=>({id:42,status:"ACTIVE",last_message:"Önceki",last_message_at:"2026-11-16T10:00:00",last_message_id:10,unread_count:2,...overrides});
const event=(event_type,payload,event_id=100)=>({event_type,payload,event_id,entity_id:payload.case_id});

test("incoming consultation message updates only its visible inbox row and unread count",()=>{
 const items=[row(),row({id:43,last_message_id:7})];
 const result=applyConsultationInboxEvent(items,event("MESSAGE_CREATED",{
  case_id:42,message_id:11,preview:"Yeni klinik mesaj",created_at:"2026-11-17T08:00:00",
  is_outgoing:false,case_status:"ACTIVE",
 }));
 assert.equal(result.changed,true);assert.equal(result.refresh,false);
 assert.equal(result.items[0].last_message,"Yeni klinik mesaj");
 assert.equal(result.items[0].last_message_id,11);assert.equal(result.items[0].unread_count,3);
 assert.equal(result.items[1],items[1]);
});

test("outgoing message updates preview without increasing unread count",()=>{
 const result=applyConsultationInboxEvent([row()],event("MESSAGE_CREATED",{
  case_id:42,message_id:11,preview:"Gönderildi",created_at:"2026-11-17T08:00:00",
  is_outgoing:true,case_status:"ACTIVE",
 }));
 assert.equal(result.items[0].unread_count,2);
 assert.equal(result.items[0].last_message_id,11);
});

test("duplicate and out-of-order message events cannot double increment unread count",()=>{
 const items=[row({last_message_id:12,unread_count:4})];
 const duplicate=applyConsultationInboxEvent(items,event("MESSAGE_CREATED",{
  case_id:42,message_id:12,preview:"Aynı",created_at:"2026-11-17T08:00:00",is_outgoing:false,
 }));
 const older=applyConsultationInboxEvent(items,event("MESSAGE_CREATED",{
  case_id:42,message_id:11,preview:"Eski",created_at:"2026-11-17T07:00:00",is_outgoing:false,
 }));
 assert.equal(duplicate.changed,false);assert.equal(older.changed,false);
 assert.equal(items[0].unread_count,4);
});

test("malformed message event requests one authoritative reconciliation",()=>{
 const result=applyConsultationInboxEvent([row()],event("MESSAGE_CREATED",{case_id:42,message_id:"bad"}));
 assert.equal(result.refresh,true);assert.equal(result.changed,false);
});

test("CASE_READ clears unread only for the account that marked the case read",()=>{
 const own=applyConsultationInboxEvent([row()],event("CASE_READ",{case_id:42,user_id:7,through_id:12}),7);
 const peer=applyConsultationInboxEvent([row()],event("CASE_READ",{case_id:42,user_id:8,through_id:12}),7);
 assert.equal(own.items[0].unread_count,0);
 assert.equal(peer.items[0].unread_count,2);
});

test("case creation requests a first-page refresh while status changes patch in place",()=>{
 const created=applyConsultationInboxEvent([row()],event("CASE_CREATED",{case_id:99}));
 const status=applyConsultationInboxEvent([row()],event("CASE_STATUS_UPDATED",{case_id:42,status:"EXPERT_COMPLETED"}));
 assert.equal(created.refresh,true);
 assert.equal(status.items[0].status,"EXPERT_COMPLETED");
 assert.equal(status.refresh,false);
});

test("chat status and peer read receipts update without replacing message history",()=>{
 const current={id:42,status:"ACTIVE",other_read_at:null};
 const status=applyConsultationChatEvent(current,event("CASE_STATUS_UPDATED",{
  case_id:42,status:"EXPERT_COMPLETED",completion_confirmation_deadline:"2026-11-18T10:00:00",
 }),42,7);
 const read=applyConsultationChatEvent(status,event("CASE_READ",{
  case_id:42,user_id:8,through_id:19,at:"2026-11-17T08:10:00",
 }),42,7);
 const ignored=applyConsultationChatEvent(read,event("CASE_READ",{
  case_id:42,user_id:7,through_id:20,at:"2026-11-17T08:11:00",
 }),42,7);
 assert.equal(status.status,"EXPERT_COMPLETED");
 assert.equal(read.other_read_at,"2026-11-17T08:10:00");
 assert.equal(ignored.other_read_at,read.other_read_at);
});

test("message merge is ascending and idempotent across socket, receipt and HTTP copies",()=>{
 const result=mergeConsultationMessages([{id:2,content:"İki"},{id:1,content:"Bir"}],[
  {id:2,content:"İki güncel"},{id:3,content:"Üç"},{id:3,content:"Üç"},
 ]);
 assert.deepEqual(result,[{id:1,content:"Bir"},{id:2,content:"İki güncel"},{id:3,content:"Üç"}]);
});

test("native consultation chat catches up only messages after its last verified ID",()=>{
 const source=fs.readFileSync(require.resolve("../src/ModernScreens.tsx"),"utf8");
 assert.ok(source.includes("getConsultationUpdates(token,id,cursor)"));
 assert.ok(source.includes('if(eventCase===id&&eventType==="MESSAGE_CREATED")'));
 assert.ok(source.includes("messageId>messageCursor.current)void catchUpMessages()"));
 assert.ok(source.includes("mergeConsultationMessages(previous.messages||[],page.messages||[])"));
});

test("consultation inbox applies message previews locally instead of reloading the first page per message",()=>{
 const source=fs.readFileSync(require.resolve("../src/ModernScreens.tsx"),"utf8");
 const start=source.indexOf("export function Consultations(");
 const end=source.indexOf("export function ConsultationChat(",start);
 const inbox=source.slice(start,end);
 assert.ok(inbox.includes("applyConsultationInboxEvent(data,lastEvent,userId)"));
 assert.equal(inbox.includes('if(type==="MESSAGE_CREATED"&&caseId){void load()}'),false);
});

test("consultation inbox receives authenticated user identity from both navigation entry points",()=>{
 const source=fs.readFileSync(require.resolve("../src/ModernScreens.tsx"),"utf8");
 const app=fs.readFileSync(require.resolve("../App.tsx"),"utf8");
 const start=source.indexOf("export function Consultations(");
 const end=source.indexOf("export function ConsultationChat(",start);
 const inbox=source.slice(start,end);
 assert.ok(inbox.includes("export function Consultations({token,userId,navigation}:{token:string;userId:number;navigation:any})"));
 assert.ok(inbox.includes("applyConsultationInboxEvent(data,lastEvent,userId)"));
 assert.ok(app.includes("<Consultations token={token} userId={user.id} navigation={navigation}/>"));
 assert.ok(app.includes("<Consultations token={token} userId={user.id} navigation={p.navigation}/>"));
});
