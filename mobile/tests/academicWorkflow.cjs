const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const compile=file=>ts.transpileModule(fs.readFileSync(require.resolve(file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
function api(request=async()=>({})){const exports={};vm.runInNewContext(compile('../src/academicApi.ts'),{exports,require:()=>({request})});return exports}
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
function composerComponent(native){const exports={};vm.runInNewContext(compile('../src/NativeAcademicComposer.tsx'),{exports,require:n=>n==='react'?{...React,default:React}:native});return exports.default;}
const running={id:12,status:'RUNNING',stage:'Synthetic generation',question:'Synthetic question'};

test('academic cancellation uses the selected course and validates the run id',async()=>{const calls=[],a=api(async(...args)=>{calls.push(args);return{run:{...running,status:'CANCELLED',stage:'Kullanıcı tarafından iptal edildi',partial:'',error:'Bu çalışma iptal edildi.'}}});const result=await a.cancelRun('token',3,12);assert.equal(result.status,'CANCELLED');assert.equal(calls[0][0],'/academic/courses/3/runs/12/cancel');assert.equal(calls[0][1],'token');assert.equal(calls[0][2].method,'POST');await assert.rejects(a.cancelRun('token',3,0));});
test('academic file access rejects external and cross-course bearer destinations',()=>{const a=api();assert.equal(a.academicFilePath(1,'/notes/courses/1/ai/messages/2/pdf?part=1'),'/api/mobile/v1/academic/courses/1/messages/2/pdf?part=1');for(const p of ['https://evil.test','/api/mobile/v1/academic/courses/2/materials/1/file','/api/mobile/v1/academic/courses/1/materials/../file','/notes/courses/1/ai/messages/2/pdf?other=1'])assert.throws(()=>a.academicFilePath(1,p));});

const timelineItem=(id,overrides={})=>({id,role:'ASSISTANT',content:'Synthetic answer',created_at:'2026-11-19T10:00:00.000Z',quiz:null,quiz_stale:false,artifact:null,sources:[],vote:null,...overrides});
test('academic timeline validates bounded ordered pages and accepts nullable citation metadata',async()=>{
 const items=Array.from({length:50},(_,index)=>timelineItem(index+1));
 items[0]={...items[0],sources:[{title:null,page:null,page_start:null,page_end:null,url:null}]};
 const first=api(async path=>{assert.equal(path,'/academic/courses/3/timeline');return{items,next_before:1}});
 const page=await first.timeline('token',3);
 assert.equal(page.items.length,50);assert.equal(page.next_before,1);assert.equal(page.items[0].sources[0].title,null);
 const next=api(async path=>{assert.equal(path,'/academic/courses/3/timeline?before=60');return{items:Array.from({length:50},(_,index)=>timelineItem(index+10)),next_before:10}});
 assert.equal((await next.timeline('token',3,60)).next_before,10);
});
test('academic timeline rejects duplicate, unordered, oversized and cross-course records',async()=>{
 const valid=Array.from({length:50},(_,index)=>timelineItem(index+1));
 const cases=[
  valid.map((x,index)=>index===1?timelineItem(1):x),
  [...valid].reverse(),
  valid.map((x,index)=>index===0?{...x,content:'x'.repeat(500001)}:x),
  valid.map((x,index)=>index===0?{...x,created_at:'not-a-date'}:x),
  valid.map((x,index)=>index===0?{...x,artifact:{name:'private.pdf',url:'/api/mobile/v1/academic/courses/99/messages/12/pdf'}}:x),
  valid.map((x,index)=>index===0?{...x,quiz:{message_id:999,questions:[{number:1,stem:'Synthetic',options:['A','B','C','D','E'],result:null}]}}:x)
 ];
 for(const items of cases)await assert.rejects(api(async()=>({items,next_before:items[0]?.id??null})).timeline('token',3));
 await assert.rejects(api(async()=>({items:valid,next_before:0})).timeline('token',3));
});

const validWorkspace={course:{id:3,title:'Synthetic course',description:'Synthetic'},materials:[{id:2,name:'Synthetic.pdf',mime:'application/pdf',size:1024,index_status:'READY',url:'/api/mobile/v1/academic/courses/3/materials/2/file'}],max_file_bytes:157286400,max_upload_count:12,next_before:null};
test('academic library and workspace enforce descending bounded cursors and course-owned file paths',async()=>{
 const a=api(async path=>path.startsWith('/academic/library')?{items:[{id:4,title:'Synthetic course'}],next_before:null}:validWorkspace);
 assert.equal((await a.library('token')).items[0].id,4);
 assert.equal((await a.workspace('token',3)).materials[0].id,2);
 await assert.rejects(api(async()=>({items:[{id:4,title:'A'},{id:4,title:'B'}],next_before:null})).library('token'));
 await assert.rejects(api(async()=>({items:[{id:4,title:'A'}],next_before:4})).library('token'));
 await assert.rejects(api(async()=>({...validWorkspace,materials:[{...validWorkspace.materials[0],url:'/api/mobile/v1/academic/courses/9/materials/2/file'}]})).workspace('token',3));
 await assert.rejects(api(async()=>({...validWorkspace,max_file_bytes:500*1024*1024})).workspace('token',3));
 await assert.rejects(api(async()=>({...validWorkspace,next_before:2})).workspace('token',3));
});
test('academic quizzes, learning and indexed source pages reject malformed payloads',async()=>{
 const quiz={message_id:11,questions:[{number:1,stem:'Synthetic stem',options:['A','B','C','D','E'],result:null}]};
 const learning={learning:{practiced_facts:1,due_count:1,correct:1,wrong:0,weak_count:0,review:[{fact:'Synthetic fact',source:'Synthetic page 1',due:true,correct:1,wrong:0,needs_practice:false}]}};
 const source={filename:'Synthetic.pdf',page:2,status:'READY',ocr_text:'Synthetic OCR',chunks:[{id:7,title:null,text:'Synthetic chunk'}]};
 const a=api(async path=>path.endsWith('/quizzes')?{quizzes:[quiz]}:path.endsWith('/learning')?learning:source);
 assert.equal((await a.quizzes('token',3)).quizzes[0].message_id,11);
 assert.equal((await a.learning('token',3)).learning.review.length,1);
 assert.equal((await a.sourcePage('token',3,2,2)).chunks[0].title,null);
 await assert.rejects(api(async()=>({quizzes:[{...quiz,questions:[{...quiz.questions[0],number:0}]}]})).quizzes('token',3));
 await assert.rejects(api(async()=>({learning:{...learning.learning,review:[...learning.learning.review,...learning.learning.review,...learning.learning.review,...learning.learning.review,...learning.learning.review,...learning.learning.review,...learning.learning.review]}})).learning('token',3));
 await assert.rejects(api(async()=>({...source,page:3})).sourcePage('token',3,2,2));
 await assert.rejects(api(async()=>({...source,chunks:[{id:7,title:null,text:'x'.repeat(200001)}]})).sourcePage('token',3,2,2));
 await assert.rejects(api(async()=>({run:{...running,partial:{unexpected:true}}})).runStatus('token',3,12));
});
test('academic persisted intent is user and course bound and rejects malformed work',()=>{const a=api(),v={user:1,course:3,request_key:'synthetic-key-0001',message:'Synthetic question'};assert.equal(a.parseIntent(JSON.stringify(v),1,3).message,v.message);assert.throws(()=>a.parseIntent(JSON.stringify(v),2,3));assert.throws(()=>a.parseIntent(JSON.stringify(v),1,4));assert.throws(()=>a.parseIntent(JSON.stringify({...v,message:''}),1,3));assert.equal(a.validateRun({run:{...running,partial:null,error:null}}).id,12);assert.throws(()=>a.validateRun({run:{...running,status:'mystery'}}));});
function ui(overrides={},saved=null,timerApi={}){const exports={},calls=[],courseCalls=[],storage=new Map(),a=api();if(saved)storage.set('dai.academic.run.1.3',JSON.stringify(saved));const native={StyleSheet:{create:x=>x},Platform:{OS:'android'},Alert:{alert(){}},AppState:{currentState:'active',addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Image','KeyboardAvoidingView','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};native.FlatList=props=>React.createElement('FlatList',props,props.ListHeaderComponent,...props.data.map((item,index)=>React.createElement(React.Fragment,{key:index},props.renderItem({item,index}))),props.ListFooterComponent,props.data.length?null:props.ListEmptyComponent);
 const endpoint={...a,library:async()=>({items:[{id:3,title:'Synthetic course'}],next_before:null}),courseCreateReceipt:async()=>null,uploadReceipt:async()=>null,createCourse:async(_t,title,description,request_key)=>{courseCalls.push({title,description,request_key});return{course:{id:4,title,description},materials:[],max_file_bytes:157286400,max_upload_count:12,next_before:null}},workspace:async()=>({course:{id:3,title:'Synthetic course'},materials:[],max_file_bytes:157286400,max_upload_count:12,next_before:null}),timeline:async()=>({items:[],next_before:null}),quizzes:async()=>({quizzes:[]}),indexStatus:async()=>({ready:true,state:'ready',total:1,completed:1,files:[]}),learning:async()=>({learning:{practiced_facts:0,due_count:0,correct:0,wrong:0,weak_count:0,review:[]}}),activeRun:async()=>null,receipt:async()=>null,createRun:async(_t,_c,intent)=>{calls.push(intent);return running},...overrides};
 const secure={getItemAsync:async k=>storage.get(k)||null,setItemAsync:async(k,v)=>storage.set(k,v),deleteItemAsync:async k=>storage.delete(k)};
 vm.runInNewContext(compile('../src/NativeAcademic.tsx'),{exports,setTimeout:timerApi.setTimeout||setTimeout,clearTimeout:timerApi.clearTimeout||clearTimeout,AbortController,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{useIsFocused:()=>true}:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=> '00000000-0000-4000-8000-000000000001'}:n==='./socialDraft'?{chunkedDraftStore:()=>secure}:n==='./academicApi'?endpoint:n==='./NativeAcademicComposer'?{default:composerComponent(native)}:n==='expo-document-picker'?{getDocumentAsync:async()=>({canceled:true})}:n==='./nativeAcademicFiles'?{uploadAcademic:async()=>{},removeAcademicCacheFile:async()=>true}:{default:'NativeAcademicFile'}});return{Component:exports.default,calls,courseCalls,storage,endpoint};}
async function openLibrary(h){let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1})));return tree}
async function open(h){const tree=await openLibrary(h);const course=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)==='Synthetic course'));await renderer.act(async()=>course.props.onPress());return tree}
test('native academic starts a durable job once despite rapid double tap',async()=>{const h=ui(),tree=await open(h);await renderer.act(async()=>tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Akademik soru').props.onChangeText('Synthetic question'));await renderer.act(async()=>{const b=button(tree,'Gönder');b.props.onPress();b.props.onPress();await new Promise(r=>setImmediate(r))});assert.equal(h.calls.length,1);assert.equal(h.calls[0].message,'Synthetic question');assert.ok(text(tree.toJSON()).includes('RUNNING'));assert.equal(button(tree,'20 Soru Hazırla').props.disabled,true);await renderer.act(async()=>tree.unmount())});
test('uncertain study creation reuses persisted UUID and exact question after reopen',async()=>{const saved={user:1,course:3,request_key:'synthetic-existing-key',message:'Original synthetic question'},calls=[],h=ui({createRun:async(_t,_c,intent)=>{calls.push(intent);return running}},saved),tree=await open(h);await renderer.act(async()=>button(tree,'Aynı İsteği Doğrula / Sürdür').props.onPress());assert.equal(calls.length,1);assert.equal(calls[0].request_key,saved.request_key);assert.equal(calls[0].message,saved.message);assert.equal(h.storage.size,0);await renderer.act(async()=>tree.unmount())});
test('known server receipt restores the existing job without another generation',async()=>{const saved={user:1,course:3,request_key:'synthetic-existing-key',message:'Original synthetic question'},h=ui({receipt:async()=>running},saved),tree=await open(h);assert.equal(h.calls.length,0);assert.ok(text(tree.toJSON()).includes('RUNNING'));assert.equal(h.storage.size,0);await renderer.act(async()=>tree.unmount())});
test('source read failure blocks falsely acknowledged uncertain upload',async()=>{const h=ui(),tree=await open(h);h.storage.set('dai.academic.upload.1.3','Synthetic.pdf');h.endpoint.workspace=async()=>{throw Error('Synthetic network failure')};await renderer.act(async()=>button(tree,'Durumu Yenile').props.onPress());assert.ok(text(tree.toJSON()).includes('Synthetic network failure'));await renderer.act(async()=>tree.unmount())});
test('native quiz submits real numbering and locks answer after authoritative selection',async()=>{const q={message_id:11,questions:[{number:14,stem:'Synthetic stem',options:['A1','B2','C3','D4','E5'],result:null}]},calls=[],h=ui({timeline:async()=>({items:[{id:11,role:'ASSISTANT',content:'',created_at:'2030-01-01',quiz:q,sources:[]}],next_before:null}),quizzes:async()=>({quizzes:[q]}),answer:async(_t,_c,m,n,c)=>{calls.push([m,n,c]);q.questions[0].result={selected:c,correct:false,correct_choice:'B'};q.questions[0].rationale='Synthetic grounded explanation';return{quiz:q}}}),tree=await open(h);assert.ok(!text(tree.toJSON()).includes('Synthetic grounded explanation'));await renderer.act(async()=>tree.root.findAllByType('Pressable').find(n=>n.props.accessibilityRole==='radio').props.onPress());assert.deepEqual(calls,[[11,14,'A']]);assert.ok(text(tree.toJSON()).includes('Synthetic grounded explanation'));assert.equal(tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='radio').every(n=>n.props.disabled),true);await renderer.act(async()=>tree.unmount())});
test('native academic upload requires a matching server receipt before local cleanup',async()=>{const exports={},calls=[],deleted=[],key='synthetic-upload-key-0001',receipt={course_id:3,request_key:key,material_id:11,name:'Synthetic.pdf',mime:'application/pdf',size:1000,content_sha256:'a'.repeat(64),payload_hash:'b'.repeat(64),created_at:'2026-11-19T10:00:00Z'};const fsapi={cacheDirectory:'file:///cache/',getInfoAsync:async()=>({exists:true,size:1000}),deleteAsync:async(uri,options)=>deleted.push([uri,options]),FileSystemUploadType:{MULTIPART:1},createUploadTask:(...args)=>{calls.push(args);args[3]({totalBytesSent:500,totalBytesExpectedToSend:1000});return{uploadAsync:async()=>({status:200,body:JSON.stringify({ok:true,receipt})}),cancelAsync:async()=>{}}}};vm.runInNewContext(compile('../src/nativeAcademicFiles.ts'),{exports,setTimeout,clearTimeout,require:n=>n==='expo-file-system/legacy'?fsapi:n==='./api'?{ApiError:class extends Error{}}:n==='./sessionExpiry'?{revalidateSession:async()=>{}}:{validateAcademicUploadReceipt:(value,course,requestKey,name,size,mime)=>{assert.equal(course,3);assert.equal(requestKey,key);assert.equal(value.material_id,11);assert.equal(name,'Synthetic.pdf');assert.equal(size,1000);assert.equal(mime,'application/pdf');return value}}});const progress=[];const result=await exports.uploadAcademic('token',3,{uri:'file:///cache/academic/random.pdf',name:'Synthetic.pdf',mimeType:'application/pdf'},key,157286400,v=>progress.push(v));assert.equal(result.material_id,11);assert.equal(calls[0][2].parameters.original_filename,'Synthetic.pdf');assert.equal(calls[0][2].parameters.request_key,key);assert.equal(calls[0][2].headers.Cookie,'');assert.equal(calls[0][2].fieldName,'files');assert.equal(progress[0],.5);assert.deepEqual(deleted,[['file:///cache/academic/random.pdf',{idempotent:true}]])});
test('unreadable cross-account saved work blocks new paid generation',async()=>{const h=ui({}, {user:9,course:3,request_key:'synthetic-existing-key',message:'Other synthetic question'}),tree=await open(h);assert.equal(button(tree,'20 Soru Hazırla').props.disabled,true);assert.equal(h.calls.length,0);await renderer.act(async()=>tree.unmount())});
test('native upload deadline rejects even when platform cancel cannot settle upload',async()=>{let expire,cancelled=0;const exports={};const filesystem={cacheDirectory:'file:///cache/',getInfoAsync:async()=>({exists:true,size:1000}),FileSystemUploadType:{MULTIPART:1},createUploadTask:()=>({uploadAsync:()=>new Promise(()=>{}),cancelAsync:async()=>{cancelled++}})};vm.runInNewContext(compile('../src/nativeAcademicFiles.ts'),{exports,setTimeout:fn=>{expire=fn;return 1},clearTimeout(){},require:n=>n==='expo-file-system/legacy'?filesystem:n==='./api'?{ApiError:class extends Error{constructor(status,message){super(message);this.status=status}}:n==='./sessionExpiry'?{revalidateSession:async()=>{}}:{validateAcademicUploadReceipt:()=>({material_id:1})}});const pending=exports.uploadAcademic('A',3,{uri:'file:///cache/file.pdf',name:'Synthetic.pdf',mimeType:'application/pdf'},'synthetic-upload-key-0001',150000,()=>{});await new Promise(r=>setImmediate(r));expire();await assert.rejects(pending,/sonucu belirsiz/);assert.equal(cancelled,1)});
test('academic markdown renders native headings and horizontally scrollable tables',async()=>{const exports={},native=Object.fromEntries(['ScrollView','Text','View'].map(x=>[x,x]));native.StyleSheet={create:x=>x};vm.runInNewContext(compile('../src/NativeAnswerText.tsx'),{exports,require:n=>n==='react'?{...React,default:React}:native});let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{value:'# Synthetic heading\n| Source | Page |\n|---|---|\n| Notes | 2 |\n<!--ACADEMIC_Q_CURSOR:1:2-->'})));assert.equal(tree.root.findByType('ScrollView').props.horizontal,true);assert.ok(text(tree.toJSON()).includes('Synthetic heading'));assert.ok(!text(tree.toJSON()).includes('ACADEMIC'));await renderer.act(async()=>tree.unmount())});
test('leaving during receipt lookup preserves intent and does not start a later paid request',async()=>{let release;const pending=new Promise(r=>release=r),h=ui({receipt:async()=>pending}),tree=await open(h);await renderer.act(async()=>tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Akademik soru').props.onChangeText('Synthetic delayed question'));await renderer.act(async()=>{button(tree,'Gönder').props.onPress();await new Promise(r=>setImmediate(r))});await renderer.act(async()=>button(tree,'Derslerime Dön').props.onPress());await renderer.act(async()=>{release(null);await new Promise(r=>setImmediate(r))});assert.equal(h.calls.length,0);assert.ok(h.storage.has('dai.academic.run.1.3'));await renderer.act(async()=>tree.unmount())});


test('native Academic AI cancels only the active course run and shows the canonical result',async()=>{const calls=[],h=ui({activeRun:async()=>running,cancelRun:async(_t,c,id)=>{calls.push([c,id]);return{...running,status:'CANCELLED',stage:'Kullanıcı tarafından iptal edildi',partial:'',error:'Bu çalışma iptal edildi.'}}}),tree=await open(h);assert.ok(button(tree,'Bu işlemi durdur'));await renderer.act(async()=>{button(tree,'Bu işlemi durdur').props.onPress();await new Promise(r=>setImmediate(r))});assert.deepEqual(calls,[[3,12]]);assert.ok(text(tree.toJSON()).includes('CANCELLED'));assert.ok(!button(tree,'Bu işlemi durdur'));await renderer.act(async()=>tree.unmount())});

test('late RUNNING poll cannot overwrite a confirmed Academic AI cancellation',async()=>{let releaseStatus,markStarted;const pendingStatus=new Promise(r=>releaseStatus=r),started=new Promise(r=>markStarted=r),timers=[];let nextId=0;const timerApi={setTimeout(fn,delay){const item={id:++nextId,fn,delay,cancelled:false};timers.push(item);return item.id},clearTimeout(id){const item=timers.find(t=>t.id===id);if(item)item.cancelled=true}};const h=ui({activeRun:async()=>running,runStatus:async()=>{markStarted();return pendingStatus},cancelRun:async()=>({...running,status:'CANCELLED',stage:'Kullanıcı tarafından iptal edildi',partial:'',error:'Bu çalışma iptal edildi.'})},null,timerApi),tree=await open(h);await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});const timer=timers.find(t=>!t.cancelled&&t.delay===5000);assert.ok(timer,'foreground poll should be scheduled');await renderer.act(async()=>{timer.fn();await started});assert.ok(button(tree,'Bu işlemi durdur'));await renderer.act(async()=>{button(tree,'Bu işlemi durdur').props.onPress();await new Promise(r=>setImmediate(r))});releaseStatus(running);await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});assert.ok(text(tree.toJSON()).includes('CANCELLED'));assert.ok(!text(tree.toJSON()).includes('RUNNING'));await renderer.act(async()=>tree.unmount())});


test('lost cancel response reconciles a server-confirmed cancellation without a false error',async()=>{const cancelled={...running,status:'CANCELLED',stage:'Kullanıcı tarafından iptal edildi',partial:'',error:'Bu çalışma iptal edildi.'},h=ui({activeRun:async()=>running,cancelRun:async()=>{throw Error('Synthetic lost response')},runStatus:async()=>cancelled}),tree=await open(h);await renderer.act(async()=>{button(tree,'Bu işlemi durdur').props.onPress();await new Promise(r=>setImmediate(r))});assert.ok(text(tree.toJSON()).includes('CANCELLED'));assert.ok(!text(tree.toJSON()).includes('Synthetic lost response'));await renderer.act(async()=>tree.unmount())});


test('Academic chat composer stays outside the scrolling history and preserves drafts across tabs',async()=>{
 const h=ui(),tree=await open(h);
 const input=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Akademik soru');
 assert.ok(input);
 await renderer.act(async()=>input.props.onChangeText('Persistent synthetic draft'));
 let parent=input.parent,insideHistory=false;
 while(parent){if(parent.type==='FlatList')insideHistory=true;parent=parent.parent}
 assert.equal(insideHistory,false,'composer must be a sibling of the scrollable history');
 await renderer.act(async()=>button(tree,'Kaynaklar').props.onPress());
 assert.equal(tree.root.findAllByType('TextInput').some(n=>n.props.accessibilityLabel==='Akademik soru'),false);
 await renderer.act(async()=>button(tree,'Çalışma').props.onPress());
 const restored=tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Akademik soru');
 assert.equal(restored.props.value,'Persistent synthetic draft');
 await renderer.act(async()=>button(tree,'Sorular').props.onPress());
 assert.equal(tree.root.findAllByType('TextInput').some(n=>n.props.accessibilityLabel==='Akademik soru'),false);
 await renderer.act(async()=>tree.unmount());
});

test('Academic index polling follows active per-file work, not aggregate partial state',()=>{
 const a=api();
 const failedPartial={ready:true,complete:false,state:'partial',completed:1,total:2,files:[
  {id:1,filename:'ready.pdf',state:'ready',usable:true},
  {id:2,filename:'failed.pdf',state:'failed',message:'Synthetic failure'}
 ]};
 assert.equal(a.indexNeedsPolling(failedPartial),false,'a ready+failed partial index must not poll forever');
 assert.equal(a.indexNeedsPolling({...failedPartial,files:[failedPartial.files[0],{id:2,filename:'updating.pdf',state:'updating'}]}),true);
 assert.equal(a.indexNeedsPolling({...failedPartial,files:[{id:1,filename:'preparing.pdf',state:'preparing'}]}),true);
 assert.equal(a.indexNeedsPolling({...failedPartial,complete:true,state:'ready'}),false);
 assert.throws(()=>a.validateIndexStatus({...failedPartial,files:[]}),/doğrulanamadı/);
});

test('native Academic polling is foreground-only, idle-free and slower than active run polling for indexing',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeAcademic.tsx'),'utf8');
 assert.match(source,/A\.indexNeedsPolling\(index\)/);
 assert.match(source,/nextIndexAt=Date\.now\(\)\+15000/);
 assert.match(source,/\(!runBusy&&!indexPending\)/);
 assert.match(source,/runBusy\?5000:15000/);
 assert.match(source,/\[focused,foreground,ready,runBusy,indexPending\]/);
});


test('interrupted Academic run shows its safe checkpoint and retries only after an explicit action',async()=>{
 const interrupted={...running,status:'INTERRUPTED',partial:'Synthetic safe checkpoint',error:'Synthetic interruption'};
 const h=ui({activeRun:async()=>interrupted,runStatus:async()=>interrupted}),tree=await open(h);
 assert.ok(text(tree.toJSON()).includes('Synthetic safe checkpoint'));
 const retry=button(tree,'Aynı Soruyu Yeniden Dene');
 assert.ok(retry);
 assert.equal(h.calls.length,0,'restoring an interrupted run must never auto-charge a retry');
 await renderer.act(async()=>{retry.props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(h.calls.length,1);
 assert.equal(h.calls[0].message,interrupted.question);
 await renderer.act(async()=>tree.unmount());
});


test('Academic native entrypoints contain no TypeScript parser diagnostics',()=>{
 for(const file of ['../src/NativeAcademic.tsx','../src/academicApi.ts','../src/nativeAcademicFiles.ts']){
  const source=fs.readFileSync(require.resolve(file),'utf8');
  const result=ts.transpileModule(source,{fileName:file,reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}});
  const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).map(d=>ts.flattenDiagnosticMessageText(d.messageText,' '));
  assert.deepEqual(errors,[],file+': '+errors.join('; '));
 }
});

test('optional learning and quiz outages do not block the core Academic workspace',async()=>{
 const h=ui({
  learning:async()=>{throw Error('Synthetic learning endpoint outage')},
  quizzes:async()=>{throw Error('Synthetic quiz endpoint outage')}
 });
 const tree=await open(h);
 assert.equal(button(tree,'Gönder').props.disabled,false);
 assert.ok(button(tree,'Derslerime Dön'));
 assert.ok(text(tree.toJSON()).includes('Synthetic learning endpoint outage'));
 await renderer.act(async()=>tree.unmount());
});

test('index readiness outage leaves the course readable but prevents AI generation',async()=>{
 const h=ui({indexStatus:async()=>{throw Error('Synthetic index status outage')}});
 const tree=await open(h);
 assert.ok(button(tree,'Derslerime Dön'));
 assert.equal(button(tree,'Gönder').props.disabled,true);
 assert.ok(text(tree.toJSON()).includes('Synthetic index status outage'));
 await renderer.act(async()=>tree.unmount());
});

test('required workspace failure keeps Academic actions fail-closed',async()=>{
 const h=ui({timeline:async()=>{throw Error('Synthetic timeline outage')}});
 const tree=await open(h);
 assert.equal(button(tree,'Gönder').props.disabled,true);
 assert.ok(text(tree.toJSON()).includes('Synthetic timeline outage'));
 await renderer.act(async()=>tree.unmount());
});


test('course creation reconciliation selects only a new exact title and description match',()=>{
 const a=api(),intent={version:1,user:1,title:'Synthetic course',description:'Description',known_ids:[3,4]};
 const found=a.findCreatedCourse([
  {id:4,title:'Synthetic course',description:'Description'},
  {id:8,title:'Synthetic course',description:'Description'},
  {id:9,title:'Synthetic course',description:'Different'}
 ],intent);
 assert.equal(found.id,8);
 assert.equal(a.findCreatedCourse([{id:4,title:'Synthetic course',description:'Description'}],intent),null);
});

test('uncertain course creation cannot be manually unlocked into a duplicate create',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeAcademic.tsx'),'utf8');
 assert.ok(source.includes('A.findCreatedCourse(v.items,uncertain)'));
 assert.ok(source.includes('disabled={busy||!!uncertain'));
 assert.doesNotMatch(source,/Listeyi Kontrol Ettim; Yeni Oluşturmaya İzin Ver/);
});

test('Academic upload receipt binds the exact owner course request key and SHA-256 payload',()=>{
 const a=api(),key='synthetic-upload-key-0001',receipt={course_id:3,request_key:key,material_id:11,name:'lecture.pdf',mime:'application/pdf',size:100,content_sha256:'a'.repeat(64),payload_hash:'b'.repeat(64),created_at:'2026-11-19T10:00:00Z'};
 assert.equal(a.validateAcademicUploadReceipt(receipt,3,key).material_id,11);
 assert.throws(()=>a.validateAcademicUploadReceipt(receipt,4,key));
 assert.throws(()=>a.validateAcademicUploadReceipt(receipt,3,'synthetic-other-key-0001'));
 assert.throws(()=>a.validateAcademicUploadReceipt({...receipt,content_sha256:'bad'},3,key));
 assert.throws(()=>a.validateAcademicUploadReceipt({...receipt,name:'other.pdf'},3,key,'lecture.pdf'));
 assert.throws(()=>a.validateAcademicUploadReceipt({...receipt,size:101},3,key,'lecture.pdf',100));
});

test('persisted upload intent v2 is bound to the same account course and request key',()=>{
 const a=api(),value={version:2,user:1,course:3,name:'lecture.pdf',mime:'application/pdf',uri:'file:///cache/lecture.pdf',size:100,request_key:'synthetic-upload-key-0001'};
 assert.equal(a.parseUploadIntent(JSON.stringify(value),1,3).request_key,value.request_key);
 assert.throws(()=>a.parseUploadIntent(JSON.stringify(value),2,3));
 assert.throws(()=>a.parseUploadIntent(JSON.stringify(value),1,4));
 assert.throws(()=>a.parseUploadIntent(JSON.stringify({...value,request_key:'short'}),1,3));
 assert.throws(()=>a.parseUploadIntent(JSON.stringify({...value,mime:'image/png'}),1,3));
 assert.throws(()=>a.parseUploadIntent(JSON.stringify({...value,size:0}),1,3));
 assert.throws(()=>a.parseUploadIntent(JSON.stringify({...value,version:1}),1,3));
});

test('Academic upload recovery queries the exact receipt and never guesses by filename or size',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeAcademic.tsx'),'utf8');
 assert.ok(source.includes('A.uploadReceipt(token,course.id,pending.request_key)'));
 assert.ok(source.includes('reconcileUpload(uploadIntent)'));
 assert.ok(source.includes('pending.request_key,data.max_file_bytes'));
 assert.doesNotMatch(source,/findUploadedMaterial|uploadIntent\.known_ids/);
 assert.ok(source.includes('Aynı Anahtarla Güvenli Yeniden Dene'));
});

test('Academic upload receipt lookup is owner course and request-key scoped',async()=>{
 const key='synthetic-upload-key-0001',receipt={course_id:3,request_key:key,material_id:11,name:'lecture.pdf',mime:'application/pdf',size:100,content_sha256:'a'.repeat(64),payload_hash:'b'.repeat(64),created_at:'2026-11-19T10:00:00Z'},calls=[];
 const a=api(async(...args)=>{calls.push(args);return{receipt}});
 assert.equal((await a.uploadReceipt('token',3,key)).material_id,11);
 assert.equal(calls[0][0],'/academic/courses/3/materials/receipt?request_key='+encodeURIComponent(key));
 assert.equal(calls[0][1],'token');
 assert.equal(await api(async()=>({receipt:null})).uploadReceipt('token',3,key),null);
 await assert.rejects(api(async()=>({receipt:{...receipt,course_id:4}})).uploadReceipt('token',3,key));
});


test('persisted Academic course creation intent is account-bound',()=>{
 const a=api(),intent={version:1,user:1,title:'Synthetic course',description:'',known_ids:[3,4]};
 assert.equal(a.parseCourseCreateIntent(JSON.stringify(intent),1).title,intent.title);
 assert.throws(()=>a.parseCourseCreateIntent(JSON.stringify(intent),2));
 assert.throws(()=>a.parseCourseCreateIntent(JSON.stringify({...intent,known_ids:['3']}),1));
});

test('uncertain Academic course creation survives restart and opens only after a new matching server row',async()=>{
 const h=ui({
  library:async()=>({items:[],next_before:null}),
  createCourse:async()=>{throw Error('Synthetic lost create response')}
 });
 let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1})));
 await renderer.act(async()=>button(tree,'Yeni Ders').props.onPress());
 await renderer.act(async()=>tree.root.findAllByType('TextInput').find(n=>n.props.accessibilityLabel==='Ders adı').props.onChangeText('Recovered title'));
 await renderer.act(async()=>{button(tree,'Dersi Oluştur').props.onPress();await new Promise(r=>setImmediate(r))});
 const key='dai.academic.course-create.1';
 assert.ok(h.storage.has(key));
 assert.equal(button(tree,'Dersi Oluştur').props.disabled,true);
 await renderer.act(async()=>tree.unmount());

 let reopened;
 await renderer.act(async()=>reopened=renderer.create(React.createElement(h.Component,{token:'A',userId:1})));
 assert.ok(h.storage.has(key));
 assert.equal(button(reopened,'Dersi Oluştur').props.disabled,true);
 h.endpoint.library=async()=>({items:[{id:91,title:'Recovered title',description:''}],next_before:null});
 await renderer.act(async()=>{button(reopened,'Ders Listesini Yeniden Kontrol Et').props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(h.storage.has(key),false);
 await renderer.act(async()=>reopened.unmount());
});

test('native course creation persists a stable request key and retries the exact payload',async()=>{
 const calls=[];let attempts=0;
 const h=ui({
  createCourse:async(_t,title,description,key)=>{
   calls.push({title,description,key});
   if(attempts++===0)throw Error('Synthetic lost response');
   return{course:{id:4,title,description},materials:[],max_file_bytes:157286400,max_upload_count:12,next_before:null};
  },
  courseCreateReceipt:async()=>null
 });
 const tree=await openLibrary(h);
 await renderer.act(async()=>button(tree,'Yeni Ders').props.onPress());
 const fields=tree.root.findAllByType('TextInput');
 await renderer.act(async()=>fields.find(n=>n.props.placeholder==='Ders adı').props.onChangeText('Synthetic receipt course'));
 await renderer.act(async()=>fields.find(n=>n.props.placeholder==='Açıklama').props.onChangeText('Synthetic description'));
 await renderer.act(async()=>{button(tree,'Dersi Oluştur').props.onPress();await new Promise(r=>setImmediate(r))});
 const saved=JSON.parse(h.storage.get('dai.academic.course-create.1'));
 assert.equal(saved.version,2);
 assert.match(saved.request_key,/^[-_a-zA-Z0-9]{16,80}$/);
 assert.equal(calls.length,1);
 await renderer.act(async()=>{button(tree,'Aynı isteği güvenle yeniden dene').props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(calls.length,2);
 assert.deepEqual(calls[1],calls[0]);
 assert.equal(h.storage.has('dai.academic.course-create.1'),false);
 await renderer.act(async()=>tree.unmount());
});

test('native course creation resolves a lost response from the server receipt without another POST',async()=>{
 let committed=null,posts=0,receiptReads=0;
 const h=ui({
  createCourse:async(_t,title,description)=>{
   posts++;
   committed={course:{id:44,title,description},materials:[],max_file_bytes:157286400,max_upload_count:12,next_before:null};
   throw Error('Synthetic response lost after commit');
  },
  courseCreateReceipt:async()=>{receiptReads++;return committed}
 });
 const tree=await openLibrary(h);
 await renderer.act(async()=>button(tree,'Yeni Ders').props.onPress());
 const field=tree.root.findAllByType('TextInput').find(n=>n.props.placeholder==='Ders adı');
 await renderer.act(async()=>field.props.onChangeText('Synthetic committed course'));
 await renderer.act(async()=>{button(tree,'Dersi Oluştur').props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(posts,1);
 assert.ok(h.storage.has('dai.academic.course-create.1'));
 await renderer.act(async()=>{button(tree,'Sunucu kaydını doğrula').props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(receiptReads,1);
 assert.equal(posts,1);
 assert.equal(h.storage.has('dai.academic.course-create.1'),false);
 await renderer.act(async()=>tree.unmount());
});

test('course create intents accept legacy records but require a stable key for new records',()=>{
 const a=api(),legacy={version:1,user:1,title:'Synthetic legacy course',description:'',known_ids:[1]},current={version:2,user:1,title:'Synthetic new course',description:'',known_ids:[],request_key:'synthetic-course-key-0001'};
 assert.equal(a.parseCourseCreateIntent(JSON.stringify(legacy),1).version,1);
 assert.equal(a.parseCourseCreateIntent(JSON.stringify(current),1).request_key,current.request_key);
 assert.throws(()=>a.parseCourseCreateIntent(JSON.stringify({...current,request_key:undefined}),1));
 assert.throws(()=>a.parseCourseCreateIntent(JSON.stringify({...current,request_key:'short'}),1));
 assert.throws(()=>a.parseCourseCreateIntent(JSON.stringify(current),2));
});

test('course create client sends the key and receipt lookup stays on the private native route',async()=>{
 const calls=[],workspace={course:{id:9,title:'Synthetic course'},materials:[],max_file_bytes:157286400,max_upload_count:12,next_before:null};
 const a=api(async(...args)=>{calls.push(args);return calls.length===1?workspace:{workspace:null}});
 const created=await a.createCourse('private-token','Synthetic course','Synthetic description','synthetic-course-key-0001');
 assert.equal(created.course.id,9);
 assert.equal(calls[0][0],'/academic/library');
 assert.equal(calls[0][1],'private-token');
 assert.deepEqual(JSON.parse(calls[0][2].body),{title:'Synthetic course',description:'Synthetic description',request_key:'synthetic-course-key-0001'});
 assert.equal(await a.courseCreateReceipt('private-token','synthetic-course-key-0001'),null);
 assert.equal(calls[1][0],'/academic/library/receipt?request_key=synthetic-course-key-0001');
 assert.equal(calls[1][1],'private-token');
 await assert.rejects(a.courseCreateReceipt('private-token','short'));
 await assert.rejects(a.createCourse('private-token','Synthetic course','','short'));
 const malformed=api(async()=>({workspace:{course:{id:9,title:'Synthetic course'}}}));
 await assert.rejects(malformed.courseCreateReceipt('private-token','synthetic-course-key-0001'));
});

