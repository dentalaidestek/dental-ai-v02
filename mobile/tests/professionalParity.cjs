const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const fixture=()=>({current_title:'Doç. Dr.',titles:['Doç. Dr.','Prof. Dr.'],eligible:true,membership:{status:'NONE'},document_types:[{key:'STUDENT',label:'Öğrenci Belgesi',description:'Synthetic'}],title_change:null,expert:null,specialties:['Endodonti'],minimum_price:500,has_photo:true,sms_enabled:false});
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
function mountModule(api,alerts,picker={getDocumentAsync:async()=>({canceled:true})},fileSystem={}){
 const exports={},native={StyleSheet:{create:x=>x},Alert:{alert:(...v)=>alerts.push(v)},AppState:{addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeProfessional.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-document-picker'?picker:n==='expo-file-system/legacy'?fileSystem:n==='./NativeExpertPerformance'?{default:()=>React.createElement('NativeExpertPerformance')}:n==='./realtime'?{useRealtime:()=>({lastEvent:null})}:api});return exports.default;
}
test('professional title uses explicit native confirmation and refreshes account identity',async()=>{
 const calls=[],alerts=[],changed=[];const api={getProfessional:async()=>fixture(),changeProfessionalTitle:async(token,title)=>{calls.push([token,title]);return{...fixture(),current_title:title}}};const Component=mountModule(api,alerts);let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'A',onChanged:()=>changed.push(true)}))});
 await renderer.act(async()=>button(tree,'Prof. Dr.').props.onPress());await renderer.act(async()=>button(tree,'Mesleki Durumu Kaydet').props.onPress());assert.equal(calls.length,0);
 await renderer.act(async()=>alerts.at(-1)[2].find(x=>x.text==='Onayla').onPress());assert.deepEqual(calls,[['A','Prof. Dr.']]);assert.equal(changed.length,1);
 await renderer.act(async()=>tree.unmount());
});
test('professional screen hides prior account data and ignores its delayed load',async()=>{
 let release;const api={getProfessional:token=>token==='A'?new Promise(r=>release=r):Promise.resolve({...fixture(),current_title:'Prof. Dr.'})};const Component=mountModule(api,[]);let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',onChanged(){}})));
 await renderer.act(async()=>tree.update(React.createElement(Component,{token:'B',onChanged(){}})));
 await renderer.act(async()=>release({...fixture(),membership:{status:'REJECTED',reason:'OLD ACCOUNT'}}));assert.ok(!JSON.stringify(tree.toJSON()).includes('OLD ACCOUNT'));
 await renderer.act(async()=>tree.unmount());
});
test('professional API rejects malformed states and invalid documents before network writes',async()=>{
 const api=require('../src/professionalApi.ts'),original=global.fetch;let count=0;
 try{global.fetch=async()=>{count++;return new Response(JSON.stringify({...fixture(),title_change:{status:'APPROVED',requested_title:'Prof. Dr.'}}),{status:200})};await assert.rejects(()=>api.getProfessional('A'),/doğrulanamadı/);
 await assert.rejects(()=>api.uploadProfessionalDocument('A','membership',{uri:'file:///proof.exe',name:'proof.exe',size:20,mimeType:'application/octet-stream'},'STUDENT',true),/PDF/);assert.equal(count,1);
 await assert.rejects(()=>api.uploadProfessionalDocument('A','membership',{uri:'file:///proof.pdf',name:'proof.pdf',size:6*1024*1024,mimeType:'application/pdf'},'STUDENT',true),/5 MB/);assert.equal(count,1);
 }finally{global.fetch=original}
});

test('expert editor sends the web fields and prevents duplicate writes while pending',async()=>{
 let release;const writes=[],busy=[];const value=fixture();value.expert={specialty:'Endodonti',phone:'05551234567',institution:'Before',bio:'Before bio',orcid_url:'0000-0002-1825-0097',publications_text:'Old publication',consultation_price:700,availability:'AVAILABLE',application_status:'APPROVED',verification_status:'VERIFIED',specialty_verified:true,credential_document_name:'proof.pdf'};
 const api={getProfessional:async()=>value,saveExpertProfile:(token,draft)=>{writes.push({token,draft});return new Promise(resolve=>release=()=>resolve(value))}};const Component=mountModule(api,[]);let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',onChanged(){},onBusyChanged:v=>busy.push(v)})));
 await renderer.act(async()=>button(tree,'Uzman Profilimi Düzenle').props.onPress());
 await renderer.act(async()=>{tree.root.findByProps({accessibilityLabel:'Kurum'}).props.onChangeText('Updated institution');tree.root.findByProps({accessibilityLabel:'Hakkında'}).props.onChangeText('Updated bio');tree.root.findByProps({accessibilityLabel:'Yayınlar / tezler'}).props.onChangeText('New publication');});
 await renderer.act(async()=>{button(tree,'Uzman Profilini Kaydet').props.onPress();button(tree,'Uzman Profilini Kaydet').props.onPress()});assert.equal(writes.length,1);assert.equal(writes[0].draft.institution,'Updated institution');assert.equal(writes[0].draft.publications_text,'New publication');assert.equal(busy.at(-1),true);
 await renderer.act(async()=>release());assert.equal(busy.at(-1),false);await renderer.act(async()=>tree.unmount());
});

test('expert rules are readable and require explicit checkbox consent before acceptance',async()=>{
 const value=fixture();value.expert={specialty:'Endodonti',availability:'BUSY',application_status:'APPROVED',verification_status:'VERIFIED',specialty_verified:true,consultation_price:700};const calls=[];
 const api={getProfessional:async()=>value,getExpertRules:async()=>({version:'web-v1',text:'Synthetic canonical rules: 10 dakika',accepted:false,blocked_until:null}),acceptExpertRules:async(...args)=>calls.push(args)};const Component=mountModule(api,[]);let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',onChanged(){}})));await renderer.act(async()=>button(tree,'Vaka Kabul Kurallarını Oku').props.onPress());
 assert.ok(JSON.stringify(tree.toJSON()).includes('Synthetic canonical rules'));assert.equal(button(tree,'Kuralları Onayla').props.disabled,true);assert.equal(calls.length,0);
 await renderer.act(async()=>tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityRole==='checkbox').props.onPress());assert.equal(button(tree,'Kuralları Onayla').props.disabled,false);
 await renderer.act(async()=>button(tree,'Kuralları Onayla').props.onPress());assert.deepEqual(calls,[['A','web-v1']]);await renderer.act(async()=>tree.unmount());
});

test('membership picker requires ownership consent, locks duplicate sends and clears its cache copy',async()=>{
 const asset={uri:'file:///cache/proof.pdf',name:'proof.pdf',size:2048,mimeType:'application/pdf'},uploads=[],deleted=[];let release;
 const api={getProfessional:async()=>fixture(),checkDocument:()=>asset,uploadProfessionalDocument:(...args)=>{uploads.push(args);return new Promise(resolve=>release=()=>resolve({...fixture(),membership:{status:'PENDING'}}))}};
 const Component=mountModule(api,[],{getDocumentAsync:async()=>({canceled:false,assets:[asset]})},{cacheDirectory:'file:///cache/',deleteAsync:async uri=>deleted.push(uri)});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(Component,{token:'A',onChanged(){}})));await renderer.act(async()=>button(tree,'Üyelik Belgesi Gönder').props.onPress());await renderer.act(async()=>button(tree,'Belge Seç').props.onPress());
 assert.equal(button(tree,'Belgeyi İncelemeye Gönder').props.disabled,true);await renderer.act(async()=>tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityRole==='checkbox').props.onPress());assert.equal(button(tree,'Belgeyi İncelemeye Gönder').props.disabled,false);
 await renderer.act(async()=>{button(tree,'Belgeyi İncelemeye Gönder').props.onPress();button(tree,'Belgeyi İncelemeye Gönder').props.onPress()});assert.equal(uploads.length,1);assert.equal(uploads[0][1],'membership');assert.equal(uploads[0][2].name,'proof.pdf');assert.equal(uploads[0][4],true);
 await renderer.act(async()=>release());assert.deepEqual(deleted,['file:///cache/proof.pdf']);assert.ok(JSON.stringify(tree.toJSON()).includes('Üyelik belgeniz incelemede'));await renderer.act(async()=>tree.unmount());
});

test('account places professional documents and expert management in separate web headings',async()=>{
 const child=mountModule({getProfessional:async()=>fixture()},[]),exports={},identity={id:8,username:'synthetic',display_name:'Synthetic',role:'DOCTOR',is_active:true};
 const native={StyleSheet:{create:s=>s},AppState:{addEventListener:()=>({remove(){}})},Alert:{alert(){}},...Object.fromEntries(['ActivityIndicator','Image','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeAccount.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='./NativeProfessional'?{default:child}:n==='@react-navigation/native'?{useIsFocused:()=>true}:n==='./authApi'?{getAccount:async()=>({user:identity,photo_url:null,next_username_change_at:null,email_change_allowed:true})}:n==='./realtime'?{useRealtime:()=>({lastEvent:null})}:{}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{token:'A',user:identity,onChanged(){},signOut(){},onMessages(){},onNotifications(){},onExperts(){},onAcademic(){},onHistory(){}})));
 await renderer.act(async()=>button(tree,'Mesleki durum ve belgelerim').props.onPress());assert.ok(button(tree,'Üyelik Belgesi Gönder'));assert.equal(button(tree,'Uzman Olarak Başvur'),undefined);
 await renderer.act(async()=>button(tree,'Uzman profilim').props.onPress());assert.ok(button(tree,'Uzman Olarak Başvur'));assert.equal(button(tree,'Üyelik Belgesi Gönder'),undefined);await renderer.act(async()=>tree.unmount());
});
