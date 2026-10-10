const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.join(__dirname,'../../app/templates/expert_case_room.html'),'utf8');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox'],headless:true});
 const page=await browser.newPage();
 await page.setContent('<div id="expertChat" data-user-id="1"><div id="msg-1" data-message-type="IMAGE"><img class="chat-clinical-image"><small>21:27 ✓✓ Okundu</small></div><div id="msg-2" data-message-type="TEXT"><a class="expert-reply-ref">Yanıtlanan mesaj</a><p>Kral merhaba &lt;img src=x onerror=alert(1)&gt;</p><small>21:28</small></div></div><div id="replyPreview"><span></span></div>');
 const result=await page.evaluate(source=>{
  let destroyed=false,suspended=false,lastMessageId=2;
  const pendingTextSends=new Map(),pendingMediaSends=new Map(),bindSwipe=()=>{},bindAnnotation=()=>{},scrollChatToBottom=()=>{};
  const chat=document.getElementById('expertChat'),currentReplyPreview=()=>document.getElementById('replyPreview'),sent=[];
  const socket={readyState:WebSocket.OPEN,send:value=>sent.push(JSON.parse(value))};
  let visibility='visible',focused=true;
  Object.defineProperty(document,'visibilityState',{get:()=>visibility,configurable:true});document.hasFocus=()=>focused;
  eval(source.slice(source.indexOf('function messagePreview('),source.indexOf('const currentComposerError'))+'\n'+source.slice(source.indexOf('function esc('),source.indexOf('function addMessage('))+'\n'+source.slice(source.indexOf('function addMessage('),source.indexOf('let caseRefreshTimer'))+'\n'+`
   updateReplyPreview(1);if(currentReplyPreview().querySelector('span').textContent!=='Görsel')throw Error('Image picked timestamp');
   if(!replyMarkup(1).includes('Görsel'))throw Error('Sent reply lost image label');
   const text=replyMarkup(2);if(!text.includes('Kral merhaba')||text.includes('<img'))throw Error('Reply content/XSS');
   visibility='hidden';markVisibleChatRead();if(sent.length)throw Error('Background marked read');
   visibility='visible';focused=false;markVisibleChatRead();if(sent.length)throw Error('Unfocused marked read');
   focused=true;suspended=true;markVisibleChatRead();if(sent.length)throw Error('Other screen marked read');
   suspended=false;markVisibleChatRead();markVisibleChatRead();if(sent.length!==1||sent[0].through_id!==2)throw Error('Cursor/dedup');
   addMessage({id:3,sender_user_id:1,message_type:'TEXT',content:'Reply',reply_to_message_id:1,created_at:'2026-10-09T18:00:00'});
   if(document.querySelector('#msg-3 .expert-reply-ref').textContent!=='↩ Görsel')throw Error('Confirmed message lost reply');
   addMessage({id:4,sender_user_id:1,message_type:'TEXT',content:'Reply',reply_to_message_id:2,created_at:'2026-10-09T18:00:00'});
   if(!document.querySelector('#msg-4 .expert-reply-ref').textContent.includes('Kral merhaba'))throw Error('Confirmed text lost reply');
   lastMessageId=3;visibility='hidden';markVisibleChatRead();visibility='visible';markVisibleChatRead();if(sent.length!==2||sent[1].through_id!==3)throw Error('Resume acknowledgement');
  `);
  return sent;
 },source);
 assert.equal(result.length,2);console.log('PASS: image/text reply, escaped content, hidden/unfocused/suspended reads, resume and cursor dedup');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
