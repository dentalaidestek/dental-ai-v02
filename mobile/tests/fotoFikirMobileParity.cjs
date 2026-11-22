// Foto Fikir mobile-web parity contracts: the _ff_auth Bearer bridge, the
// native API client (10 endpoints + first-party image source), the studio
// screen copy and its App.tsx registration fixed by the parity task.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{test}=require('node:test');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const root=path.join(__dirname,'../..');
const src={
 api:fs.readFileSync(root+'/app/foto_fikir_api.py','utf8'),
 ffApi:fs.readFileSync(root+'/mobile/src/fotoFikirApi.ts','utf8'),
 screen:fs.readFileSync(root+'/mobile/src/NativeFotoFikir.tsx','utf8'),
 app:fs.readFileSync(root+'/mobile/App.tsx','utf8'),
};
const ffEndpoints=['','/ideas','/slides','/mevzuat-check','/generate-image','/brand-kit','/brand-kit/generate','/ig-profile','/reels','/history'];

test('backend _ff_auth keeps the cookie-first web path and adds the mobile Bearer bridge',()=>{
 const body=src.api.slice(src.api.indexOf('def _ff_auth'),src.api.indexOf('@contextmanager'));
 const cookieAt=body.indexOf('request.cookies.get("dental_ai_session")'),authAt=body.indexOf('request.headers.get("authorization")');
 assert.ok(cookieAt>=0&&authAt>cookieAt,'cookie path must be evaluated before the authorization header');
 assert.ok(body.includes('scheme.lower() != "bearer"'),'case-insensitive Bearer prefix');
 assert.ok(body.includes('HTTPAuthorizationCredentials'),'lazy credentials object');
 assert.ok(body.includes('_mobile_user'),'same token mechanism as the mobile v1 routers');
 assert.ok(body.includes('from app import mobile_api as mobile_module'));
 assert.ok(body.includes('"Oturum gerekli."'),'same Turkish 401 copy for invalid or expired Bearer');
});

test('fotoFikirApi.ts declares all ten /api/foto-fikir endpoint callers',()=>{
 assert.ok(src.ffApi.includes('const FF_BASE = FF_SITE + "/api/foto-fikir"'));
 const callers=['getFFBootstrap','suggestFFIdeas','prepareFFSlides','checkFFMevzuat','generateFFImages','uploadFFBrandKit','generateFFBrandScene','getFFIgProfile','getFFReelsPlan','getFFHistory'];
 for(const name of callers)assert.ok(new RegExp('export const '+name+' =|export const '+name+'=|export async function '+name).test(src.ffApi),name);
 for(const endpoint of ffEndpoints)assert.ok(src.ffApi.includes('"'+endpoint+'"'),endpoint);
});

test('ffImageSource attaches the Bearer header only to first-party /uploads/foto_fikir paths',()=>{
 assert.ok(src.ffApi.includes('path.startsWith("/uploads/foto_fikir/")'));
 assert.ok(src.ffApi.includes('headers: { Authorization: "Bearer " + token }'));
 const ffApi=require('../src/fotoFikirApi.ts');
 const first=ffApi.ffImageSource('secret','/uploads/foto_fikir/3/ff_x.png');
 assert.equal(first.uri,'https://dentalai.tr/uploads/foto_fikir/3/ff_x.png');
 assert.equal(first.headers.Authorization,'Bearer secret');
 const other=ffApi.ffImageSource('secret','https://cdn.example.com/x.png');
 assert.equal(other.uri,'https://cdn.example.com/x.png');
 assert.equal(other.headers,undefined,'never leak the session token to external hosts');
});

test('ffRequest sends the Bearer header and skips Content-Type on the multipart brand-kit upload',async()=>{
 const ffApi=require('../src/fotoFikirApi.ts');
 const original=global.fetch;const calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({exists:true,photos_count:1,photos:['/uploads/foto_fikir/3/brand_1.jpg'],saved:1}),{status:200})};
 try{
  await ffApi.uploadFFBrandKit('secret',[{uri:'file:///a.jpg',name:'a.jpg',type:'image/jpeg'}]);
  assert.match(calls[0].url,/\/api\/foto-fikir\/brand-kit$/);
  assert.equal(calls[0].init.headers.Authorization,'Bearer secret');
  assert.equal(calls[0].init.headers['Content-Type'],undefined,'multipart body must set its own boundary');
  global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({profile:{display_name:'Dr. Test'},styles:[{id:'sade-klinik',name:'Sade Klinik',hint:'beyaz'}],quota:{used:1,limit:30,period:'ay'},brand_kit:{exists:false,photos_count:0,photos:[]},recent:[]}),{status:200})};
  const boot=await ffApi.getFFBootstrap('secret');
  assert.equal(boot.quota.limit,30);
  assert.match(calls[1].url,/\/api\/foto-fikir$/);
  assert.equal(calls[1].init.headers.Authorization,'Bearer secret');
  assert.equal(calls[1].init.headers['Content-Type'],'application/json');
 }finally{global.fetch=original}
});

test('ffRequest maps a 401 to the Turkish copy and runs the session revalidation probe',async()=>{
 const ffApi=require('../src/fotoFikirApi.ts');
 const original=global.fetch;const token='expired-'+Date.now();const calls=[];
 global.fetch=async(url)=>{calls.push(String(url));return new Response(JSON.stringify({detail:'Oturum gerekli.'}),{status:401})};
 try{
  await assert.rejects(()=>ffApi.getFFHistory(token),error=>error.status===401&&error.message==='Oturum gerekli.');
  assert.ok(calls.some(url=>url.endsWith('/api/foto-fikir/history')));
  assert.ok(calls.some(url=>url.endsWith('/api/mobile/v1/me')),'401 triggers the shared session revalidation flow');
 }finally{global.fetch=original}
});

test('client validation mirrors the backend rules with Turkish copy and no network call',async()=>{
 const ffApi=require('../src/fotoFikirApi.ts');
 const original=global.fetch;global.fetch=()=>{throw Error('unexpected network call')};
 try{
  assert.throws(()=>ffApi.prepareFFSlides('t','konu',2),/3 ile 8 arasında/);
  assert.throws(()=>ffApi.checkFFMevzuat('t',['a','b','c','d','e','f','g','h','i','j','k','l','m']),/1 ile 12 arası/);
  assert.throws(()=>ffApi.uploadFFBrandKit('t',[]),/En fazla 3 fotoğraf/);
  assert.throws(()=>ffApi.uploadFFBrandKit('t',[{uri:'file:///a.gif',name:'a.gif',type:'image/gif'}]),/Yalnızca PNG veya JPEG/);
  assert.throws(()=>ffApi.generateFFBrandScene('t',''),/Geçerli bir sahne/);
  assert.throws(()=>ffApi.getFFReelsPlan('t',''),/Reels konusu gerekli/);
  await assert.rejects(async()=>ffApi.generateFFImages('t',{topic:'',styleId:'sade-klinik',slides:[],includeName:false}),/Konu ve en az bir slayt metni gerekli/);
 }finally{global.fetch=original}
});

test('generate-image waits on the long 600s deadline before the 408 timeout',async t=>{
 const ffApi=require('../src/fotoFikirApi.ts');
 const original=global.fetch;
 t.mock.timers.enable({apis:['setTimeout']});
 global.fetch=(_url,options)=>new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted'))));
 try{
  const pending=assert.rejects(()=>ffApi.generateFFImages('t',{topic:'konu',styleId:'sade-klinik',slides:[{headline:'Başlık',body:'Metin'}],includeName:false}),error=>error.status===408);
  t.mock.timers.tick(600000);
  await pending;
 }finally{global.fetch=original;t.mock.timers.reset()}
});

test('the studio screen keeps the quota header, three steps and mevzuat copy',()=>{
 assert.ok(src.screen.includes('Bu ay {quota?quota.used:0}/{quota?quota.limit:30} görsel'));
 assert.ok(src.screen.includes('Örnek çıktı (mock) modu etkin'),'mock warning when payload.mock');
 for(const step of ['1. Konu','2. Metin onayı','3. Görsel'])assert.ok(src.screen.includes(step),step);
 for(const level of ['OK','DİKKAT','KALDIR'])assert.ok(new RegExp('[,{"]'+level).test(src.screen),level);
 assert.ok(src.screen.includes('Yaratıcı alternatif:'));
 assert.ok(src.screen.includes('Mevzuat kontrolü yap'));
 assert.ok(src.screen.includes('disclaimer'));
 assert.ok(src.screen.includes('Görselin sağ alt köşesine adım yazılsın'));
 assert.ok(src.screen.includes('useState(true)'),'adım yazma varsayılan açık');
 assert.ok(src.screen.includes('Fikir öner')&&src.screen.includes('Slayt metinlerini hazırla')&&src.screen.includes('Görselleri üret'));
});

test('the screen wires all ten endpoint callers and the authorized image source',()=>{
 for(const name of ['getFFBootstrap','suggestFFIdeas','prepareFFSlides','checkFFMevzuat','generateFFImages','uploadFFBrandKit','generateFFBrandScene','getFFIgProfile','getFFReelsPlan','getFFHistory'])
  assert.ok(src.screen.includes(name),name);
 assert.ok(src.screen.includes('ffImageSource(token,')&&src.screen.includes('<Image source={ffImageSource(token,'),'gallery uses the Bearer-header image pattern');
 assert.ok(src.screen.includes('Yönetmenlik: {row.shot}'),'reels shot row');
 assert.ok(src.screen.includes('Görseli aç'),'history preview entry');
});

test('App.tsx registers the FotoFikir screen and home entry with the dashboard card art',()=>{
 assert.ok(src.app.includes('import NativeFotoFikir from"./src/NativeFotoFikir"'));
 assert.ok(src.app.includes('name="FotoFikir" options={{title:"Foto Fikir — İçerik stüdyosu"}}'));
 const screenAt=src.app.indexOf('name="FotoFikir"');
 assert.ok(screenAt>src.app.indexOf('name="Academic"'),'registered next to the Academic screen');
 assert.ok(src.app.slice(screenAt-80,screenAt).includes('SessionScope scope={`${token}:${user.id}:foto-fikir`}')||src.app.includes('SessionScope scope={`${token}:${user.id}:foto-fikir`}'));
 assert.ok(src.app.includes('title="Foto Fikir — İçerik stüdyosu" description="Onaylı metinlerinizden karusel görselleri, marka kiti ve Reels planı."'));
 assert.ok(src.app.includes('asset="/static/dashboard/dental_ai_foto_fikir_card.webp"'));
 assert.ok(src.app.indexOf('title="Foto Fikir — İçerik stüdyosu"')>src.app.indexOf('title="Dental AI ile Analiz"'),'home entry after Dental AI ile Analiz');
 assert.ok(src.app.includes('asset.startsWith("/")?"https://dentalai.tr"+asset'),'backwards-compatible full-URL asset support');
});

test('the new Foto Fikir TS/TSX files carry no emoji and keep Turkish labels',()=>{
 const emoji=/[\u{1F300}-\u{1FAFF}\u{1F000}-\u{1F02F}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE0F}\u{2190}-\u{21FF}]/u;
 assert.ok(!emoji.test(src.ffApi),'emoji in fotoFikirApi.ts');
 assert.ok(!emoji.test(src.screen),'emoji in NativeFotoFikir.tsx');
 for(const label of ['Foto Fikir','Marka Kiti','Instagram Profili','Reels Çekim Planı','Son İşlemler','Kancalar','Senaryo','Kurgu adımları (CapCut)','Sahne görseli üret','Fotoğraf seç ve yükle'])
  assert.ok(src.screen.includes(label),label);
});
