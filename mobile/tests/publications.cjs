const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const paper={id:5,title:'Synthetic paper',authors:'A. Synthetic',year:2025,journal:'Synthetic Journal',doi:'10.1000/test',url:'https://doi.org/10.1000/test',description:'Summary',source:'MANUAL',status:'PUBLISHED',version:1};
test('publication updates send the current version and preserve DOI-match provenance',async()=>{
 const api=require('../src/publicationsApi.ts'),original=global.fetch,calls=[];
 try{global.fetch=async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify({...paper,version:2}),{status:200})};const result=await api.savePublication('token',{...paper,match_id:9},paper);assert.equal(result.version,2);const payload=JSON.parse(calls[0].options.body);assert.equal(payload.version,1);assert.equal(payload.match_id,9);assert.equal(calls[0].options.method,'PUT');assert.equal(calls[0].options.credentials,'omit');assert.equal(calls[0].options.headers.Authorization,'Bearer token');}finally{global.fetch=original}
});
test('ORCID HTTP 200 failure is surfaced and malformed publication pages are rejected',async()=>{
 const api=require('../src/publicationsApi.ts'),original=global.fetch;
 try{global.fetch=async()=>new Response(JSON.stringify({ok:false,error_code:'ORCID_UNAVAILABLE',message:'Manual entry remains available'}),{status:200});await assert.rejects(()=>api.syncOrcid('token','0000-0002-1825-0097'),/Manual entry/);
 global.fetch=async()=>new Response(JSON.stringify({items:[paper],total:1,next_cursor:8,sync:null}),{status:200});await assert.rejects(()=>api.getPublications('token',2),/sayfa/);
 await assert.rejects(()=>api.savePublication('token',{...paper,year:99}),/yıl/);
 }finally{global.fetch=original}
});
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(tree,label)=>tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
function ui(api,alerts=[]){api={...require('../src/publicationsApi.ts'),...api};const exports={},native={StyleSheet:{create:x=>x},Alert:{alert:(...a)=>alerts.push(a)},AppState:{addEventListener:()=>({remove(){}})},Linking:{openURL:async()=>{}},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x])),FlatList:({data,renderItem,ListHeaderComponent,ListEmptyComponent,ListFooterComponent})=>React.createElement('FlatList',null,ListHeaderComponent,data.length?data.map(item=>React.createElement(React.Fragment,{key:item.id},renderItem({item}))):ListEmptyComponent,ListFooterComponent)};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePublications.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,setTimeout,clearTimeout,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='./usePagedRecords'?require('../src/usePagedRecords.ts'):n==='expo-crypto'?{randomUUID:()=> 'synthetic-share-key'}:api});return exports.default;
}
test('native publication editor sends all web fields and locks duplicate save taps',async()=>{
 const calls=[];let release;const api={getPublications:async()=>({items:[],next_cursor:null,total:0,sync:null}),savePublication:(_t,draft)=>{calls.push(draft);return new Promise(r=>release=()=>r(paper))}};const Component=ui(api);let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',expertId:2,owned:true,canWrite:true})));await renderer.act(async()=>button(tree,'Manuel Yayın Ekle').props.onPress());
 await renderer.act(async()=>{for(const [label,value]of Object.entries({'Makale başlığı':'Synthetic paper','Yazarlar':'A. Synthetic','Yıl':'2025','Dergi':'Synthetic Journal','DOI':'10.1000/test','Kaynak bağlantısı':'https://doi.org/10.1000/test','Açıklama':'Summary'}))tree.root.findByProps({accessibilityLabel:label}).props.onChangeText(value)});
 await renderer.act(async()=>{button(tree,'Yayını Kaydet').props.onPress();button(tree,'Yayını Kaydet').props.onPress()});assert.equal(calls.length,1);assert.equal(calls[0].journal,'Synthetic Journal');assert.equal(calls[0].year,2025);await renderer.act(async()=>release());await renderer.act(async()=>tree.unmount());
});
test('read-only publication list exposes sources without edit controls',async()=>{
 const Component=ui({getPublications:async()=>({items:[paper],next_cursor:null,total:1,sync:null})});let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',expertId:2,owned:false,canWrite:false})));assert.ok(JSON.stringify(tree.toJSON()).includes('Synthetic paper'));assert.equal(button(tree,'Manuel Yayın Ekle'),undefined);assert.equal(button(tree,'Düzenle'),undefined);await renderer.act(async()=>tree.unmount());
});

test('publication share uses canonical preview and one stable idempotency key',async()=>{
 const api=require('../src/publicationsApi.ts'),original=global.fetch,calls=[];
 try{global.fetch=async(url,options)=>{calls.push({url,body:JSON.parse(options.body||'{}')});return new Response(JSON.stringify(url.endsWith('share-preview')?{available:true,id:12,url:'https://doi.org/10.1000/test'}:{id:31}),{status:200})};await api.sharePublication('token',paper,'Synthetic commentary','00000000-0000-4000-8000-000000000001');assert.equal(calls[1].body.preview_id,12);assert.equal(calls[1].body.idempotency_key,'00000000-0000-4000-8000-000000000001');}finally{global.fetch=original}
});

test('DOI lookup fills the native editor and keeps match id until confirmed save',async()=>{
 const calls=[],api={getPublications:async()=>({items:[],next_cursor:null,total:0,sync:null}),lookupPublicationDoi:async()=>({...paper,match_id:19}),savePublication:async(_t,draft)=>{calls.push(draft);return paper}};const Component=ui(api);let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',expertId:2,owned:true,canWrite:true})));await renderer.act(async()=>button(tree,'Manuel Yayın Ekle').props.onPress());await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'DOI'}).props.onChangeText('10.1000/test'));await renderer.act(async()=>button(tree,'DOI Bilgilerini Getir').props.onPress());assert.equal(tree.root.findByProps({accessibilityLabel:'Makale başlığı'}).props.value,'Synthetic paper');assert.equal(calls.length,0);await renderer.act(async()=>button(tree,'Yayını Kaydet').props.onPress());assert.equal(calls[0].match_id,19);await renderer.act(async()=>tree.unmount());
});

const profile={user_id:2,display_name:'Uzm. Dt. Synthetic Expert',raw_name:'Synthetic Expert',photo_url:null,specialty:'Endodonti',institution:'Synthetic institution',bio:'Synthetic bio',orcid_url:null,publications_text:null,academic_title_verified:false,consultation_price:1200,availability:'AVAILABLE',owned:false,can_publish:false,support_available:true,performance:{rating_avg:null,review_count:0,completed_count:4,avg_response_minutes:null}};
function profileUI(api){const exports={},native={StyleSheet:{create:x=>x},AppState:{addEventListener:()=>({remove(){}})},Linking:{openURL:async()=>{}},...Object.fromEntries(['ActivityIndicator','Image','Pressable','ScrollView','Text','View'].map(x=>[x,x]))};const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeExpertProfile.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;vm.runInNewContext(code,{exports,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{useIsFocused:()=>true}:n==='./publicationsApi'?api:n==='./socialApi'?{getSocialStats:async()=>({followers:3,following:2,posts:1,publications:1,following_by_viewer:false}),setFollow:async()=>({following_by_viewer:true})}:n==='./realtime'?{useRealtime:()=>({lastEvent:null})}:n==='./NativeRelationships'?{default:p=>React.createElement('NativeRelationships',p)}:n==='./SocialScreens'?{DentalFlow:p=>React.createElement('DentalFlow',p,p.expertHeader)}:{default:p=>React.createElement('NativePublications',p,p.header)}});return exports.default;}
test('public expert profile shows real identity, tabs and patient-linked support navigation',async()=>{
 const navigation=[],Component=profileUI({getPublicExpert:async()=>profile});let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',user:{id:1},expertId:2,patientId:8,navigation:{navigate:(...a)=>navigation.push(a)}})));assert.ok(text(tree.toJSON()).includes('Synthetic institution'));await renderer.act(async()=>button(tree,'Uzmandan Destek Al').props.onPress());assert.equal(navigation[0][0],'NewConsultation');assert.equal(navigation[0][1].patientId,8);await renderer.act(async()=>button(tree,'Yayınlar').props.onPress());assert.equal(tree.root.findByType('NativePublications').props.canWrite,false);await renderer.act(async()=>tree.unmount());
});
test('public expert profile never shows a delayed previous account response',async()=>{
 let release;const Component=profileUI({getPublicExpert:token=>token==='A'?new Promise(r=>release=r):Promise.resolve({...profile,bio:'New account profile'})});let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',user:{id:1},expertId:2,navigation:{}})));await renderer.act(async()=>tree.update(React.createElement(Component,{token:'B',user:{id:1},expertId:2,navigation:{}})));await renderer.act(async()=>release({...profile,bio:'Old account leaked'}));assert.ok(!text(tree.toJSON()).includes('Old account leaked'));await renderer.act(async()=>tree.unmount());
});

test('expert directory opens even busy profiles and retains the selected patient context',async()=>{
 const exports={},navigations=[],native={StyleSheet:{create:x=>x},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x])),FlatList:({data,renderItem})=>React.createElement('FlatList',null,data.map(item=>React.createElement(React.Fragment,{key:item.user_id},renderItem({item}))))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,setTimeout,clearTimeout,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='./modernApi'?{getExperts:async()=>({items:[{user_id:2,display_name:'Synthetic expert',specialty:'Endodonti',availability:'BUSY'}]})}:n==='./realtime'?{useRealtime:()=>({lastEvent:null})}:{}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(exports.ExpertDirectory,{token:'A',patientId:8,navigation:{navigate:(...a)=>navigations.push(a)}}));await new Promise(r=>setTimeout(r,10))});await renderer.act(async()=>new Promise(r=>setTimeout(r,10)));
 const row=tree.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)==='Synthetic expert'));assert.ok(row);assert.ok(!row.props.disabled);await renderer.act(async()=>row.props.onPress());assert.equal(navigations[0][0],'ExpertProfile');assert.equal(navigations[0][1].patientId,8);await renderer.act(async()=>tree.unmount());
});

test('native ORCID import locks repeated taps and refreshes persisted sync state',async()=>{
 let release,complete=false;const calls=[],alerts=[],Component=ui({getPublications:async()=>({items:complete?[paper]:[],next_cursor:null,total:complete?1:0,sync:complete?{status:'SUCCEEDED',imported_count:1}:null}),syncOrcid:async(...args)=>{calls.push(args);return new Promise(r=>release=()=>{complete=true;r({ok:true,imported_count:1,message:'One imported'})})}},alerts);let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',expertId:2,owned:true,canWrite:true})));await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'ORCID aktarım kimliği'}).props.onChangeText('0000-0002-1825-0097'));await renderer.act(async()=>{button(tree,'ORCID Yayınlarını Getir').props.onPress();button(tree,'ORCID Yayınlarını Getir').props.onPress()});assert.equal(calls.length,1);await renderer.act(async()=>release());assert.ok(text(tree.toJSON()).includes('1 yayın içe aktarıldı.'));assert.ok(text(tree.toJSON()).includes('Synthetic paper'));assert.equal(alerts.length,1);await renderer.act(async()=>tree.unmount());
});

test('own expert header exposes private relationship drawers and native expert navigation',async()=>{
 const navigation=[],Component=profileUI({getPublicExpert:async()=>({...profile,owned:true})});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',user:{id:2},expertId:2,navigation:{navigate:(...args)=>navigation.push(args)}})));
 const lists=tree.root.findByType('NativeRelationships');assert.equal(lists.props.ownerId,2);assert.equal(lists.props.showFollowers,true);assert.equal(lists.props.followers,3);
 await renderer.act(async()=>lists.props.onExpert(3));assert.deepEqual(JSON.parse(JSON.stringify(navigation)),[['ExpertProfile',{id:3}]]);await renderer.act(async()=>tree.unmount());
});
