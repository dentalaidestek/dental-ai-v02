const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const tick=()=>new Promise(r=>setImmediate(r));
function harness(){
 const state=[],alerts=[],refs=[],previous=[],effects=[],requests=[];let cursor=0,ri=0,ei=0;
 const react={useState:initial=>{const id=cursor++;if(!(id in state))state[id]=typeof initial==='function'?initial():initial;return [state[id],v=>state[id]=typeof v==='function'?v(state[id]):v]},useRef:v=>{const i=ri++;return refs[i]||(refs[i]={current:v})},useEffect:(f,deps)=>{const i=ei++;if(!previous[i]||deps.some((v,j)=>!Object.is(v,previous[i].deps[j])))effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})},createElement:(type,props,...children)=>({type,props:{...props,children}})};react.default=react;
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8')+'\nexport const __test={PostCard,CommentThread,Composer};';
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,exports={};
 const native={Alert:{alert:(...args)=>alerts.push(args)},StyleSheet:{create:s=>s},Pressable:'Pressable',Text:'Text',View:'View',Image:'Image'};
 const api={getComments:async(...args)=>{requests.push(args);return {items:[{id:20,text:'reply',author_name:'R',parent_id:10}],next_cursor:null}}};
 vm.runInNewContext(code,{exports,require:n=>n==='react'?react:n==='react-native'?native:n==='./socialApi'?api:n==='./socialDraft'?{chunkedDraftStore:()=>({}),draftKey:()=> 'draft',readDraft:async()=>null}:n==='expo-crypto'?{randomUUID:()=> 'synthetic-id'}:{}});
 return {alerts,refs,requests,render:(name,props)=>{cursor=ri=ei=0;const tree=exports.__test[name](props);while(effects.length)effects.shift()();return tree}};
}
function nodes(tree){if(!tree||typeof tree!=='object')return [];return [tree,...(tree.props?.children||[]).flat(Infinity).flatMap(nodes)];}
const text=n=>typeof n==='string'?n:!n||typeof n!=='object'?'':(n.props?.children||[]).flat(Infinity).map(text).join('');
test('Android owner menu exposes every action without an Alert exceeding three buttons',()=>{
 const h=harness(),props={token:'synthetic',post:{id:1,author_id:1,author_name:'Expert',text:'Science',media:[],status:'PUBLISHED',owned:true,created_at:'2026-11-10'},onEdit(){}};
 let tree=h.render('PostCard',props);nodes(tree).find(n=>n.props?.accessibilityLabel==='Gönderi işlemleri').props.onPress();
 assert.ok(h.alerts.every(a=>!a[2]||a[2].length<=3),'Android truncates Alert buttons after three');
 tree=h.render('PostCard',props);const sheet=nodes(tree).find(n=>n.props?.title==='Gönderi işlemleri');assert.ok(sheet,'native action sheet opens');
 const labels=nodes(sheet).map(n=>n.props?.title);for(const label of ['Düzenle','Sabitle','Yorumları kapat','Sil'])assert.ok(labels.includes(label),label);
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
 const source=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
 const gallery=source.slice(source.indexOf('export function MediaGallery('),source.indexOf('export function ExpertDirectory('));
 assert.ok(gallery.includes('const mounted=useRef(true)'), 'mounted state must be tracked');
 assert.ok(gallery.includes('generation.current++'), 'refresh generations invalidate stale requests');
 assert.ok(gallery.includes('scope!==patientScope.current||!mounted.current'), 'patient switch must cancel pending media picker');
 assert.ok(gallery.includes('loadingMoreRef.current||refreshing||uploading||deleting'), 'pagination must not overlap refresh or mutations');
 assert.ok(gallery.includes('if(mounted.current&&scope===patientScope.current)'), 'old account must not update gallery after upload');
 assert.ok(gallery.includes('if(mounted.current&&current===generation.current&&scope===patientScope.current)'), 'old page must not overwrite current patient');
});

test('patient detail never renders stale clinical data after account or patient change',()=>{
 const source=fs.readFileSync(require.resolve('../App.tsx'),'utf8');
 const screen=source.slice(source.indexOf('function PatientDetailScreen('),source.indexOf('function PatientStack('));
 const profile=fs.readFileSync(require.resolve('../src/NativePatientProfile.tsx'),'utf8');
 assert.match(screen,/NativePatientProfile key=\{token\+":"\+id\}/,'navigation must remount the patient boundary');
 assert.ok(profile.includes('if(owner.current!==scope){owner.current=scope;request.current++;}'),'scope changes synchronously invalidate requests');
 assert.ok(profile.includes('if(!current()||seq!==request.current)return false'),'stale requests cannot commit');
 assert.ok(profile.includes('if(!detail||loadedScope!==scope)'),'hide previous patient before effects');
 assert.ok(profile.includes('mounted.current=false;request.current++'),'unmount invalidates pending requests');
});

test('clinical gallery hides old patient thumbnails and preview before effects run',()=>{
 const source=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
 const gallery=source.slice(source.indexOf('export function MediaGallery('),source.indexOf('export function ExpertDirectory('));
 assert.match(gallery,/visibleData=d\?\.accountScope===patientScope\.current\?d:null/);
 assert.match(gallery,/data=\{visibleData\?\.items\|\|\[\]\}/);
 assert.match(gallery,/visible=\{preview!==null&&preview\.accountScope===patientScope\.current\}/);
 assert.match(gallery,/preview\.accountScope!==patientScope\.current/);
 assert.match(gallery,/setD\(\{\.\.\.page,accountScope:scope\}\)/);
});

test('clinical gallery ignores pending page responses from another account before effects run',()=>{
 const source=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
 const gallery=source.slice(source.indexOf('export function MediaGallery('),source.indexOf('export function ExpertDirectory('));
 assert.match(gallery,/const current=\+\+generation\.current;const scope=patientScope\.current/);
 assert.match(gallery,/current===generation\.current&&scope===patientScope\.current/);
 assert.match(gallery,/setD\(\{\.\.\.page,accountScope:scope\}\)/);
 assert.match(gallery,/previous\.accountScope===scope/);
 assert.match(gallery,/next_before:page\.next_before,accountScope:previous\.accountScope/);
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

test('Dental Flow picker does not mislabel unnamed PNG and WebP uploads as JPEG',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const upload=source.slice(source.indexOf('async function image()'),source.indexOf('async function post()'));
 assert.match(upload,/a\.mimeType === "image\/png" \? "png"/);
 assert.match(upload,/a\.mimeType === "image\/webp" \? "webp"/);
 assert.match(upload,/name: a\.fileName \|\|/);
});

test('Dental Flow composer previews each selected photo and clears local thumbnails with draft',()=>{
 const source=fs.readFileSync(require.resolve('../src/SocialScreens.tsx'),'utf8');
 const composer=source.slice(source.indexOf('function Composer('),source.indexOf('function Sheet('));
 assert.match(composer,/setLocalPhotos\(previous => \[\.\.\.previous, a\.uri\]\.slice\(-4\)\)/);
 assert.match(composer,/localPhotos\.map\(\(uri,index\)=>/);
 assert.match(composer,/setLocalPhotos\(\[\]\)/);
 assert.doesNotMatch(composer,/Yüklenen son fotoğrafın önizlemesi/);
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
 assert.match(source,/<Composer\s+key=\{\x60\$\{user\.id\}:\$\{token\}\x60\}\s+token=\{token\}\s+userId=\{user\.id\}/);
});
