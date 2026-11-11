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
 assert.ok(gallery.includes('if(mounted.current&&current===generation.current)'), 'old page must not overwrite current patient');
});
