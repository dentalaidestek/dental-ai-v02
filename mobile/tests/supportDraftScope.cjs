const ts=require("typescript");
const assert=require("node:assert/strict");
const {test}=require("node:test");
require.extensions[".ts"]=(m,f)=>m._compile(ts.transpileModule(require("node:fs").readFileSync(f,"utf8"),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,f);
const {
 supportCreateIntentStorageKey,
 supportReplyIntentStorageKey,
 isSupportPendingIntentForUser
}=require("../src/supportDraftScope.ts");

test("support create intents use a stable account-specific namespace",()=>{
 assert.equal(supportCreateIntentStorageKey(41),"dai.support.create.pending.v2.41");
 assert.notEqual(supportCreateIntentStorageKey(41),supportCreateIntentStorageKey(42));
 assert.throws(()=>supportCreateIntentStorageKey(0),/Geçersiz/);
 assert.throws(()=>supportCreateIntentStorageKey(Number.MAX_SAFE_INTEGER+1),/Geçersiz/);
});

test("support reply intents are scoped by both account and ticket",()=>{
 assert.equal(supportReplyIntentStorageKey(41,900),"dai.support.reply.pending.v2.41.900");
 assert.notEqual(supportReplyIntentStorageKey(41,900),supportReplyIntentStorageKey(42,900));
 assert.notEqual(supportReplyIntentStorageKey(41,900),supportReplyIntentStorageKey(41,901));
 assert.throws(()=>supportReplyIntentStorageKey(41,0),/Geçersiz/);
});

test("only versioned create intents owned by the current account are restored",()=>{
 const intent={version:2,user_id:41,kind:"CREATE",key:"support_m1abcde_12345678",subject:"Teknik destek",message:"Özel açıklama",case_id:null};
 assert.equal(isSupportPendingIntentForUser(intent,41,"CREATE"),true);
 assert.equal(isSupportPendingIntentForUser(intent,42,"CREATE"),false);
 assert.equal(isSupportPendingIntentForUser({...intent,version:1},41,"CREATE"),false);
 assert.equal(isSupportPendingIntentForUser({...intent,user_id:42},41,"CREATE"),false);
 assert.equal(isSupportPendingIntentForUser({...intent,key:"bad"},41,"CREATE"),false);
 assert.equal(isSupportPendingIntentForUser({...intent,subject:""},41,"CREATE"),false);
});

test("only the matching account and ticket can restore a reply intent",()=>{
 const intent={version:2,user_id:41,kind:"REPLY",ticket_id:900,key:"support_m1abcde_12345678",message:"Yanıt"};
 assert.equal(isSupportPendingIntentForUser(intent,41,"REPLY",900),true);
 assert.equal(isSupportPendingIntentForUser(intent,42,"REPLY",900),false);
 assert.equal(isSupportPendingIntentForUser(intent,41,"REPLY",901),false);
 assert.equal(isSupportPendingIntentForUser({...intent,ticket_id:901},41,"REPLY",900),false);
});
