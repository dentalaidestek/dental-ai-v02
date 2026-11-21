const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
// Evaluate transpiled CommonJS in THIS realm instead of a fresh vm context so
// returned arrays/objects share prototypes with assert.deepStrictEqual targets
// (cross-realm structural equals fail); require stubs are unchanged.
const loadModuleRealm=(code,exports,require=()=>{throw Error('unexpected require')})=>{vm.runInThisContext('(function(exports,require,module,__filename,__dirname){'+code+'\n})',{filename:'synthetic-module.js'})(exports,require,{exports},'synthetic-module.js','.')};
const tick=()=>new Promise(r=>setImmediate(r));
const sessionScopeSource=fs.readFileSync(require.resolve('../src/socialSessionScope.ts'),'utf8');
const sessionScopeCode=ts.transpileModule(sessionScopeSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const sessionScopeExports={};
loadModuleRealm(sessionScopeCode,sessionScopeExports);
function harness(){
 const state=[],alerts=[],refs=[],previous=[],effects=[],callbacks=[],requests=[],uploads=[],previews=[],posts=[],shared=[],opened=[],getPostCalls=[],getModerationCalls=[],storeValues=new Map();let cursor=0,ri=0,ei=0,ci=0,getPostResponse=null,moderationResponse=null;
 let getCommentsHandler=async()=>({items:[{id:20,text:'reply',author_name:'R',parent_id:10}],next_cursor:null});
 const store={getItemAsync:async k=>storeValues.get(k)||null,setItemAsync:async(k,v)=>storeValues.set(k,v),deleteItemAsync:async k=>storeValues.delete(k)};
 const picker={assets:[],options:null,requestMediaLibraryPermissionsAsync:async()=>({granted:true}),launchImageLibraryAsync:async options=>{picker.options=options;return {canceled:false,assets:picker.assets}}};
 const react={useState:initial=>{const id=cursor++;if(!(id in state))state[id]=typeof initial==='function'?initial():initial;return [state[id],v=>state[id]=typeof v==='function'?v(state[id]):v]},useRef:v=>{const i=ri++;return refs[i]||(refs[i]={current:v})},useEffect:(f,deps)=>{const i=ei++;if(!previous[i]||deps.some((v,j)=>!Object.is(v,previous[i].deps[j])))effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})},useCallback:(fn,deps)=>{const i=ci++;if(!callbacks[i]||deps.some((v,j)=>!Object.is(v,callbacks[i].deps[j])))callbacks[i]={deps,fn};return callbacks[i].fn},createElement:(type,props,...children)=>({type,props:{...props,children}})};react.default=react;
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8')+'\nexport const __test={PostCard,CommentThread,Comments,Composer};';
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,exports={};
 const native={Alert:{alert:(...args)=>alerts.push(args)},Share:{share:async options=>{shared.push(options);return {action:'sharedAction'}}},Linking:{openURL:async url=>opened.push(url)},Platform:{OS:'ios'},StyleSheet:{create:s=>s},Pressable:'Pressable',Text:'Text',View:'View',Image:'Image',ScrollView:'ScrollView',KeyboardAvoidingView:'KeyboardAvoidingView',Modal:'Modal',SafeAreaView:'SafeAreaView',ActivityIndicator:'ActivityIndicator',FlatList:'FlatList'};
 const api={getPost:async(_t,id)=>{getPostCalls.push([_t,id]);return getPostResponse||{id,author_id:1,author_name:'Expert',text:'Refreshed',status:'PUBLISHED',version:2,owned:true,pinned:false,comments_closed:false,liked:false,like_count:0,comment_count:0,media:[],created_at:'2026-11-17T13:20:00Z'}},getPostModerationStatus:async(_t,id)=>{getModerationCalls.push([_t,id]);return moderationResponse||{target_type:'POST',target_id:id,status:'PUBLISHED',version:2,moderation:{registered:true,content_version:2,revision:2,state:'HUMAN_DONE',wait_type:'NONE',reasons:[],reason:'Otomatik kontrol tamamlandı.',retryable:false}}},getComments:async(...args)=>{requests.push(args);return getCommentsHandler(...args)},setFollow:async(_t,_id,followed)=>({following_by_viewer:followed}),socialPostUrl:(authorId,postId)=>'https://dentalai.tr/expert-support/expert/'+authorId+'?post='+postId,socialImageSource:(url,token)=>({uri:url,headers:{Authorization:'Bearer '+token}}),uploadSocialImage:async(_token,file)=>{uploads.push(file);return {id:uploads.length,url:'/api/expert-social/media/'+uploads.length}},getLinkPreview:async(_token,url)=>{previews.push(url);return {available:true,id:77,url,domain:'example.org',site_name:'Example',title:'Example title',description:'Safe preview',cover:{id:81,url:'/api/expert-social/media/81'}}},createPost:async(_token,payload)=>{posts.push(payload);return {id:90,author_id:1,author_name:'Expert',text:payload.text,status:'PUBLISHED',version:1,owned:true,pinned:false,comments_closed:false,liked:false,like_count:0,comment_count:0,media:[],created_at:'2026-11-17'}}};
 const draftModule={chunkedDraftStore:()=>store,draftKey:(userId,scope)=>userId+':'+scope,readDraft:async(s,key)=>{const value=await s.getItemAsync(key);return value?JSON.parse(value):null},submitDraft:async(s,key,draft,send)=>{const intent={...draft,attempted:true};await s.setItemAsync(key,JSON.stringify(intent));const result=await send(intent);await s.deleteItemAsync(key);return result}};
 loadModuleRealm(code,exports,n=>n==='react'?react:n==='react-native'?native:n==='react-native-safe-area-context'?{SafeAreaView:'SafeAreaView'}:n==='./socialApi'?api:n==='./socialDraft'?draftModule:n==='expo-secure-store'?store:n==='expo-image-picker'?picker:n==='expo-crypto'?{randomUUID:()=> 'synthetic-id'}:n==='./socialSessionScope'?sessionScopeExports:{}); return {alerts,refs,requests,shared,opened,uploads,previews,posts,picker,storeValues,getPostCalls,getModerationCalls,sessionScope:sessionScopeExports,api,setGetPostResponse:value=>getPostResponse=value,setModerationResponse:value=>moderationResponse=value,setGetCommentsHandler:fn=>{getCommentsHandler=fn},render:(name,props)=>{cursor=ri=ei=ci=0;const tree=exports.__test[name](props);while(effects.length)effects.shift()();return tree}};
}
function nodes(tree){if(!tree||typeof tree!=='object')return [];const out=[tree];if(typeof tree.type==='function'){try{const rendered=tree.type({...tree.props,children:tree.props?.children});out.push(...nodes(rendered))}catch{}}for(const c of (tree.props?.children||[]).flat(Infinity))out.push(...nodes(c));return out;}
const text=n=>typeof n==='string'?n:!n||typeof n!=='object'?'':(n.props?.children||[]).flat(Infinity).map(text).join('');
test('Android owner menu exposes every action without an Alert exceeding three buttons',()=>{
 const h=harness(),props={token:'synthetic',post:{id:1,author_id:1,author_name:'Expert',text:'Science',media:[],status:'PUBLISHED',owned:true,created_at:'2026-11-10'},onEdit(){}};
 let tree=h.render('PostCard',props);nodes(tree).find(n=>n.props?.accessibilityLabel==='Gönderi işlemleri').props.onPress();
 assert.ok(h.alerts.every(a=>!a[2]||a[2].length<=3),'Android truncates Alert buttons after three');
 tree=h.render('PostCard',props);const sheet=nodes(tree).find(n=>n.props?.title==='Gönderi işlemleri');assert.ok(sheet,'native action sheet opens');
 const labels=nodes(sheet).map(n=>n.props?.title);for(const label of ['Düzenle','Sabitle','Yorumları kapat','Sil'])assert.ok(labels.includes(label),label);
});
test('published Dental Flow cards follow the author and share a canonical post URL',async()=>{
 const h=harness(),followed=[],supported=[];
 const post={id:42,author_id:7,author_name:'Synthetic expert',text:'Synthetic post',media:[],status:'PUBLISHED',owned:false,author_followed:false,author_support_available:true,comments_closed:false,liked:false,like_count:0,comment_count:0,created_at:'2026-11-17'};
 const props={token:'synthetic',userId:2,post,showExpertActions:true,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow:async(...args)=>{followed.push(args);return true},onSupport:()=>supported.push(true)};
 let tree=h.render('PostCard',props);
 const follow=nodes(tree).find(n=>n.props?.accessibilityLabel==='Takip et');assert.ok(follow);
 await follow.props.onPress();await tick();assert.deepEqual(followed,[[7,true]]);
 tree=h.render('PostCard',{...props,post:{...post,author_followed:true}});
 const support=nodes(tree).find(n=>n.props?.accessibilityLabel==='Uzmandan Destek Al');assert.ok(support);support.props.onPress();assert.deepEqual(supported,[true]);
 const share=nodes(tree).find(n=>n.props?.accessibilityLabel==='Gönderi bağlantısını paylaş');assert.ok(share);
 await share.props.onPress();assert.deepEqual(h.shared[0],{message:'https://dentalai.tr/expert-support/expert/7?post=42',url:'https://dentalai.tr/expert-support/expert/7?post=42'});
});

test('owner pending Dental Flow post refreshes only the minimal moderation receipt',async()=>{
 const h=harness(),updates=[],post={id:12,author_id:1,author_name:'Expert',author_specialty:'Ortodonti',text:'Pending',media:[],status:'PENDING',version:1,owned:true,comments_closed:false,liked:false,like_count:0,comment_count:0,created_at:'2026-11-17T13:20:00Z',moderation:{registered:true,content_version:1,revision:1,state:'WAITING_HUMAN',wait_type:'HUMAN_REVIEW',reasons:['IMAGE_REVIEW'],reason:'Görsel yönetici incelemesi bekliyor.',retryable:false}};
 h.setModerationResponse({target_type:'POST',target_id:12,status:'PUBLISHED',version:2,moderation:{...post.moderation,state:'HUMAN_DONE',wait_type:'NONE',reason:'Otomatik kontrol tamamlandı.'}});
 const tree=h.render('PostCard',{token:'synthetic',userId:1,post,showExpertActions:false,onUpdate:p=>updates.push(p),onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow(){},onSupport(){}});
 assert.ok(text(tree).includes('Görsel yönetici incelemesi bekliyor'));
 assert.ok(text(tree).includes('İnceleme bekliyor'));
 const refresh=nodes(tree).find(n=>n.props?.accessibilityLabel==='Yayın durumunu yenile');
 assert.ok(refresh,'owner can refresh the authoritative moderation result');
 await refresh.props.onPress();await tick();
 assert.deepEqual(h.getModerationCalls,[['synthetic',12]]);
 assert.deepEqual(h.getPostCalls,[],'status refresh must not download post text or media');
 assert.equal(updates[0].status,'PUBLISHED');
 assert.equal(updates[0].author_specialty,'Ortodonti','refresh must preserve feed presentation metadata');
});

test('published Dental Flow cards show verified expert, specialty and full timestamp together',()=>{
 const h=harness(),post={id:13,author_id:7,author_name:'Verified expert',author_specialty:'Endodonti',text:'Post',media:[],status:'PUBLISHED',owned:false,comments_closed:false,liked:false,like_count:0,comment_count:0,created_at:'2026-11-17T13:20:00Z'};
 const tree=h.render('PostCard',{token:'synthetic',userId:2,post,showExpertActions:true,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow(){},onSupport(){}});
 const expected=new Date(post.created_at).toLocaleString('tr-TR',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
 assert.ok(text(tree).includes('Mesleki belgesi doğrulanmış'));
 assert.ok(text(tree).includes('Endodonti'));
 assert.ok(text(tree).includes(expected),'specialty must not replace the web-equivalent date/time');
});

test('exhausted moderation failure escalates instead of promising an automatic retry',()=>{
 const h=harness(),post={id:14,author_id:1,author_name:'Expert',text:'Pending',media:[],status:'PENDING',version:3,owned:true,comments_closed:false,liked:false,like_count:0,comment_count:0,created_at:'2026-11-17T13:20:00Z',moderation:{registered:true,content_version:3,revision:4,state:'FAILED',wait_type:'RETRY_EXHAUSTED',reasons:['MODERATION_UNAVAILABLE'],reason:'Otomatik kontrol tamamlanamadı; yönetici müdahalesi gerekiyor.',retryable:false}};
 const tree=h.render('PostCard',{token:'synthetic',userId:1,post,showExpertActions:false,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow(){},onSupport(){}});
 assert.ok(text(tree).includes('Yönetici müdahalesi gerekiyor'));
 assert.equal(text(tree).includes('Otomatik kontrol yeniden denenecek'),false);
});

test('pending posts disable like/share and closed comments are not opened',()=>{
 const h=harness(),post={id:3,author_id:7,author_name:'Expert',text:'Pending',media:[],status:'PENDING',owned:true,comments_closed:true,liked:false,like_count:0,comment_count:0,created_at:'2026-11-17'};
 const tree=h.render('PostCard',{token:'synthetic',userId:2,post,showExpertActions:true,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow(){},onSupport(){}});
 const like=nodes(tree).find(n=>n.props?.accessibilityLabel==='Beğen');
 const share=nodes(tree).find(n=>n.props?.accessibilityLabel==='Gönderi bağlantısını paylaş');
 assert.equal(like.props.disabled,true);assert.equal(share.props.disabled,true);
 assert.ok(text(tree).includes('Yorumlar kapalı'));
 assert.equal(nodes(tree).some(n=>n.props?.accessibilityLabel?.startsWith('Yorumlar ')),false);
 const profileTree=h.render('PostCard',{token:'synthetic',userId:2,post:{...post,status:'PUBLISHED'},showExpertActions:false,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow(){},onSupport(){}});
 assert.equal(text(profileTree).includes('Uzman profili'),false);
});

test('Dental Flow native filters use the web taxonomy and reset the paged scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const feed=source.slice(source.indexOf('export function DentalFlow('),source.indexOf('const s = StyleSheet.create'));
 assert.match(feed,/api\.getFeed\(token, mode, before, selectedSpecialty\)/);
 assert.ok(feed.includes('selectedSpecialty}'));
 assert.ok(feed.includes('if (before === undefined) setSpecialties(p.specialties)'));
 assert.ok(feed.includes('Branş filtresi:'));
 assert.match(feed,/specialties\.map\(\(specialty\)/);
 assert.match(feed,/navigation\.navigate\("ExpertDirectory"\)/);
 assert.match(feed,/expertId === user.id && canCompose/,'the feed composer is restricted to an owned profile with server-confirmed publish permission');
 assert.doesNotMatch(feed,/!expertId \|\| expertId === user\.id/,'ordinary members must not see a composer that the API rejects');

 assert.match(feed,/mode === "following" && !followed/);
 assert.match(feed,/feedFollowLocks\.current\.has\(authorId\)/);
 assert.match(feed,/await api\.setFollow\(token, authorId, followed\)/);
 assert.match(feed,/feedFollowLocks\.current\.delete\(authorId\)/);
 const card=source.slice(source.indexOf('function PostCard('),source.indexOf('function Comments('));
 assert.doesNotMatch(card,/api\.setFollow/);
});

test('composer cannot unmount a pending upload or submission and overwrite a newer draft',async()=>{
 const h=harness();let closed=0;const props={token:'synthetic',userId:1,onClose:()=>closed++,onPosted(){}};
 let tree=h.render('Composer',props);await tick();tree=h.render('Composer',props);
 h.refs.at(-1).current=true;tree.props.onClose();assert.equal(closed,0);
 h.refs.at(-1).current=false;tree.props.onClose();assert.equal(closed,1);
});
test('reply threads start collapsed and refresh their exhausted cache when reply count changes',async()=>{
 const h=harness(),props={token:'synthetic',item:{id:10,author_name:'A',text:'root',parent_id:null,reply_count:1},postId:1,onChange(){},onReply(){},onProfile(){}};
 let tree=h.render('CommentThread',props);assert.equal(h.requests.length,0);
 let toggle=nodes(tree).find(n=>n.type==='Pressable'&&text(n)==='1 yanıtı aç');await toggle.props.onPress();await tick();tree=h.render('CommentThread',props);assert.equal(h.requests.length,1);assert.ok(text(tree).includes('Yanıtları kapat'));
 h.render('CommentThread',{...props,item:{...props.item,reply_count:2}});tree=h.render('CommentThread',{...props,item:{...props.item,reply_count:2}});
 toggle=nodes(tree).find(n=>n.type==='Pressable'&&text(n)==='2 yanıtı aç');assert.ok(toggle);await toggle.props.onPress();await tick();assert.equal(h.requests.length,2);assert.equal(h.requests[1][2],0);
});

test('clinical media gallery prevents stale account mutations and pagination overlap',()=>{
 // The duplicate ModernScreens gallery was removed in 2cfb204f and patientMediaRoute.cjs forbids restoring it;
 // these protections are asserted against the canonical native archive (NativePatientMedia.tsx).
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.ok(source.includes('const mounted=useRef(true)'), 'mounted state must be tracked');
 assert.ok(source.includes('const sequence=++request.current'), 'refresh generations invalidate stale requests');
 assert.ok(source.includes('picker!==pickerGeneration.current'), 'patient switch must cancel pending media picker');
 assert.ok(source.includes('if(loadLock.current){if(!more&&current())refreshPending.current=true;return;}'), 'refreshes must queue instead of overlapping an active page');
 assert.ok(source.includes('if(refreshPending.current&&!mutation.current)'), 'queued refresh runs after the active page and mutation');
 assert.ok(source.includes('if(!current())return;'), 'old account must not update gallery after upload');
 assert.ok(source.includes('if(!current()||sequence!==request.current)return;'), 'old page must not overwrite current patient');
});

test('patient detail never renders stale clinical data after account or patient change',()=>{
 const source=fs.readFileSync(require.resolve('../App.tsx'),'utf8');
 const screen=source.slice(source.indexOf('function PatientDetailScreen('),source.indexOf('function PatientStack('));
 const profile=fs.readFileSync(require.resolve('../src/NativePatientProfile.tsx'),'utf8');
 assert.ok(source.includes('import useSessionRenderKey from \"./src/useSessionRenderKey\";'),'patient navigation must use the opaque session-key hook');
 assert.ok(screen.includes('const profileRenderKey=useSessionRenderKey(`${token}:${userId}:${id}`);'),'account and patient changes must rotate the private render scope');
 assert.ok(screen.includes('NativePatientProfile key={profileRenderKey}'),'navigation must remount the patient boundary without exposing the bearer token');
 assert.ok(profile.includes('if(owner.current!==scope){owner.current=scope;request.current++;}'),'scope changes synchronously invalidate requests');
 assert.ok(profile.includes('if(!current()||seq!==request.current)return false'),'stale requests cannot commit');
 assert.ok(profile.includes('if(!detail||loadedScope!==scope)'),'hide previous patient before effects');
 assert.ok(profile.includes('mounted.current=false;request.current++'),'unmount invalidates pending requests');
});

test('clinical gallery hides old patient thumbnails and preview before effects run',()=>{
 // Canonical gallery lives in NativePatientMedia.tsx (ModernScreens copy removed in 2cfb204f).
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/const visibleItems=loadedOwner===owner\?items:\[\]/,'thumbnails from another account stay hidden');
 assert.match(source,/data=\{visibleItems\}/,'only owner-visible items are rendered');
 assert.match(source,/visible=\{open&&loadedOwner===owner\}/,'the preview modal cannot show another patient');
 assert.match(source,/setPreview\(null\)/,'preview resets when the owner scope changes');
 assert.match(source,/setLoadedOwner\(owner\)/,'each committed page is stamped with the requesting owner');
});

test('clinical gallery ignores pending page responses from another account before effects run',()=>{
 // Canonical gallery lives in NativePatientMedia.tsx (ModernScreens copy removed in 2cfb204f).
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/const sequence=\+\+request\.current/,'each page request snapshots the current generation');
 assert.match(source,/if\(!current\(\)\|\|sequence!==request\.current\)return;/,'stale owner or generation cannot commit');
 assert.match(source,/setLoadedOwner\(owner\)/,'pages are stamped with the requesting owner');
 assert.match(source,/more&&\(mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)/,'pagination never appends across owners');
 assert.match(source,/setCursor\(page\.next_before\)/,'the cursor belongs to the committed page only');
});

test('expert directory does not display previous account results while new account loads',()=>{
 const source=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
 const directory=source.slice(source.indexOf('export function ExpertDirectory('),source.indexOf('export function ',source.indexOf('export function ExpertDirectory(')+20));
 assert.match(directory,/activeToken\.current!==token/);
 assert.match(directory,/seq\.current\+\+/);
 assert.match(directory,/accountToken:token/);
 assert.match(directory,/data=\{data\?\.accountToken===token\?data\.items:\[\]\}/);
 assert.match(directory,/request===seq\.current&&activeToken\.current===token/);
});

test('consultation messages cannot display or overwrite another account or case',()=>{
 const source=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
 const chat=source.slice(source.indexOf('export function ConsultationChat('),source.indexOf('export function Academic('));
 assert.match(chat,/activeScope\.current=token\+":"\+userId\+":"\+id/);
 assert.match(chat,/visibleData=data\?\.accountScope===activeScope\.current\?data:null/);
 assert.match(chat,/request===requestSeq\.current&&scope===activeScope\.current/);
 assert.match(chat,/data=\{visibleData\?\.messages\|\|\[\]\}/);
 assert.match(chat,/return\(\)=>\{requestSeq\.current\+\+;sending\.current=false\}/);
});

test('Dental Flow native composer selects up to four images and persists each completed upload',async()=>{
 const h=harness(),props={token:'synthetic',userId:1,onClose(){},onPosted(){}};
 h.picker.assets=[
  {uri:'file:///one.png',fileName:'one.png',mimeType:'image/png',fileSize:1200},
  {uri:'file:///two.webp',fileName:'two.webp',mimeType:'image/webp',fileSize:1400},
  {uri:'file:///large.jpg',fileName:'large.jpg',mimeType:'image/jpeg',fileSize:9*1024*1024},
 ];
 let tree=h.render('Composer',props);await tick();tree=h.render('Composer',props);
 const add=nodes(tree).find(n=>text(n)==='Fotoğraf ekle');assert.ok(add);
 await add.props.onPress();await tick();tree=h.render('Composer',props);
 assert.equal(h.picker.options.allowsMultipleSelection,true);
 assert.equal(h.picker.options.selectionLimit,4);
 assert.deepEqual(h.uploads.map(x=>x.name),['one.png','two.webp']);
 assert.deepEqual(JSON.parse(h.storeValues.get('1:post')).media_ids,[1,2]);
 assert.ok(text(tree).includes('8 MB'));
 const move=nodes(tree).find(n=>n.props?.accessibilityLabel==='Fotoğrafı sonraya taşı 1');assert.ok(move);
 await move.props.onPress();await tick();tree=h.render('Composer',props);
 assert.deepEqual(JSON.parse(h.storeValues.get('1:post')).media_ids,[2,1]);
 const remove=nodes(tree).find(n=>n.props?.accessibilityLabel==='Fotoğrafı kaldır 1');assert.ok(remove);
 await remove.props.onPress();await tick();
 assert.deepEqual(JSON.parse(h.storeValues.get('1:post')).media_ids,[1]);
});

test('Dental Flow composer previews HTTPS links and sends the owner-scoped preview receipt',async()=>{
 const h=harness(),closed=[];const props={token:'synthetic',userId:2,onClose:()=>closed.push(true),onPosted(){}};
 let tree=h.render('Composer',props);await tick();tree=h.render('Composer',props);
 const link=nodes(tree).find(n=>n.props?.accessibilityLabel==='Bağlantı');assert.ok(link);
 link.props.onChangeText('https://example.org/article');
 tree=h.render('Composer',props);
 const preview=nodes(tree).find(n=>text(n)==='Önizlemeyi getir');assert.ok(preview);
 await preview.props.onPress();await tick();tree=h.render('Composer',props);
 assert.deepEqual(h.previews,['https://example.org/article']);
 assert.ok(text(tree).includes('Example title'));
 const publish=nodes(tree).find(n=>text(n)==='Paylaş');assert.ok(publish);
 await publish.props.onPress();await tick();await tick();
 assert.equal(h.posts.length,1);
 assert.equal(h.posts[0].preview_id,77);
 assert.equal(h.posts[0].link_url,'https://example.org/article');
 assert.deepEqual(closed,[true]);
});

test('native Dental Flow renders link cover separately from the four-image gallery',()=>{
 const h=harness(),post={id:42,author_id:7,author_name:'Expert',text:'Clinical share',status:'PUBLISHED',version:1,owned:false,pinned:false,comments_closed:false,liked:false,like_count:0,comment_count:0,link_url:'https://example.org/article',cover_media_id:10,preview:{title:'Example title',domain:'example.org',description:'Safe description'},media:[{id:10,url:'/api/expert-social/media/10'},{id:11,url:'/api/expert-social/media/11'}],created_at:'2026-11-17'};
 const tree=h.render('PostCard',{token:'synthetic',userId:2,post,showExpertActions:true,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow:async()=>true,onSupport(){}});
 const galleryButtons=nodes(tree).filter(n=>n.props?.accessibilityLabel?.startsWith('Gönderi görselini aç'));
 assert.equal(galleryButtons.length,1,'the link cover must not be duplicated in the gallery');
 assert.ok(text(tree).includes('Example title'));
 assert.ok(text(tree).includes('Safe description'));
 assert.equal(nodes(tree).filter(n=>n.type==='Image').length,2,'one gallery image plus one preview cover');
});

test('Dental Flow-owned aggregate posts route management to the expert profile like web',()=>{
 const h=harness(),props={token:'synthetic',userId:1,post:{id:5,author_id:1,author_name:'Owner',text:'Owned',media:[],status:'PUBLISHED',owned:true,created_at:'2026-11-17'},showExpertActions:true,onUpdate(){},onComments(){},onProfile(){},onImage(){},onEdit(){},onFollow:async()=>true,onSupport(){}};
 let tree=h.render('PostCard',props);nodes(tree).find(n=>n.props?.accessibilityLabel==='Gönderi işlemleri').props.onPress();
 tree=h.render('PostCard',props);const sheet=nodes(tree).find(n=>n.props?.title==='Gönderi işlemleri');
 const labels=nodes(sheet).map(n=>n.props?.title);assert.ok(labels.includes('Profilimde yönet'));assert.equal(labels.includes('Düzenle'),false);
});

test('uncertain Dental Flow post retries reuse the frozen idempotency key',async()=>{
 const h=harness(),draft={id:'11111111-1111-4111-8111-111111111111',text:'Retry me',link:'',media_ids:[9],attempted:true};
 h.storeValues.set('3:post',JSON.stringify(draft));
 const props={token:'synthetic',userId:3,onClose(){},onPosted(){}};
 let tree=h.render('Composer',props);await tick();tree=h.render('Composer',props);
 const retry=nodes(tree).find(n=>text(n)==='Tekrar dene');assert.ok(retry);
 await retry.props.onPress();await tick();
 assert.equal(h.posts.length,1);
 assert.equal(h.posts[0].idempotency_key,draft.id);
 assert.deepEqual(h.posts[0].media_ids,[9]);
});
test('Dental Flow native tabs use the web label and selected state',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 assert.ok(source.includes('m === "discover" ? "Keşfet" : "Takip Ettiklerim"'));
});
test('failed encrypted Dental Flow draft reads offer non-destructive retry',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const draft=source.slice(source.indexOf('function useDraft('),source.indexOf('function Composer('));
 assert.match(draft,/\[retry, setRetry\] = useState\(0\)/);
 assert.match(draft,/\[key, retry\]/);
 assert.match(draft,/retryRead:/);
 const composer=source.slice(source.indexOf('function Composer('),source.indexOf('function Sheet('));
 assert.match(composer,/title="Tekrar oku" onPress=\{d\.retryRead\}/);
 assert.match(composer,/title="Bozuk taslağı temizle"/);
});

test('Dental Flow composer remounts when authenticated account or session changes',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 // Credential-free remount: the key is the non-secret session epoch, which
 // advances on every real identity change (user.id or token) — the bearer
 // token itself must never appear inside a React key.
 assert.match(source,/key=\{\`\$\{sessionKey\}:composer\`\}\s+token=\{token\}\s+userId=\{user\.id\}/);
 assert.match(source,/if\s*\(\s*isSocialSessionCurrent\(\s*observedSession\.current,\s*nextSession\s*\)\s*\)\s*return;/,'session epoch advances only on a real identity change');
 assert.match(source,/setSessionEpoch\(\(value\) => value \+ 1\)/,'identity change bumps the session epoch so the composer remounts');
 assert.doesNotMatch(source,/key=\{`\$\{user\.id\}:\$\{token\}`\}/,'bearer tokens must never be embedded in React keys');
});

test('Dental Flow composer selects, restores and submits a custom link cover',async()=>{
 const h=harness(),props={token:'synthetic',userId:1,onClose(){},onPosted(){}};
 const saved={id:'cover-key',text:'',link:'https://example.org/article',media_ids:[11,12],attempted:false,preview_id:77,preview:{available:true,id:77,url:'https://example.org/article',cover:{id:81,url:'/api/expert-social/media/81'}}};
 h.storeValues.set('1:post',JSON.stringify(saved));
 h.render('Composer',props);await tick();
 let tree=h.render('Composer',props);
 const choose=nodes(tree).find(n=>n.props?.accessibilityLabel==='Bağlantı kapağı yap 2');
 assert.ok(choose,'uploaded media should be selectable as the link cover');
 choose.props.onPress();
 tree=h.render('Composer',props);
 assert.ok(nodes(tree).some(n=>n.props?.accessibilityLabel==='Bağlantı kapağı seçildi 2'));
 const publish=nodes(tree).find(n=>n.type==='Pressable'&&text(n)==='Paylaş');
 assert.ok(publish);await publish.props.onPress();await tick();
 assert.equal(h.posts.length,1);assert.equal(h.posts[0].cover_media_id,12);
});
test('Dental Flow defaults the first of four uploaded images as the link cover and clears a removed cover',async()=>{
 const h=harness(),props={token:'synthetic',userId:1,onClose(){},onPosted(){}};
 const saved={id:'cover-key',text:'',link:'https://example.org/article',media_ids:[11,12,13,14],attempted:false,preview_id:77,preview:{available:true,id:77,url:'https://example.org/article',cover:null}};
 h.storeValues.set('1:post',JSON.stringify(saved));
 h.render('Composer',props);await tick();
 let tree=h.render('Composer',props);
 const publish=nodes(tree).find(n=>n.type==='Pressable'&&text(n)==='Paylaş');
 await publish.props.onPress();
 assert.equal(h.posts[0].cover_media_id,11,'web uses the first image when all four slots are filled without a selected cover');
 const h2=harness(),saved2={...saved,media_ids:[11,12],cover_media_id:12};
 h2.storeValues.set('1:post',JSON.stringify(saved2));
 h2.render('Composer',props);await tick();tree=h2.render('Composer',props);
 const remove=nodes(tree).find(n=>n.props?.accessibilityLabel==='Fotoğrafı kaldır 2');
 assert.ok(remove);remove.props.onPress();await tick();await tick();tree=h2.render('Composer',props);
 const publish2=nodes(tree).find(n=>n.type==='Pressable'&&text(n)==='Paylaş');
 await publish2.props.onPress();await tick();
 assert.equal(h2.posts[0].cover_media_id,undefined);
});

test('Dental Flow keeps a safe link card visible when metadata preview is unavailable',async()=>{
 const h=harness(),props={token:'synthetic',userId:1,onClose(){},onPosted(){}};
 const saved={id:'plain-link',text:'',link:'https://example.org/article',media_ids:[],attempted:false,preview:null};
 h.storeValues.set('1:post',JSON.stringify(saved));
 h.render('Composer',props);await tick();
 const tree=h.render('Composer',props);
 const card=nodes(tree).find(n=>n.props?.accessibilityLabel==='Bağlantı önizlemesini aç');
 assert.ok(card,'the web composer retains the URL card when preview metadata is unavailable');
 await card.props.onPress();
 assert.deepEqual(h.opened,['https://example.org/article']);
});
test('Dental Flow reconnect refresh is event-driven, owner-only and bounded',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const helper=fs.readFileSync(require.resolve('../src/socialModerationRefresh.ts'),'utf8');
 assert.match(source,/AppState\.addEventListener\(\s*"change"/);
 assert.ok(source.includes('navigation?.addListener?.("focus"'));
 assert.ok(source.includes('api.getPostModerationStatus'));
 assert.ok(source.includes('selectOwnedModerationCandidates(pages.items)'));
 assert.ok(helper.includes('SOCIAL_MODERATION_RESUME_LIMIT = 5'));
 assert.ok(helper.includes('SOCIAL_MODERATION_RESUME_COOLDOWN_MS = 15_000'));
 assert.doesNotMatch(source,/setInterval\s*\(/,'reconnect refresh must not introduce polling');
});



test('comment refresh invalidates an in-flight page lease without wedging the next cursor',async()=>{
 const h=harness(),pending=[];
 const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r});return {promise,resolve}};
 h.setGetCommentsHandler((_token,_postId,after)=>{
  if(after===0)return Promise.resolve({items:[{id:10,text:'root',author_name:'A',parent_id:null}],next_cursor:10});
  if(after===10){const item=deferred();pending.push(item);return item.promise;}
  if(after===20)return Promise.resolve({items:[],next_cursor:null});
  throw Error('unexpected cursor '+after);
 });
 const props={token:'synthetic',userId:2,post:{id:5,comments_closed:false},onClose(){},onProfile(){}};
 h.render('Comments',props);await tick();
 let tree=h.render('Comments',props),list=nodes(tree).find(n=>n.type==='FlatList');
 assert.ok(list,'comments use the native paged list');
 list.props.ListFooterComponent.props.onPress();
 assert.equal(h.requests.length,2,'the first older-page request starts');
 list.props.onRefresh();
 await tick();
 tree=h.render('Comments',props);list=nodes(tree).find(n=>n.type==='FlatList');
 list.props.ListFooterComponent.props.onPress();
 assert.equal(h.requests.length,4,'refresh releases the stale page lease so the current cursor can be requested again');
 assert.equal(h.requests[3][2],10);
 pending[0].resolve({items:[{id:11,text:'stale page',author_name:'A',parent_id:null}],next_cursor:20});
 await tick();
 tree=h.render('Comments',props);list=nodes(tree).find(n=>n.type==='FlatList');
 list.props.ListFooterComponent.props.onPress();
 assert.equal(h.requests.length,4,'a stale finally block must not release the newer page request lease');
 pending[1].resolve({items:[{id:21,text:'current page',author_name:'B',parent_id:null}],next_cursor:20});
 await tick();
 tree=h.render('Comments',props);list=nodes(tree).find(n=>n.type==='FlatList');
 assert.equal(list.props.ListFooterComponent.props.disabled,false);
 list.props.ListFooterComponent.props.onPress();await tick();
 assert.equal(h.requests.length,5,'pagination continues from the current page cursor');
 assert.equal(h.requests[4][2],20);
});


test('Dental Flow comment pagination lock is owned by a request and refresh invalidates stale ownership',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const comments=source.slice(source.indexOf('function Comments('),source.indexOf('function PostCard('));
 assert.match(comments,/commentPageRequest\s*=\s*useRef<number\s*\|\s*null>\(null\)/);
 assert.match(comments,/if \(after && commentPageRequest\.current !== null\) return/);
 assert.match(comments,/else commentPageRequest\.current = null/);
 assert.match(comments,/if \(commentPageRequest\.current === request\)/);
 assert.doesNotMatch(comments,/commentPageLock/);
});


test('Dental Flow session scope changes on account or bearer rotation and rejects stale async completions',()=>{
 const oldSession={userId:7,token:'old-bearer'};
 const newSession={userId:8,token:'new-bearer'};
 const rotated={userId:7,token:'rotated-bearer'};
 const oldKey=sessionScopeExports.socialSessionKey(oldSession.userId,1);
 const rotatedKey=sessionScopeExports.socialSessionKey(rotated.userId,2);
 const otherAccountKey=sessionScopeExports.socialSessionKey(newSession.userId,1);
 assert.notEqual(oldKey,rotatedKey);
 assert.notEqual(oldKey,otherAccountKey);
 assert.equal(oldKey.includes('old-bearer'),false,'bearer token must never enter React keys');
 assert.equal(sessionScopeExports.isSocialSessionCurrent(oldSession,oldSession),true);
 assert.equal(sessionScopeExports.isSocialSessionCurrent(newSession,oldSession),false);
 assert.equal(sessionScopeExports.isSocialSessionCurrent(rotated,oldSession),false);
});

test('Dental Flow gates old feed, comments, images and edits while a new session is being painted',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const flow=source.slice(source.indexOf('export function DentalFlow('));
 assert.match(flow,/const sessionKey = socialSessionKey\(user\.id, sessionEpoch\)/);
 assert.match(flow,/const sessionReady = isSocialSessionCurrent\(readySession, \{ userId: user\.id, token \}\)/);
 assert.match(flow,/const observedSession = useRef\(\{ userId: user\.id, token \}\)/);
 assert.match(flow,/if \(isSocialSessionCurrent\(observedSession\.current, nextSession\)\) return/);
 assert.match(flow,/setSessionEpoch\(\(value\) => value \+ 1\)/);
 assert.match(flow,/usePagedRecords<api\.SocialPost>\(\s*`\$\{sessionKey\}/);
 assert.match(flow,/data=\{sessionReady \? pages\.items : \[\]\}/);
 assert.match(flow,/\{comments && sessionReady && \(/);
 assert.match(flow,/key=\{\`\$\{sessionKey\}:\$\{comments\.id\}\`\}/);
 assert.match(flow,/\{image && sessionReady && \(/);
 assert.match(flow,/\{editing && sessionReady && \(/);
 assert.match(flow,/moderationResumeGate\.current = createModerationResumeGate\(\)/);
 assert.match(flow,/if \(!sessionReady \|\| moderationRefreshLocks\.current\.has\(sessionKey\)\) return/);
});

test('Dental Flow ignores delayed follow, edit and compose results from a previous session',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const flow=source.slice(source.indexOf('export function DentalFlow('));
 assert.match(flow,/if \(!isSocialSessionCurrent\(sessionScope\.current, requestSession\)\) return false/);
 assert.match(flow,/update\(p, p\.id, requestSession\)/);
 assert.match(flow,/if \(!isSocialSessionCurrent\(sessionScope\.current, \{ userId: user\.id, token \}\)\) return;/);
 assert.match(flow,/onPosted=\{\(p\) => \{\s*if \(!isSocialSessionCurrent/);
});


test('native comment moderation matches web ownership rules and updates the authoritative count',async()=>{
 const h=harness(),changes=[],counts=[];
 h.api.deleteComment=async()=>({ok:true,comment_count:4,removed_count:2});
 const item={id:21,post_id:4,author_id:9,author_name:'Other member',text:'Reply thread root',status:'PUBLISHED',version:1,owned:false,liked:false,like_count:0,reply_count:1,parent_id:null};
 let tree=h.render('CommentThread',{token:'synthetic',item,postId:4,canDeleteOthers:true,commentsClosed:false,onChange:(...args)=>changes.push(args),onReply(){},onProfile(){},onCountChange:count=>counts.push(count)});
 nodes(tree).find(n=>n.props?.accessibilityLabel==='Yorum işlemleri').props.onPress();
 const actions=h.alerts[0][2];
 assert.deepEqual(actions.map(a=>a.text),['Vazgeç','Sil','Bildir']);
 assert.ok(actions.length<=3,'Android must retain every action without truncating the Alert');
 actions.find(a=>a.text==='Sil').onPress();
 const confirm=h.alerts[1][2];
 await confirm.find(a=>a.text==='Sil').onPress();
 await tick();
 assert.deepEqual(changes,[[null,21]]);
 assert.deepEqual(counts,[4]);

 const member=harness();
 tree=member.render('CommentThread',{token:'synthetic',item,postId:4,canDeleteOthers:false,commentsClosed:false,onChange(){},onReply(){},onProfile(){},onCountChange(){}});
 nodes(tree).find(n=>n.props?.accessibilityLabel==='Yorum işlemleri').props.onPress();
 assert.deepEqual(member.alerts[0][2].map(a=>a.text),['Vazgeç','Bildir']);

 const author=harness();
 tree=author.render('CommentThread',{token:'synthetic',item:{...item,owned:true},postId:4,canDeleteOthers:false,commentsClosed:false,onChange(){},onReply(){},onProfile(){},onCountChange(){}});
 nodes(tree).find(n=>n.props?.accessibilityLabel==='Yorum işlemleri').props.onPress();
 assert.deepEqual(author.alerts[0][2].map(a=>a.text),['Vazgeç','Düzenle','Sil']);
});

test('native comments hide replies on closed or unpublished threads and use ten-row reply pages',async()=>{
 const h=harness(),base={id:10,post_id:5,author_id:7,author_name:'Expert',text:'Root',version:1,owned:false,liked:false,like_count:0,reply_count:1,parent_id:null};
 let tree=h.render('CommentThread',{token:'synthetic',item:{...base,status:'PENDING'},postId:5,canDeleteOthers:false,commentsClosed:false,onChange(){},onReply(){},onProfile(){},onCountChange(){}});
 assert.equal(nodes(tree).some(n=>text(n)==='Yanıtla'),false);
 const pendingLike=nodes(tree).find(n=>n.type==='Pressable'&&text(n).startsWith('♡'));
 assert.equal(pendingLike.props.disabled,true);

 tree=h.render('CommentThread',{token:'synthetic',item:{...base,status:'PUBLISHED'},postId:5,canDeleteOthers:false,commentsClosed:true,onChange(){},onReply(){},onProfile(){},onCountChange(){}});
 assert.equal(nodes(tree).some(n=>text(n)==='Yanıtla'),false);

 tree=h.render('CommentThread',{token:'synthetic',item:{...base,status:'PUBLISHED'},postId:5,canDeleteOthers:false,commentsClosed:false,onChange(){},onReply(){},onProfile(){},onCountChange(){}});
 const toggle=nodes(tree).find(n=>n.type==='Pressable'&&text(n)==='1 yanıtı aç');
 assert.ok(toggle);
 await toggle.props.onPress();
 await tick();
 assert.equal(h.requests[0][4],10,'native reply paging must match the web limit');
});

test('native comment sheet displays and publishes the server comment count',async()=>{
 const h=harness(),counts=[];
 h.setGetCommentsHandler(async()=>({items:[],next_cursor:null,comment_count:12}));
 const onCountChange=(postId,count)=>counts.push([postId,count]);
 const props={token:'synthetic',userId:3,post:{id:6,owned:true,comments_closed:false,comment_count:10},onClose(){},onProfile(){},onCountChange};
 let tree=h.render('Comments',props);
 await tick();
 tree=h.render('Comments',props);
 const sheet=nodes(tree).find(n=>typeof n.props?.title==='string'&&n.props.title.startsWith('Yorumlar'));
 assert.ok(sheet);
 assert.equal(sheet.props.title,'Yorumlar · 12');
 assert.deepEqual(counts,[[6,12]]);
});
