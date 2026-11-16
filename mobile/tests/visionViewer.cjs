const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const compile=f=>ts.transpileModule(fs.readFileSync(require.resolve(f),'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const model=require('../src/visionModel.ts'),text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const finding={finding_code:'CARIES',label:'Synthetic caries',confidence:.9,bbox:[.2,.3,.4,.5],fdi:'36'};
test('native viewer scales normalized and pixel XYXY boxes and clips bounds',()=>{const f=model.visionFindings({findings:[finding]})[0];assert.deepEqual(model.visionBox(f,1000,500),{x:200,y:150,width:200,height:100});assert.deepEqual(model.visionBox({...f,box:[-20,100,1200,600]},1000,500),{x:0,y:100,width:1000,height:400});assert.equal(model.visionBox({...f,box:null},1000,500),null)});
test('native vision pools preserve unlocalized findings without inventing boxes and label attention separately',()=>{const list=model.visionFindings({result:{findings:[finding,finding,{label:'Low unsupported',confidence:.2},{label:'Supported low',confidence:.2,fusion_supported:true},{label:'No location'}],gradcam_attention:[{label:'Synthetic attention',bbox:[.1,.2,.3,.4]}]}});assert.equal(list.length,4);assert.equal(list.find(f=>f.label==='No location').box,null);assert.equal(list.find(f=>f.label==='Synthetic attention').attention,true);assert.ok(!list.some(f=>f.label==='Low unsupported'))});
test('invalid geometry and invalid probabilities do not produce misleading overlays',()=>{const list=model.visionFindings({findings:[{label:'Bad probability',confidence:500,bbox:[0,0,10,10]},{label:'Reversed',confidence:.9,bbox:[5,5,3,3]},{label:'String coords',confidence:.9,bbox:['1','2','3','4']}]});assert.equal(list.length,2);assert.ok(list.every(f=>f.box===null))});
function ui(getVision){const exports={},timers=[];let nextTimer=0;const schedule=(fn,delay)=>{const id=++nextTimer;timers.push({id,fn,delay,cancelled:false});return id},cancel=id=>{const timer=timers.find(x=>x.id===id);if(timer)timer.cancelled=true};const native={StyleSheet:{create:x=>x},AppState:{currentState:'active',addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Image','Modal','Pressable','ScrollView','Text','View'].map(x=>[x,x]))};vm.runInNewContext(compile('../src/NativeVisionViewer.tsx'),{exports,Error,setTimeout:schedule,clearTimeout:cancel,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='react-native-svg'?{default:'Svg',Rect:'Rect'}:n==='@react-navigation/native'?{useIsFocused:()=>true}:n==='./visionModel'?model:{getVision,clinicalImage:()=>({uri:'https://example.invalid/synthetic.png',headers:{Authorization:'Bearer synthetic'}})}});exports.default.__timers=timers;return exports.default}
test('native image dimensions drive SVG viewBox and a finding selection highlights its actual region',async()=>{const Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[finding]})}));let t;await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:1,assetId:4,onClose(){}})));await renderer.act(async()=>t.root.findByType('Image').props.onLoad({nativeEvent:{source:{width:1000,height:500}}}));assert.equal(t.root.findByType('Svg').props.viewBox,'0 0 1000 500');const box=t.root.findByType('Rect');assert.equal(box.props.x,200);assert.equal(box.props.y,150);const firstWidth=box.props.strokeWidth;await renderer.act(async()=>box.props.onPress());assert.equal(t.root.findByType('Rect').props.strokeWidth,firstWidth*2);assert.ok(text(t.toJSON()).includes('kesin lezyon sınırı'));await renderer.act(async()=>t.unmount())});
test('unlocalized native finding is shown in list and never represented as an invented rectangle',async()=>{const Component=ui(async()=>({pending:false,findings:model.visionFindings({findings:[{label:'Synthetic unlocalized'}]})}));let t;await renderer.act(async()=>t=renderer.create(React.createElement(Component,{token:'A',analysisId:1,assetId:4,onClose(){}})));await renderer.act(async()=>t.root.findByType('Image').props.onLoad({nativeEvent:{source:{width:1000,height:500}}}));assert.equal(t.root.findAllByType('Rect').length,0);assert.ok(text(t.toJSON()).includes('doğrulanabilir konum bulunmuyor'));await renderer.act(async()=>t.unmount())});


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
