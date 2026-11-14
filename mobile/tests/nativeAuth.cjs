const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const text=node=>typeof node==='string'?node:!node?'':(node.children||[]).map(text).join('');
function button(tree,label){return tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(child=>text(child)===label))}
test('signup stays native and stores a session only after OTP and identity confirmation',async()=>{
 const stored=[],registrations=[],completed=[],exports={},options={legal_version:'test-version',professional_titles:['Öğrenci'],agreements:['terms','kvkk','clinical'].map(key=>({key,title:key,text:'Synthetic legal text'}))};
 const native={StyleSheet:{create:s=>s},Linking:{getInitialURL:async()=>null,addEventListener:()=>({remove(){}}),openURL(){throw Error('native signup must not redirect')}},BackHandler:{addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const api={login:async()=>{throw Error('Unexpected login')},verifyEmail:async(challenge,code)=>{assert.equal(challenge,'challenge');assert.equal(code,'123456');return{access_token:'confirmed-token'}},getMe:async()=>({user:{id:8,display_name:'Synthetic',username:'synthetic'}}),logout:async()=>{}};
 const auth={getAuthOptions:async()=>options,parseRecoveryLink:()=>null,registerAccount:async values=>{registrations.push(values);return{access_token:null,challenge_token:'challenge',expires_at:'2026-11-14T20:00:00'}}};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeAuth.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='expo-secure-store'?{setItemAsync:async(...args)=>stored.push(args)}:name==='./api'?api:auth});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(exports.default,{done:(...args)=>completed.push(args)}))});
 await renderer.act(async()=>button(tree,'Üye Ol').props.onPress());
 const values={'Ad soyad':'Synthetic Member','E-posta':'synthetic@example.test','Kullanıcı adı — en az 8 karakter':'synthetic-member','Şifre — en az 8 karakter':'correct-password','Şifre tekrarı':'correct-password','Üniversite / kurum':'Synthetic University'};
 await renderer.act(async()=>{for(const [label,value]of Object.entries(values))tree.root.findByProps({accessibilityLabel:label}).props.onChangeText(value);tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityRole==='radio').props.onPress();for(const item of tree.root.findAllByType('Pressable').filter(x=>x.props.accessibilityRole==='checkbox'))item.props.onPress()});
 await renderer.act(async()=>button(tree,'Hesap Oluştur').props.onPress());
 assert.equal(registrations.length,1);assert.equal(registrations[0].legal_version,'test-version');assert.equal(stored.length,0);assert.equal(completed.length,0);
 await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'Doğrulama kodu'}).props.onChangeText('123456'));
 await renderer.act(async()=>button(tree,'E-postayı Doğrula').props.onPress());
 assert.deepEqual(stored,[['dentalai_token','confirmed-token']]);assert.equal(completed[0][1].id,8);
 await renderer.act(async()=>tree.unmount());
});
test('recovery accepts only the intended HTTPS/custom-scheme destination',()=>{
 const {parseRecoveryLink}=require('../src/authApi.ts'),token='a'.repeat(43);
 assert.equal(parseRecoveryLink('https://dentalai.tr/reset-password?token='+token),token);
 assert.equal(parseRecoveryLink('dentalai://reset-password?token='+token),token);
 for(const url of ['https://evil.test/reset-password?token='+token,'https://dentalai.tr.evil.test/reset-password?token='+token,'http://dentalai.tr/reset-password?token='+token,'https://name@dentalai.tr/reset-password?token='+token,'https://dentalai.tr/reset-password?token=short'])assert.equal(parseRecoveryLink(url),null);
});
test('account editing refreshes shared identity and revoking changes expire the active session',async()=>{
 const events=[],changed=[],calls=[],exports={};let identity={id:8,username:'synthetic',display_name:'Synthetic Before',role:'DOCTOR',is_active:true};
 const native={StyleSheet:{create:s=>s},AppState:{addEventListener:()=>({remove(){}})},Alert:{alert(){}},...Object.fromEntries(['ActivityIndicator','Image','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const api={getAccount:async()=>({user:identity,photo_url:null,next_username_change_at:null,email_change_allowed:true}),accountAction:async(_token,action,values)=>{calls.push({action,values});if(action==='display-name'){identity={...identity,display_name:values.display_name};return{ok:true}}return{ok:true,requires_login:true}}};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeAccount.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./authApi'?api:name==='./realtime'?{useRealtime:()=>({lastEvent:null})}:name==='./sessionExpiry'?{reportSessionExpiry:token=>events.push(token)}:{}});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(exports.default,{token:'active-token',user:identity,onChanged:user=>changed.push(user),signOut(){},onMessages(){},onNotifications(){},onExperts(){},onAcademic(){},onHistory(){}}))});
 await renderer.act(async()=>button(tree,'Kişisel Bilgiler').props.onPress());
 await renderer.act(async()=>tree.root.findByProps({accessibilityLabel:'Ad soyad'}).props.onChangeText('Synthetic After'));
 await renderer.act(async()=>button(tree,'Ad Soyadı Kaydet').props.onPress());
 assert.equal(changed.at(-1).display_name,'Synthetic After');assert.equal(calls[0].action,'display-name');
 await renderer.act(async()=>button(tree,'Hesap Güvenliği').props.onPress());
 await renderer.act(async()=>{tree.root.findByProps({accessibilityLabel:'Mevcut şifre'}).props.onChangeText('correct-password');tree.root.findByProps({accessibilityLabel:'Yeni şifre'}).props.onChangeText('new-password');tree.root.findByProps({accessibilityLabel:'Yeni şifre tekrarı'}).props.onChangeText('new-password')});
 await renderer.act(async()=>button(tree,'Şifreyi Değiştir').props.onPress());
 assert.deepEqual(events,['active-token']);
 await renderer.act(async()=>tree.unmount());
});
test('account API refuses remote image URLs and registration cannot bypass consent or OTP',async()=>{
 const api=require('../src/authApi.ts'),original=global.fetch;
 try{
  let calls=0;global.fetch=async()=>{calls++;return new Response(JSON.stringify({user:{id:8,username:'synthetic',display_name:'Synthetic'},email_change_allowed:true,photo_url:'https://evil.test/private.jpg'}),{status:200})};
  await assert.rejects(()=>api.getAccount('token'),/fotoğrafı adresi/);
  const values={legal_version:'version',display_name:'Synthetic',username:'synthetic',email:'synthetic@example.test',password:'correct-password',university:'Test',professional_title:'Öğrenci',specialty:'',accept_terms:false,kvkk_informed:true,accept_clinical:true};
  await assert.rejects(()=>api.registerAccount(values),/hukuki metni/);assert.equal(calls,1);
  global.fetch=async()=>new Response(JSON.stringify({access_token:'premature',challenge_token:'code',expires_at:'expiry'}),{status:200});
  await assert.rejects(()=>api.registerAccount({...values,accept_terms:true}),/doğrulanamadı/);
 }finally{global.fetch=original}
});
