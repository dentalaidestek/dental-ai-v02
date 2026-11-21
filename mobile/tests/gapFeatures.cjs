// Web-mobil parite boşluk özellikleri için kaynak-sözleşme + davranış testleri.
// Uzman müsaitlik aboneliği, görüntü işaretleme, belge görüntüleme, performans açıklaması.
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:'commonjs'}}).outputText,f);
const React=require('react'),renderer=require('react-test-renderer');

const src={
 modern:fs.readFileSync(__dirname+'/../src/modernApi.ts','utf8'),
 professional:fs.readFileSync(__dirname+'/../src/professionalApi.ts','utf8'),
 nativeProfessional:fs.readFileSync(__dirname+'/../src/NativeProfessional.tsx','utf8'),
 nativePerformance:fs.readFileSync(__dirname+'/../src/NativeExpertPerformance.tsx','utf8'),
 screens:fs.readFileSync(__dirname+'/../src/ModernScreens.tsx','utf8'),
 backendChat:fs.readFileSync(__dirname+'/../../app/mobile_api.py','utf8'),
 backendDoc:fs.readFileSync(__dirname+'/../../app/mobile_professional_api.py','utf8'),
 webMain:fs.readFileSync(__dirname+'/../../app/main.py','utf8'),
 webSupport:fs.readFileSync(__dirname+'/../../app/templates/expert_support.html','utf8'),
};
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const byText=(tree,label)=>tree.root.findAllByType('pressable').find(n=>n.findAllByType('text').some(c=>text(c)===label));

test('chat annotate action delegates to the exact web annotation message lifecycle',()=>{
 assert(src.modern.includes('action:"expert-response"|"proposal"|"complete"|"block"|"unblock"|"report"|"delete"|"restore"|"review"|"annotate"'));
 assert(src.modern.includes('message_id?:number;annotation_json?:string'));
 assert(src.backendChat.includes('"annotate": (web.expert_support_annotate_message, (payload.message_id, payload.annotation_json))'));
 assert(src.screens.includes('{action:"annotate",message_id:target.id,annotation_json}'));
 assert(src.screens.includes('✎ İşaretle'));
 assert(src.screens.includes('Görüntüye işaretleme ekle'));
 assert(src.screens.includes('İşaretlenmiş görüntü'));
 assert(src.webMain.includes('message_type="ANNOTATION"'));
 assert(src.webMain.includes('reply_to_message_id=original.id'));
});

test('expert availability watch mirrors the web form flow and specialty list',()=>{
 assert(src.modern.includes('"/expert-support/availability-watch"'));
 assert(src.backendChat.includes('@router.post("/expert-support/availability-watch")'));
 assert(src.backendChat.includes('Geçersiz branş.'));
 const specialties=['Endodonti','Ortodonti','Pedodonti','Periodontoloji','Protetik Diş Tedavisi','Restoratif Diş Tedavisi','Ağız, Diş ve Çene Cerrahisi','Ağız, Diş ve Çene Radyolojisi'];
 for(const specialty of specialties){
  assert(src.modern.includes('"'+specialty+'"'),'mobil branş listesi eksik: '+specialty);
  assert(src.webMain.includes(specialty),'web branş listesi eksik: '+specialty);
 }
 assert(src.screens.includes('Müsait olduğunda haber ver'));
 assert(src.screens.includes('Bu branşta uzman müsait olduğunda bildirim isteğiniz kaydedildi.'));
 assert(src.webSupport.includes('Müsait olduğunda haber ver'));
});

test('professional document viewer exposes the same storage-backed document',()=>{
 assert(src.professional.includes('`/account/documents/${purpose}/content`'));
 assert(src.professional.includes('Belge görüntülenemedi.'));
 assert(src.backendDoc.includes('/account/documents/{purpose}/content'));
 assert(src.backendDoc.includes('ensure_local'));
 assert(src.backendDoc.includes("Literal['membership','title','expert']"));
 assert(src.nativeProfessional.includes('getProfessionalDocument(token,purpose)'));
 assert(src.nativeProfessional.includes('writeAsStringAsync'));
 assert(src.nativeProfessional.includes('shareAsync'));
 assert(src.nativeProfessional.includes('Üyelik Belgesini Görüntüle'));
 assert(src.nativeProfessional.includes('Yüklenen Unvan Belgesini Görüntüle'));
 assert(src.nativeProfessional.includes('Uzmanlık Belgesini Görüntüle'));
});

test('expert performance screen explains the evaluation rules like the web page',async()=>{
 const api={getExpertPerformance:async()=>({
  owner_id:1,availability:'AVAILABLE',capacity:5,open_cases:1,
  performance:{rating_avg:4.5,review_count:2,completed_count:3,avg_response_minutes:7,missed_30:0},
  policy:{blocked:false,blocked_until:null,reason:null,rules_accepted:true},events:[]})};
 const native={StyleSheet:{create:x=>x},ActivityIndicator:()=>'activity-indicator',
  AppState:{addEventListener:()=>({remove(){}})},
  Pressable:props=>React.createElement('pressable',{onPress:props.onPress,accessibilityRole:props.accessibilityRole,accessibilityState:props.accessibilityState,disabled:props.disabled},props.children),
  Text:props=>React.createElement('text',props&&props.style?{style:props.style}:null,props.children),
  View:props=>React.createElement('view',null,props.children)};
 const code=ts.transpileModule(src.nativePerformance,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};
 const sandbox={exports,module:{exports},console,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='./professionalApi'?api:null,setTimeout,clearTimeout};
 vm.runInNewContext(code,sandbox);
 const Component=exports.default;
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(Component,{token:'A'}))});
 const openButton=byText(tree,'Performansım ve Vaka Kabul Durumum');
 assert(openButton,'aç/kapat butonu bulunamadı');
 await renderer.act(async()=>openButton.props.onPress());
 const infoButton=byText(tree,'Performansınız Nasıl Değerlendirilir?');
 assert(infoButton,'değerlendirme açıklaması butonu bulunamadı');
 await renderer.act(async()=>infoButton.props.onPress());
 const content=text(tree.root);
 for(const fragment of ['Kullanıcıların gördüğü bilgiler','Kaydedilen performans olayları','Neler performansınızı düşürmez?','10 dakikalık talep kuralı','Mesaj sayısı veya mesaj uzunluğu kalite ölçütü değildir.']){
  assert(content.includes(fragment),'açıklama metni eksik: '+fragment);
 }
 await renderer.act(async()=>tree.unmount());
});
