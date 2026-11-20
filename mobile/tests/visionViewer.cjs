const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const compile=f=>ts.transpileModule(fs.readFileSync(require.resolve(f),'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const model=require('../src/visionModel.ts'),text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const finding={finding_code:'CARIES',label:'Synthetic caries',confidence:.9,bbox:[.2,.3,.4,.5],fdi:'36'};
test('native viewer scales normalized and pixel XYXY boxes and clips bounds',()=>{const f=model.visionFindings({findings:[finding]},'PANORAMIC')[0];assert.deepEqual(model.visionBox(f,1000,500),{x:200,y:150,width:200,height:100});assert.deepEqual(model.visionBox({...f,box:[-20,100,1200,600]},1000,500),{x:0,y:100,width:1000,height:400});assert.equal(model.visionBox({...f,box:null},1000,500),null)});
test('native vision pools preserve unlocalized findings without inventing boxes and label attention separately',()=>{const list=model.visionFindings({result:{findings:[finding,finding,{label:'Low unsupported',confidence:.2},{label:'Supported low',confidence:.2,fusion_supported:true},{label:'No location'}],gradcam_attention:[{label:'Synthetic attention',bbox:[.1,.2,.3,.4]}]}},'PANORAMIC');assert.equal(list.length,4);assert.equal(list.find(f=>f.label==='No location').box,null);assert.equal(list.find(f=>f.label==='Synthetic attention').attention,true);assert.ok(!list.some(f=>f.label==='Low unsupported'))});
test('invalid geometry and invalid probabilities do not produce misleading overlays',()=>{const list=model.visionFindings({findings:[{label:'Bad probability',confidence:500,bbox:[0,0,10,10]},{label:'Reversed',confidence:.9,bbox:[5,5,3,3]},{label:'String coords',confidence:.9,bbox:['1','2','3','4']}]},'PANORAMIC');assert.equal(list.length,2);assert.ok(list.every(f=>f.box===null))});
test('Grad-CAM attention matches the web modality pools',()=>{
 const snapshot={findings:[finding],gradcam_attention:[{label:'Synthetic radiographic attention',bbox:[.1,.2,.3,.4]}]};
 const panoramic=model.visionFindings(snapshot,'PANORAMIC');
 const bitewing=model.visionFindings(snapshot,'BITEWING');
 const intraoral=model.visionFindings(snapshot,'INTRAORAL_PHOTO');
 const unknown=model.visionFindings(snapshot,'UNKNOWN');
 assert.ok(panoramic.some(item=>item.attention));
 assert.ok(bitewing.some(item=>item.attention));
 assert.ok(!intraoral.some(item=>item.attention));
 assert.ok(!unknown.some(item=>item.attention));
 assert.ok(!model.visionFindings(snapshot).some(item=>item.attention),'missing modality fails closed');
});
function ui(getVision,onScrollTo=()=>{}){const exports={},timers=[];let nextTimer=0;const schedule=(fn,delay)=>{const id=++nextTimer;timers.push({id,fn,delay,cancelled:false});return id},cancel=id=>{const timer=timers.find(x=>x.id===id);if(timer)timer.cancelled=true};const ScrollView=React.forwardRef((props,ref)=>{React.useImperativeHandle(ref,()=>({scrollTo:onScrollTo}));return React.createElement('ScrollView',props,props.children)});const native={StyleSheet:{create:x=>x},AppState:{currentState:'active',addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Image','Modal','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};native.ScrollView=ScrollView;vm.compileFunction(compile('../src/NativeVisionViewer.tsx'),['exports','require','Error','setTimeout','clearTimeout'])(exports,n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='react-native-svg'?{default:'Svg',Rect:'Rect'}:n==='@react-navigation/native'?{useIsFocused:()=>true}:n==='./visionModel'?model:{getVision,clinicalImage:()=>({uri:'https://example.invalid/synthetic.png',headers:{Authorization:'Bearer synthetic'}})},Error,schedule,cancel);exports.default.__timers=timers;return exports.default}
test('native findings match web fallback descriptions without inventing an image region',()=>{const list=model.visionFindings({findings:[{finding_code:'CARIES',label:'Çürük şüphesi',confidence:.9,fdi:'36',surface:'O'},{label:'Unlocalized finding',confidence:null},{label:'Long description',confidence:.9,description:'x'.repeat(5000)}]},'INTRAORAL_PHOTO');assert.equal(list[0].description,'Çürük şüphesi 36 numaralı diş ile ilişkilendirilmiştir. İlgili yüzey: O.');assert.equal(list[1].description,'Unlocalized finding');assert.equal(list[1].box,null);assert.equal(list[2].description.length,4000)});

test('selecting a native finding returns to the image so its overlay is visible',async()=>{const scrolls=[],Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[finding]},'PANORAMIC')}),value=>scrolls.push(value));let t;await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:21,assetId:4,onClose(){}})));await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});const card=t.root.findAllByType('Pressable').find(node=>node.props.accessibilityRole==='button'&&text(node).includes('Synthetic caries'));assert.ok(card);await renderer.act(async()=>card.props.onPress());assert.equal(scrolls.length,1);assert.equal(scrolls[0].y,0);assert.equal(scrolls[0].animated,true);const selectedCard=t.root.findAllByType('Pressable').find(node=>node.props.accessibilityRole==='button'&&text(node).includes('Synthetic caries'));assert.ok(selectedCard.props.accessibilityHint.includes('görüntü'));await renderer.act(async()=>t.unmount())});

test('native image dimensions drive SVG viewBox and a finding selection highlights its actual region',async()=>{const Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[finding]},'PANORAMIC')}));let t;await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:1,assetId:4,onClose(){}})));await renderer.act(async()=>t.root.findByType('Image').props.onLoad({nativeEvent:{source:{width:1000,height:500}}}));assert.equal(t.root.findByType('Svg').props.viewBox,'0 0 1000 500');const box=t.root.findByType('Rect');assert.equal(box.props.x,200);assert.equal(box.props.y,150);const firstWidth=box.props.strokeWidth;await renderer.act(async()=>box.props.onPress());assert.equal(t.root.findByType('Rect').props.strokeWidth,firstWidth*2);assert.ok(text(t.toJSON()).includes('kesin lezyon sınırı'));await renderer.act(async()=>t.unmount())});
test('unlocalized native finding is shown in list and never represented as an invented rectangle',async()=>{const Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[{label:'Synthetic unlocalized'}]},'INTRAORAL_PHOTO')}));let t;await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:1,assetId:4,onClose(){}})));await renderer.act(async()=>t.root.findByType('Image').props.onLoad({nativeEvent:{source:{width:1000,height:500}}}));assert.equal(t.root.findAllByType('Rect').length,0);assert.ok(text(t.toJSON()).includes('doğrulanabilir konum bulunmuyor'));await renderer.act(async()=>t.unmount())});


test('pending vision polling backs off exponentially and does not schedule overlapping requests',async()=>{
 let calls=0;const Component=ui(async()=>{calls++;return{pending:true,findings:[]}});let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:1,assetId:4,onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 const first=Component.__timers.find(x=>x.delay===10000&&!x.cancelled);
 assert.ok(first,'first pending poll waits ten seconds after initial pending response');
 await renderer.act(async()=>{first.fn();await new Promise(r=>setImmediate(r))});
 assert.ok(Component.__timers.some(x=>x.delay===20000&&!x.cancelled),'second pending poll backs off to twenty seconds');
 assert.equal(calls,2);
 await renderer.act(async()=>t.unmount());
});


test('native viewer passes the selected asset modality to the canonical vision parser',async()=>{
 let received=null;const Component=ui(async(...args)=>{received=args;return{pending:false,findings:[]}});let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:1,assetId:4,assets:[{id:4,name:'intraoral.png',image_type:'INTRAORAL_PHOTO'}],onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 assert.deepEqual(received,['A',1,4,'INTRAORAL_PHOTO']);
 await renderer.act(async()=>t.unmount());
});

test('native viewer switches between authorized assets using web modality labels without a new asset-list request',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]})),selected=[];
 const assets=[{id:4,name:'bitewing.png',image_type:'BITEWING'},{id:5,name:'intraoral.png',image_type:'INTRAORAL_PHOTO'}];
 let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:12,assetId:4,assets,onSelectAsset:id=>selected.push(id),onClose(){}})));
 const rendered=text(t.toJSON());
 assert.ok(rendered.includes('Analiz #12 · Bitewing · Görüntü #4'));
 assert.ok(rendered.includes('1 · Bitewing'));
 assert.ok(rendered.includes('2 · Ağız içi'));
 const next=t.root.findAllByType('Pressable').find(node=>text(node).includes('2 · Ağız içi'));
 assert.ok(next);
 await renderer.act(async()=>next.props.onPress());
 assert.deepEqual(selected,[5]);
 await renderer.act(async()=>t.unmount());
});


const findPressable=(root,label)=>root.findAllByType('Pressable').find(node=>text(node)===label);
test('native viewer exposes the same three clinical tabs as the web viewer',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]}));let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:7,assetId:4,onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 for(const label of ['Bulgular','Tedavi','Klinik Bilgi'])assert.ok(findPressable(t.root,label),label+' tab is present');
 await renderer.act(async()=>findPressable(t.root,'Klinik Bilgi').props.onPress());
 assert.ok(text(t.toJSON()).includes('Diş Şeması / Klinik Bilgi'));
 await renderer.act(async()=>t.unmount());
});

test('treatment tab preselects only supported permanent FDI findings and delegates to canonical parent job',async()=>{
 const Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[finding,{...finding,label:'Primary tooth finding',fdi:'55'}]},'PANORAMIC')})),calls=[];let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:8,assetId:4,onRunTreatmentAnalysis:async teeth=>{calls.push(teeth);return true},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Tedavi').props.onPress());
 assert.ok(text(t.toJSON()).includes('36'));
 assert.ok(!text(t.toJSON()).includes('55'));
 await renderer.act(async()=>findPressable(t.root,'Analiz Et').props.onPress());
 assert.deepEqual(calls,[['36']]);
 assert.ok(text(t.toJSON()).includes('Tedavi değerlendirmesi başlatıldı'));
 await renderer.act(async()=>t.unmount());
});

test('clinical information tab saves through the supplied durable parent callback and clears only after confirmation',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]})),saved=[];let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:9,assetId:4,onSaveClinicalNote:async value=>{saved.push(value);return true},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Klinik Bilgi').props.onPress());
 const tooth=findPressable(t.root,'36');
 await renderer.act(async()=>tooth.props.onPress());
 const findingInput=t.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Manuel bulgu');
 const noteInput=t.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Klinik not');
 await renderer.act(async()=>{findingInput.props.onChangeText('Restorasyon kenarında açıklık');noteInput.props.onChangeText('Klinik kontrol önerildi.')});
 await renderer.act(async()=>findPressable(t.root,'Onayla').props.onPress());
 assert.deepEqual(saved,[{tooth:'36',finding:'Restorasyon kenarında açıklık',note:'Klinik kontrol önerildi.'}]);
 const after=t.root.findAllByType('TextInput');
 assert.ok(after.every(node=>node.props.value===''));
 assert.ok(text(t.toJSON()).includes('sunucuda doğrulandı'));
 await renderer.act(async()=>t.unmount());
});

test('uncertain clinical-note acknowledgement preserves native inputs and does not auto-resubmit',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]})),saved=[];let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:10,assetId:4,onSaveClinicalNote:async value=>{saved.push(value);return false},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Klinik Bilgi').props.onPress());
 const input=t.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Klinik not');
 await renderer.act(async()=>input.props.onChangeText('Bekleyen klinik not'));
 await renderer.act(async()=>findPressable(t.root,'Klinik Notu Kaydet').props.onPress());
 assert.equal(saved.length,1);
 assert.equal(t.root.findAllByType('TextInput').find(node=>node.props.accessibilityLabel==='Klinik not').props.value,'Bekleyen klinik not');
 assert.ok(text(t.toJSON()).includes('Girişleriniz korundu'));
 await renderer.act(async()=>t.unmount());
});

test('treatment tab renders the canonical result and only offers retry for retryable preliminary jobs',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]}));let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:11,assetId:4,clinicalResult:{status:'INITIAL',treatment_options:[{title:'Restorasyon değerlendirmesi',description:'Klinik muayene ile doğrulanmalı.'}]},clinicalJob:{id:77,kind:'PRELIMINARY',status:'DONE',retryable:false},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Tedavi').props.onPress());
 assert.ok(text(t.toJSON()).includes('Restorasyon değerlendirmesi'));
 assert.ok(text(t.toJSON()).includes('Klinik muayene ile doğrulanmalı.'));
 assert.equal(findPressable(t.root,'Analiz Et'),undefined,'completed treatment must not expose a second paid analysis action');
 await renderer.act(async()=>t.unmount());
});


test('failed retryable clinical job exposes retry instead of a duplicate new treatment request',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]})),retries=[];let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:12,assetId:4,clinicalJob:{id:88,kind:'VISION',status:'FAILED',retryable:true},onRunTreatmentAnalysis:async()=>{throw Error('must not start a new analysis')},onRetryTreatmentAnalysis:async()=>{retries.push(88);return true},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Tedavi').props.onPress());
 assert.ok(findPressable(t.root,'Analiz tamamlanamadı — yeniden dene'));
 assert.equal(findPressable(t.root,'Analiz Et'),undefined);
 await renderer.act(async()=>findPressable(t.root,'Analiz tamamlanamadı — yeniden dene').props.onPress());
 assert.deepEqual(retries,[88]);
 await renderer.act(async()=>t.unmount());
});

test('pending parent note and busy state lock chart writes before the callback',async()=>{
 const Component=ui(async()=>({pending:false,findings:[]})),saved=[];let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:13,assetId:4,notePending:true,parentBusy:false,onSaveClinicalNote:async value=>{saved.push(value);return true},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Klinik Bilgi').props.onPress());
 const save=findPressable(t.root,'Klinik Notu Kaydet');
 assert.equal(save.props.disabled,true);
 assert.ok(t.root.findAllByType('TextInput').every(node=>node.props.editable===false));
 assert.equal(findPressable(t.root,'36').props.disabled,true);
 assert.ok(text(t.toJSON()).includes('Bekleyen hekim notu ana klinik ekranda doğrulanmadan'));
 assert.equal(saved.length,0);
 await renderer.act(async()=>t.unmount());
});


test('parent mutation lock disables treatment selection and prevents a duplicate submit',async()=>{
 const Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[finding]},'PANORAMIC')})),calls=[];let t;
 await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:14,assetId:4,parentBusy:true,onRunTreatmentAnalysis:async teeth=>{calls.push(teeth);return true},onClose(){}})));
 await renderer.act(async()=>{await new Promise(r=>setImmediate(r))});
 await renderer.act(async()=>findPressable(t.root,'Tedavi').props.onPress());
 assert.equal(findPressable(t.root,'36').props.disabled,true);
 assert.equal(findPressable(t.root,'Analiz Et').props.disabled,true);
 assert.equal(calls.length,0);
 await renderer.act(async()=>t.unmount());
});

test('switching assets during an in-flight vision request discards stale findings and loads the latest asset',async()=>{
 const requests=[];
 const Component=ui((token,analysis,asset,modality)=>new Promise(resolve=>requests.push({token,analysis,asset,modality,resolve})));
 const assets=[{id:4,name:'bitewing.png',image_type:'BITEWING'},{id:5,name:'intraoral.png',image_type:'INTRAORAL_PHOTO'}];
 function Host(){const [assetId,setAssetId]=React.useState(4);return React.createElement(Component,{token:'A',analysisId:12,assetId,assets,onSelectAsset:setAssetId,onClose(){}})}
 let t;
 await renderer.act(async()=>{t=renderer.create(React.createElement(Host));await new Promise(r=>setImmediate(r))});
 assert.equal(requests.length,1);
 assert.equal(requests[0].asset,4);
 const oldImageLoad=t.root.findByType('Image').props.onLoad;
 await renderer.act(async()=>oldImageLoad({nativeEvent:{source:{width:1200,height:800}}}));
 const next=t.root.findAllByType('Pressable').find(node=>text(node).includes('2 · Ağız içi'));
 assert.ok(next);
 await renderer.act(async()=>{next.props.onPress();await new Promise(r=>setImmediate(r))});
 assert.equal(requests.length,1,'the second asset waits for the in-flight request lock');
 await renderer.act(async()=>oldImageLoad({nativeEvent:{source:{width:1200,height:800}}}));
 assert.equal(t.root.findAllByType('Svg').length,0,'old image dimensions cannot be reused for the newly selected asset');
 await renderer.act(async()=>{
  requests[0].resolve({pending:false,findings:[{id:'old',label:'Old asset result',category:'Diğer',tooth:null,surface:null,attention:false,confidence:.9,box:null,description:'stale'}]});
  await new Promise(r=>setImmediate(r));
 });
 assert.equal(requests.length,2,'latest asset is fetched after the old request settles');
 assert.equal(requests[1].asset,5);
 assert.equal(requests[1].modality,'INTRAORAL_PHOTO');
 assert.ok(!text(t.toJSON()).includes('Old asset result'),'stale response is not rendered under another image');
 await renderer.act(async()=>{
  requests[1].resolve({pending:false,findings:[{id:'new',label:'Current asset result',category:'Diğer',tooth:null,surface:null,attention:false,confidence:.9,box:null,description:'current'}]});
  await new Promise(r=>setImmediate(r));
 });
 assert.ok(text(t.toJSON()).includes('Current asset result'));
 await renderer.act(async()=>t.unmount());
});


test('web radiograph and intraoral viewers preselect only permanent FDI teeth like native',()=>{
 for(const file of ['radiograph_viewer.js','intraoral_viewer.js']){
  const source=fs.readFileSync(require.resolve('../../vision_service/templates/'+file),'utf8');
  const start=source.indexOf('const teeth=['),end=source.indexOf(';panel.innerHTML',start);
  assert.ok(start>=0&&end>start,file+' treatment selection block exists');
  const snippet=source.slice(start,end);
  const select=new Function('findings',snippet+';return [...selected]');
  const selected=select(()=>[
   {fdi:'36'},
   {tooth_id:'11'},
   {tooth:'55'},
   {fdi:'3A'},
   {fdi:'18'},
  ]);
  assert.deepEqual(selected.sort(),['11','18','36']);
  assert.ok(!snippet.includes('\\\\d{2}'),'viewer must not use the escaped digit matcher');
 }
});
