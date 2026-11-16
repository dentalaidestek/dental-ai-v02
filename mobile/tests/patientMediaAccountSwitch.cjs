const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const React=require('react');
const renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;

function mountMedia(getMedia, options={}){
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const native=Object.fromEntries(['ActivityIndicator','FlatList','Image','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]));
 const appStateListeners=options.appStateListeners||new Set();
 native.AppState={addEventListener:(_event,listener)=>{appStateListeners.add(listener);return{remove:()=>appStateListeners.delete(listener)}}};
 native.Alert={alert(...args){options.onAlert?.(...args)}};
 native.FlatList=props=>React.createElement('FlatList',props,...(props.data||[]).map((item,index)=>props.renderItem?.({item,index})),props.ListFooterComponent||null);
 const storage=options.storage||new Map();
 const secureStore=options.secureStore||{
  getItemAsync:async key=>storage.has(key)?storage.get(key):null,
  setItemAsync:async(key,value)=>{storage.set(key,value)},
  deleteItemAsync:async key=>{storage.delete(key)}
 };
 let keySequence=0;
 const exports={};
 vm.runInNewContext(code,{exports,Error,Date,Set,JSON,Number,Array,Promise,require:name=>{
  if(name==='react')return {...React,default:React};
  if(name==='react-native')return native;
  if(name==='@react-navigation/native')return {useIsFocused:()=>options.focused===undefined?true:options.focused};
  if(name==='expo-image-picker')return options.picker||{};
  if(name==='expo-secure-store')return secureStore;
  if(name==='expo-crypto')return {randomUUID:()=>options.randomUUID?.()||`synthetic-media-key-${String(++keySequence).padStart(4,'0')}`};
  if(name==='./socialDraft')return {chunkedDraftStore:raw=>raw};
  if(name==='./clinicalMediaVault')return {
   cleanupStaleClinicalMediaTemps:async()=>{},
   encryptClinicalMediaFile:async(uri,userId,patientId)=>options.onEncrypt?options.onEncrypt(uri,userId,patientId):'file:///documents/dai-clinical-vault/'+userId+'/'+patientId+'/synthetic-media-key-0001.dai',
   decryptClinicalMediaFile:async(uri,userId,patientId,name)=>options.onDecrypt?options.onDecrypt(uri,userId,patientId,name):'file:///cache/dai-clinical-upload-synthetic.png',
   deleteClinicalMediaVaultFile:async uri=>{options.onDeleteVault?.(uri)},
   deleteClinicalMediaTemp:async uri=>{options.onDeleteTemp?.(uri)},
   isClinicalMediaVaultUri:(uri,userId,patientId)=>typeof uri==='string'&&uri.startsWith('file:///documents/dai-clinical-vault/'+userId+'/'+patientId+'/')&&uri.endsWith('.dai'),
   validateClinicalMediaVaultFile:async()=>{}
  };
  if(name==='./api')return {
   getPatientMediaUpload:async(...args)=>options.onReceipt?options.onReceipt(...args):({found:false}),
   uploadPatientMedia:async(...args)=>options.onUpload?options.onUpload(...args):({media:{id:1,original_filename:'synthetic.png',media_type:'PHOTO'},replayed:false})
  };
  if(name==='./modernApi')return {getMedia,analyzeSelectedPatientMedia:async()=>({analysis_id:1}),deleteMedia:async(...args)=>{options.onDelete?.(...args)},deleteAllPatientMedia:async(...args)=>{options.onDelete?.(...args)}};
  if(name==='./realtime')return {useRealtime:()=>({lastEvent:null})};
  if(name==='./NativeAnalysisUpload')return {default:props=>React.createElement('NativeAnalysisUpload',props)};
  throw Error('Unexpected import '+name);
 }});
 const Component=exports.default;
 const Wrapped=props=>React.createElement(Component,{userId:1,...props});
 Wrapped.appStateListeners=appStateListeners;
 return Wrapped;
}
const visible=node=>typeof node==='string'?node:Array.isArray(node)?node.map(visible).join(''):node?.children?node.children.map(visible).join(''):'';
const findButton=(tree,label)=>tree.root.findAllByType('Pressable').find(node=>visible(node).includes(label));
async function press(tree,label){
 const node=findButton(tree,label);assert.ok(node,'missing button: '+label);
 await renderer.act(async()=>{node.props.onPress?.();await new Promise(resolve=>setImmediate(resolve))});
}

test('switching accounts starts a new gallery request while the old request is pending',async()=>{
 let resolveOld;
 const calls=[];
 const Media=mountMedia(async(token,id)=>{
  calls.push([token,id]);
  if(token==='old')return new Promise(resolve=>{resolveOld=resolve});
  return {items:[{id:9,url:'https://example.invalid/new.jpg',media_type:'PHOTO'}],next_before:null};
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis:()=>{}}))});
 assert.deepEqual(calls,[['old',1]]);
 await renderer.act(async()=>{tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis:()=>{}}))});
 assert.deepEqual(calls,[['old',1],['new',2]],'new account must not inherit old loading lock');
 await renderer.act(async()=>{resolveOld({items:[{id:1,url:'https://example.invalid/old.jpg',media_type:'PHOTO'}],next_before:null})});
 const images=tree.root.findAllByType('Image');
 assert.ok(images.some(x=>String(x.props.source?.uri).includes('new.jpg')));
 assert.ok(!images.some(x=>String(x.props.source?.uri).includes('old.jpg')),'stale patient media must never render');
 await renderer.act(async()=>tree.unmount());
});


test('uncertain media deletion blocks repeated destructive requests until reconciliation',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/async function remove\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)return;/);
 assert.match(source,/setUncertain\(true\);setError\(\(e instanceof Error\?e\.message:'Silme durumu doğrulanamadı\.'\)/);
 assert.match(source,/function confirmDelete\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)return;/);
 assert.match(source,/confirmDelete\(preview\.id\),busy\|\|uncertain/);
 assert.match(source,/confirmDelete\(\),busy\|\|uncertain/);
});

test('clinical gallery offers recovery for failed reads and distinguishes empty from error',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/Galeriyi yeniden yükle/);
 assert.match(source,/Bu hastaya ait klinik görsel bulunmuyor/);
 assert.match(source,/!loading&&!!error&&button\('Galeriyi yeniden yükle'/);
 assert.match(source,/!loading&&!error&&items\.length===0/);
 assert.match(source,/confirmDelete\(\),busy\|\|uncertain\|\|visibleItems\.length===0/);
});

test('uncertain media mutations freeze selection and pagination until reconciliation',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/disabled=\{busy\|\|uncertain\} onPress=\{\(\)=>toggle\(item\.id\)\}/);
 assert.match(source,/setSelected\(selected\.length\?\[\]:visibleItems\.slice\(0,4\)\.map\(x=>x\.id\)\)\},busy\|\|uncertain\|\|loadedOwner!==owner/);
 assert.match(source,/onEndReached=\{\(\)=>\{if\(loadedOwner===owner&&cursor&&!loading&&!error&&!uncertain&&!mutation\.current\)/);
});


test('account switch never exposes old patient thumbnails during pending new request',async()=>{
 let resolveNext;
 const Media=mountMedia(async(token)=>token==='old'
  ?{items:[{id:1,url:'https://example.invalid/old.jpg',media_type:'PHOTO'}],next_before:null}
  :new Promise(resolve=>{resolveNext=resolve}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis:()=>{}}))});
 assert.ok(tree.root.findAllByType('Image').some(x=>x.props.source?.uri?.includes('old.jpg')));
 await renderer.act(async()=>{tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis:()=>{}}))});
 assert.ok(!tree.root.findAllByType('Image').some(x=>x.props.source?.uri?.includes('old.jpg')));
 await renderer.act(async()=>{resolveNext({items:[],next_before:null})});
 await renderer.act(async()=>tree.unmount());
});


test('clinical modal and destructive actions require the current loaded account',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/visible=\{open&&loadedOwner===owner\}/);
 assert.match(source,/function confirmDelete\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)return;/);
 assert.match(source,/async function analyze\(\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\|\|!selected\.length\)return;/);
});


test('gallery selection and pagination are restricted to the loaded patient scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/function toggle\(id:number\)\{if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\|\|!visibleItems\.some\(item=>item\.id===id\)\)return;/);
 assert.match(source,/if\(loadedOwner===owner&&cursor&&!loading&&!error&&!uncertain&&!mutation\.current\)/);
});


test('refresh is blocked during unresolved mutation and paging callback observes current scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/if\(loadLock\.current\|\|\(more&&\(mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)\)\)return;/);
 assert.match(source,/onRefresh=\{\(\)=>\{if\(!mutation\.current&&!uncertain&&loadedOwner===owner\)void loader\.current\(\)\}\}/);
 assert.match(source,/\[token,patientId,cursor,uncertain,loadedOwner\]/);
});


test('delayed delete confirmation from previous account cannot delete old patient media',async()=>{
 let confirmation;
 const deletes=[];
 const Media=mountMedia(async()=>({items:[{id:5,url:'https://example.invalid/file',media_type:'PHOTO'}],next_before:null}),{
  onAlert:(_title,_message,buttons)=>{confirmation=buttons.find(button=>button.text==='Sil')},
  onDelete:(...args)=>deletes.push(args)
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis:()=>{}}))});
 const deleteButton=tree.root.findAllByType('Pressable').find(node=>visible(node).includes('Tüm Görselleri Sil'));
 assert.ok(deleteButton,'destructive action should be available for the loaded patient');
 await renderer.act(async()=>deleteButton.props.onPress());
 assert.ok(confirmation,'delete confirmation should be displayed');
 await renderer.act(async()=>tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis:()=>{}})));
 await renderer.act(async()=>{await confirmation.onPress()});
 assert.deepEqual(deletes,[],'stale confirmation must not send a delete request');
 await renderer.act(async()=>tree.unmount());
});


test('every delayed clinical media action verifies the current patient before network mutations',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/async function remove\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/function confirmDelete\(id\?:number\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/async function upload\(\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/async function analyze\(\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/async function pick\(type:'PHOTO'\|'RADIOGRAPH'\)\{\s*if\(!current\(\)\|\|mutation\.current/);
});

test('clinical gallery preview and selection handlers require the current patient scope',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/function toggle\(id:number\)\{if\(!current\(\)\|\|mutation\.current/);
 assert.match(source,/onPress=\{\(\)=>\{if\(!current\(\)\|\|loadedOwner!==owner\|\|mutation\.current\|\|uncertain\)return;setPreview\(item\)/);
 assert.match(source,/onPress=\{\(\)=>\{if\(!current\(\)\|\|loadedOwner!==owner\|\|mutation\.current\|\|uncertain\)return;setOpen\(true\)/);
});

test('picker permission resolving after an account switch cannot open the previous patient picker',async()=>{
 let grant,picks=0;const permission=new Promise(resolve=>{grant=resolve});
 const Media=mountMedia(async()=>({items:[],next_before:null}),{picker:{requestMediaLibraryPermissionsAsync:()=>permission,launchImageLibraryAsync:async()=>{picks++;return{canceled:true}}}});
 let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(Media,{token:'old',patientId:1,onAnalysis(){}})));
 const pick=tree.root.findAllByType('Pressable').find(n=>visible(n).includes('Fotoğraf Ekle'));
 await renderer.act(async()=>{pick.props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>tree.update(React.createElement(Media,{token:'new',patientId:2,onAnalysis(){}})));
 await renderer.act(async()=>{grant({granted:true});await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(picks,0,'stale permission must never open an image picker');await renderer.act(async()=>tree.unmount());
});

test('pending image thumbnails and uploads are scoped to the active patient account',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/const \[pendingOwner,setPendingOwner\]=useState\(''\)/);
 assert.match(source,/setMediaType\(type\);setPendingOwner\(owner\);setPending\(files\)/);
 assert.match(source,/pendingOwner===owner&&pending\.length>0&&<View>/);
 assert.match(source,/pendingOwner!==owner\|\|!pending\.length\)return/);
 assert.match(source,/setPending\(\[\]\);setPendingOwner\(''\);setUncertain\(false\)/);
});


test('failed full refresh clears stale patient images and selection rather than displaying outdated clinical records',async()=>{
 let fail=false;
 const Media=mountMedia(async()=>{
  if(fail)throw Error('offline');
  return {items:[{id:17,url:'https://example.invalid/stale.jpg',media_type:'PHOTO'}],next_before:null};
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'account',patientId:1,onAnalysis:()=>{}}))});
 assert.ok(tree.root.findAllByType('Image').some(x=>x.props.source?.uri?.includes('stale.jpg')));
 fail=true;
 const open=tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityLabel==='Klinik görselleri aç');
 await renderer.act(async()=>open.props.onPress());
 assert.ok(!tree.root.findAllByType('Image').some(x=>x.props.source?.uri?.includes('stale.jpg')),'failed refresh must not retain outdated thumbnails');
 assert.match(visible(tree.root),/offline/);
 await renderer.act(async()=>tree.unmount());
});


test('failed older gallery page retains verified images and cursor for an explicit retry',async()=>{
 let fail=true;const cursors=[];
 const Media=mountMedia(async(_token,_patient,before)=>{cursors.push(before);if(before){if(fail)throw Error('offline');return{items:[{id:4,url:'https://example.invalid/older.jpg',media_type:'PHOTO'}],next_before:null}}return{items:[{id:9,url:'https://example.invalid/recent.jpg',media_type:'PHOTO'}],next_before:5}});
 let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(Media,{token:'account',patientId:1,onAnalysis(){}})));
 await renderer.act(async()=>tree.root.findAllByType('Pressable').find(n=>n.props.accessibilityLabel==='Klinik görselleri aç').props.onPress());
 await renderer.act(async()=>tree.root.findByType('FlatList').props.onEndReached());
 assert.equal(tree.root.findByType('FlatList').props.data[0].id,9);assert.equal(cursors.at(-1),5);assert.match(visible(tree.root),/offline/);
 fail=false;await renderer.act(async()=>tree.root.findByType('FlatList').props.ListFooterComponent.props.onPress());
 assert.deepEqual(Array.from(tree.root.findByType('FlatList').props.data,x=>x.id),[9,4]);assert.equal(cursors.at(-1),5);await renderer.act(async()=>tree.unmount());
});

test('bulk analysis selection is limited to four and rejects stale patient actions',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/İlk 4 Görseli Seç/);
 assert.match(source,/if\(!current\(\)\|\|mutation\.current\|\|uncertain\|\|loadedOwner!==owner\)return;setSelected\(selected\.length\?\[\]:visibleItems\.slice\(0,4\)\.map\(x=>x\.id\)\)/);
});


test('photo picker results are invalidated when patient scope changes even if the user returns',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/pickerGeneration=useRef\(0\)/);
 assert.match(source,/const picker=\+\+pickerGeneration\.current/);
 assert.match(source,/mounted\.current=true;request\.current\+\+;pickerGeneration\.current\+\+/);
 assert.match(source,/mounted\.current=false;request\.current\+\+;pickerGeneration\.current\+\+/);
 assert.match(source,/picker!==pickerGeneration\.current\|\|mutation\.current\|\|uncertain\|\|result\.canceled/);
});

test('full gallery refresh invalidates preview and zoom on success and failure',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/setError\(''\);if\(!more\)\{setSelected\(\[\]\);setPreview\(null\);setZoom\(1\)\}/);
 assert.match(source,/if\(!more\)\{setItems\(\[\]\);setCursor\(null\);setSelected\(\[\]\);setPreview\(null\);setZoom\(1\)\}/);
});

test('selected-media analysis UI carries optional FDI and clinical notes',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/accessibilityLabel="Klinik görsel analizi FDI diş numarası"/);
 assert.match(source,/accessibilityLabel="Klinik görsel analizi klinik bilgisi"/);
 assert.match(source,/setComposeIds\(\[\.\.\.selected\]\)/);
 assert.match(source,/existingMediaIds=\{composeIds\}/);
 assert.match(source,/initialToothNumber=\{composeTooth\}/);
 assert.match(source,/initialClinicalNotes=\{composeNotes\}/);
 assert.match(source,/maxLength=\{4000\} multiline placeholder="Şikâyet, anamnez ve klinik bulgular"/);
});

function loadModernApi(fetchImpl){
 const source=fs.readFileSync(require.resolve('../src/modernApi.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 class ApiError extends Error{constructor(status,message){super(message);this.status=status}}
 const exports={};
 vm.runInNewContext(code,{
  exports,fetch:fetchImpl,AbortController,FormData,URLSearchParams,Response,
  setTimeout,clearTimeout,
  require:name=>name==='./api'?{ApiError}:name==='./sessionExpiry'?{revalidateSession:async()=>{}}:name==='./chatFiles'?{validateChatFile:()=>{}}:(()=>{throw Error('Unexpected import '+name)})()
 });
 return exports;
}

test('selected-media analysis sends FDI and clinical notes to the canonical mobile endpoint',async()=>{
 let request;
 const api=loadModernApi(async(url,init)=>{request={url,init};return new Response(JSON.stringify({ok:true,analysis_id:42}),{status:200,headers:{'Content-Type':'application/json'}})});
 const result=await api.analyzeSelectedPatientMedia('synthetic-token',8,[21,22],'36','Soğukta kısa süreli ağrı.');
 assert.equal(result.analysis_id,42);
 assert.equal(request.url,'https://dentalai.tr/api/mobile/v1/patients/8/media/analyze');
 assert.deepEqual(JSON.parse(request.init.body),{media_ids:[21,22],tooth_number:'36',clinical_notes:'Soğukta kısa süreli ağrı.'});
 assert.equal(request.init.credentials,'omit');
});

test('selected-media analysis rejects oversized clinical context before network access',async()=>{
 let calls=0;const api=loadModernApi(async()=>{calls++;return new Response('{}',{status:200})});
 await assert.rejects(()=>api.analyzeSelectedPatientMedia('token',8,[21],'12345678901',''));
 await assert.rejects(()=>api.analyzeSelectedPatientMedia('token',8,[21],'36','x'.repeat(4001)));
 assert.equal(calls,0,'invalid clinical context must be rejected before sending patient data');
});

test('saved gallery selection opens the same durable composer used for new analysis images',async()=>{
 const Media=mountMedia(async()=>({items:[{id:21,url:'https://example.invalid/saved-21.png',media_type:'RADIOGRAPH'},{id:22,url:'https://example.invalid/saved-22.png',media_type:'PHOTO'}],next_before:null}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'account-token',userId:77,patientId:8,onAnalysis:()=>{}}))});
 const open=tree.root.findAllByType('Pressable').find(n=>n.props.accessibilityLabel==='Klinik görselleri aç');
 await renderer.act(async()=>open.props.onPress());
 const checks=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox'&&visible(n).includes('Analiz için seç'));
 assert.equal(checks.length,2);
 await renderer.act(async()=>checks[0].props.onPress());
 const checksAgain=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox'&&visible(n).includes('Analiz için seç'));
 await renderer.act(async()=>checksAgain[1].props.onPress());
 const analyze=tree.root.findAllByType('Pressable').find(n=>visible(n).includes('Seçilenleri AI ile Analiz Et'));
 assert.ok(analyze);
 await renderer.act(async()=>analyze.props.onPress());
 const composer=tree.root.findByType('NativeAnalysisUpload');
 assert.equal(composer.props.token,'account-token');
 assert.equal(composer.props.userId,77);
 assert.equal(composer.props.patientId,8);
 assert.deepEqual(Array.from(composer.props.existingMediaIds),[21,22]);
 await renderer.act(async()=>tree.unmount());
});

test('account switch closes a mixed analysis composer and clears prior saved-media selection',async()=>{
 const Media=mountMedia(async(_token,id)=>({items:[{id:id===8?21:31,url:'https://example.invalid/'+id+'.png',media_type:'PHOTO'}],next_before:null}));
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'old',userId:1,patientId:8,onAnalysis:()=>{}}))});
 await renderer.act(async()=>tree.root.findAllByType('Pressable').find(n=>n.props.accessibilityLabel==='Klinik görselleri aç').props.onPress());
 const check=tree.root.findAllByType('Pressable').find(n=>n.props.accessibilityRole==='checkbox'&&visible(n).includes('Analiz için seç'));
 await renderer.act(async()=>check.props.onPress());
 const analyze=tree.root.findAllByType('Pressable').find(n=>visible(n).includes('Seçilenleri AI ile Analiz Et'));
 await renderer.act(async()=>analyze.props.onPress());
 assert.equal(tree.root.findAllByType('NativeAnalysisUpload').length,1);
 await renderer.act(async()=>tree.update(React.createElement(Media,{token:'new',userId:2,patientId:9,onAnalysis:()=>{}})));
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(tree.root.findAllByType('NativeAnalysisUpload').length,0);
 await renderer.act(async()=>tree.unmount());
});



test('clinical media upload persists its receipt key before transfer and displays byte progress',async()=>{
 const storage=new Map(),uploadCalls=[],receiptCalls=[];let finishUpload;
 const picker={requestMediaLibraryPermissionsAsync:async()=>({granted:true}),launchImageLibraryAsync:async()=>({canceled:false,assets:[{uri:'file:///synthetic-clinical.png',fileName:'synthetic-clinical.png',mimeType:'image/png',fileSize:1024}]})};
 const Media=mountMedia(async()=>({items:[],next_before:null}),{
  storage,picker,
  onReceipt:async(_token,patientId,key)=>{receiptCalls.push([patientId,key]);return {found:false}},
  onUpload:async(_token,patientId,file,_tooth,mediaType,key,onProgress)=>{
   uploadCalls.push([patientId,file.name,mediaType,key]);
   assert.ok(storage.has('dai.patient-media.upload.1.8'),'upload intent must be persisted before network transfer');
   onProgress({loaded:512,total:1024,lengthComputable:true});
   await new Promise(resolve=>{finishUpload=resolve});
   return {media:{id:88,original_filename:file.name,media_type:mediaType},replayed:false};
  }
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'token',patientId:8,onAnalysis:()=>{}}));await new Promise(resolve=>setImmediate(resolve))});
 await press(tree,'Fotoğraf Ekle');
 await press(tree,'Kaydet');
 assert.ok(finishUpload,'upload should start after receipt lookup');
 assert.match(visible(tree.toJSON()),/50%/);
 const intent=JSON.parse(storage.get('dai.patient-media.upload.1.8'));
 assert.equal(intent.version,1);assert.equal(intent.userId,1);assert.equal(intent.patientId,8);
 assert.equal(intent.files.length,1);assert.match(intent.files[0].requestKey,/^[A-Za-z0-9_-]{16,96}$/);
 assert.deepEqual(receiptCalls,[[8,intent.files[0].requestKey]]);
 assert.deepEqual(uploadCalls,[[8,'synthetic-clinical.png','PHOTO',intent.files[0].requestKey]]);
 await renderer.act(async()=>{finishUpload();await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(storage.has('dai.patient-media.upload.1.8'),false);
 assert.match(visible(tree.toJSON()),/1 görüntü kaydedildi/);
 await renderer.act(async()=>tree.unmount());
});

test('process-death recovery reconciles a server receipt before attempting another upload',async()=>{
 const storage=new Map(),key='synthetic-media-recovery-0001';let uploads=0;const receipts=[];
 storage.set('dai.patient-media.upload.1.8',JSON.stringify({version:1,userId:1,patientId:8,mediaType:'RADIOGRAPH',updatedAt:Date.now(),files:[{uri:'file:///restored.png',name:'restored.png',type:'image/png',requestKey:key}]}));
 const Media=mountMedia(async()=>({items:[],next_before:null}),{
  storage,
  onReceipt:async(_token,patientId,requestKey)=>{receipts.push([patientId,requestKey]);return {found:true,media:{id:91,original_filename:'restored.png',media_type:'RADIOGRAPH'}}},
  onUpload:async()=>{uploads++;throw Error('must not upload a receipt already present on server')}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'token',patientId:8,onAnalysis:()=>{}}));await new Promise(resolve=>setImmediate(resolve))});
 assert.match(visible(tree.toJSON()),/Önceki oturumdan 1 bekleyen klinik görüntü bulundu/);
 await press(tree,'Kaydet');
 assert.deepEqual(receipts,[[8,key]]);
 assert.equal(uploads,0);
 assert.equal(storage.has('dai.patient-media.upload.1.8'),false);
 await renderer.act(async()=>tree.unmount());
});

test('uncertain upload resumes with the same request key and never blindly duplicates media',async()=>{
 const storage=new Map(),receiptKeys=[];let uploads=0;
 const picker={requestMediaLibraryPermissionsAsync:async()=>({granted:true}),launchImageLibraryAsync:async()=>({canceled:false,assets:[{uri:'file:///retry.png',fileName:'retry.png',mimeType:'image/png',fileSize:100}]})};
 const Media=mountMedia(async()=>({items:[],next_before:null}),{
  storage,picker,
  onReceipt:async(_token,_patientId,key)=>{receiptKeys.push(key);return {found:receiptKeys.length>1}},
  onUpload:async()=>{uploads++;throw Error('response lost after transfer')}
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'token',patientId:8,onAnalysis:()=>{}}));await new Promise(resolve=>setImmediate(resolve))});
 await press(tree,'Fotoğraf Ekle');
 await press(tree,'Kaydet');
 assert.equal(uploads,1);
 assert.ok(storage.has('dai.patient-media.upload.1.8'));
 await press(tree,'Bekleyen yüklemeyi güvenle doğrula');
 assert.equal(uploads,1,'server receipt must suppress a duplicate transfer');
 assert.equal(receiptKeys.length,2);
 assert.equal(receiptKeys[0],receiptKeys[1]);
 assert.equal(storage.has('dai.patient-media.upload.1.8'),false);
 await renderer.act(async()=>tree.unmount());
});

test('clinical media upload is blocked when SecureStore cannot persist the intent',async()=>{
 const picker={requestMediaLibraryPermissionsAsync:async()=>({granted:true}),launchImageLibraryAsync:async()=>({canceled:false,assets:[{uri:'file:///not-persisted.png',fileName:'not-persisted.png',mimeType:'image/png',fileSize:100}]})};
 let uploads=0;
 const secureStore={getItemAsync:async()=>null,setItemAsync:async()=>{throw Error('secure store unavailable')},deleteItemAsync:async()=>{}};
 const Media=mountMedia(async()=>({items:[],next_before:null}),{secureStore,picker,onUpload:async()=>{uploads++}});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'token',patientId:8,onAnalysis:()=>{}}));await new Promise(resolve=>setImmediate(resolve))});
 await press(tree,'Fotoğraf Ekle');
 assert.match(visible(tree.toJSON()),/secure store unavailable/);
 assert.equal(uploads,0);
 await renderer.act(async()=>tree.unmount());
});

test('pending clinical media drafts are isolated by user and patient identity',async()=>{
 const storage=new Map();
 storage.set('dai.patient-media.upload.1.8',JSON.stringify({version:1,userId:1,patientId:8,mediaType:'PHOTO',updatedAt:Date.now(),files:[{uri:'file:///private.png',name:'private.png',type:'image/png',requestKey:'synthetic-private-media-0001'}]}));
 const Media=mountMedia(async()=>({items:[],next_before:null}),{storage});
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'other-account',userId:2,patientId:8,onAnalysis:()=>{}}));await new Promise(resolve=>setImmediate(resolve))});
 assert.doesNotMatch(visible(tree.toJSON()),/Önceki oturumdan 1 bekleyen klinik görüntü bulundu/);
 assert.equal(storage.has('dai.patient-media.upload.1.8'),true);
 await renderer.act(async()=>tree.unmount());
});

test('new patient media drafts persist ciphertext only and upload through a disposable plaintext file',async()=>{
 const storage=new Map(),encryptedUri='file:///documents/dai-clinical-vault/1/8/synthetic-media-key-0001.dai',tempUri='file:///cache/dai-clinical-upload-synthetic.png',uploaded=[],deletedVault=[],deletedTemp=[],encrypted=[];
 const picker={requestMediaLibraryPermissionsAsync:async()=>({granted:true}),launchImageLibraryAsync:async()=>({canceled:false,assets:[{uri:'file:///picker/private-clinical.png',fileName:'private-clinical.png',mimeType:'image/png',fileSize:1024}]})};
 const Media=mountMedia(async()=>({items:[],next_before:null}),{
  storage,picker,
  onEncrypt:async(uri,userId,patientId)=>{encrypted.push({uri,userId,patientId});return encryptedUri},
  onDecrypt:async(uri,userId,patientId,name)=>{assert.equal(uri,encryptedUri);assert.equal(userId,1);assert.equal(patientId,8);assert.equal(name,'private-clinical.png');return tempUri},
  onUpload:async(...args)=>{uploaded.push(args);return{media:{id:91,original_filename:'private-clinical.png',media_type:'PHOTO'},replayed:false}},
  onDeleteVault:uri=>deletedVault.push(uri),
  onDeleteTemp:uri=>deletedTemp.push(uri)
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,{token:'account-a',patientId:8,onAnalysis:()=>{}}))});
 await press(tree,'▧ Fotoğraf Ekle');
 const raw=JSON.parse(storage.get('dai.patient-media.upload.1.8'));
 assert.equal(raw.version,2);
 assert.equal(raw.files[0].uri,encryptedUri);
 assert.equal(raw.files[0].encryptedUri,encryptedUri);
 assert.ok(!JSON.stringify(raw).includes('file:///picker/private-clinical.png'),'picker cache URI must not be persisted');
 await press(tree,'Kaydet');
 assert.equal(encrypted.length,1);
 assert.equal(uploaded.length,1);
 assert.equal(uploaded[0][2].uri,tempUri,'multipart upload receives only a short-lived decrypted file');
 assert.deepEqual(deletedTemp,[tempUri]);
 assert.deepEqual(deletedVault,[encryptedUri]);
 assert.equal(storage.has('dai.patient-media.upload.1.8'),false);
 await renderer.act(async()=>tree.unmount());
});


test('clinical gallery refreshes on focus and app foreground without polling',async()=>{
 const listeners=new Set(),calls=[];const options={appStateListeners:listeners,focused:true};
 const Media=mountMedia(async()=>{calls.push(calls.length+1);return{items:[{id:calls.length,url:'https://example.invalid/gallery-'+calls.length+'.jpg',media_type:'PHOTO'}],next_before:null}},options);
 const props={token:'account',patientId:8,onAnalysis:()=>{}};let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Media,props))});
 assert.equal(calls.length,1,'mount performs one initial gallery read');
 assert.equal(listeners.size,1,'focused gallery subscribes to app state');
 const listener=[...listeners][0];
 await renderer.act(async()=>listener('background'));
 assert.equal(calls.length,1,'background transition does not trigger a request');
 await renderer.act(async()=>listener('active'));
 assert.equal(calls.length,2,'foreground return refreshes the canonical gallery');
 options.focused=false;
 await renderer.act(async()=>tree.update(React.createElement(Media,props)));
 assert.equal(listeners.size,0,'blur removes the app-state listener');
 const beforeFocus=calls.length;
 options.focused=true;
 await renderer.act(async()=>tree.update(React.createElement(Media,props)));
 assert.equal(calls.length,beforeFocus+1,'returning to the patient screen refreshes the gallery');
 assert.equal(listeners.size,1);
 await renderer.act(async()=>tree.unmount());
 assert.equal(listeners.size,0,'unmount removes the app-state listener');
});
