// Foto Fikir rebuild contracts: backend router + endpoints, per-image quota,
// mevzuat levels, web template IDs, dashboard card wiring, test scripts and
// the no-emoji/Turkish-copy rule fixed by the blueprint.
const fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
const root=__dirname+'/../..';
const src={
 api:fs.readFileSync(root+'/app/foto_fikir_api.py','utf8'),
 web:fs.readFileSync(root+'/app/templates/foto_fikir.html','utf8'),
 dash:fs.readFileSync(root+'/app/templates/dashboard_v2.html','utf8'),
 dashCss:fs.readFileSync(root+'/app/static/dashboard-v2.css','utf8'),
 main:fs.readFileSync(root+'/app/main.py','utf8'),
 base:fs.readFileSync(root+'/app/templates/base.html','utf8'),
};

test('foto fikir api module defines the router and all ten endpoint paths',()=>{
 assert.ok(src.api.includes('foto_fikir_router = APIRouter'));
 for (const path of [
   '/api/foto-fikir/bootstrap','/api/foto-fikir/ideas','/api/foto-fikir/slides',
   '/api/foto-fikir/mevzuat-check','/api/foto-fikir/generate-image','/api/foto-fikir/brand-kit',
   '/api/foto-fikir/brand-kit/generate','/api/foto-fikir/ig-profile','/api/foto-fikir/reels',
   '/api/foto-fikir/history',
 ]) assert.ok(src.api.includes(`@foto_fikir_router.get("${path}")`)||src.api.includes(`@foto_fikir_router.post("${path}")`), path);
 assert.ok(src.api.includes('@foto_fikir_router.get("/uploads/foto_fikir/{owner_id}/{name}")'));
});

test('quota is counted per image from payload image_paths within the current month',()=>{
 const body=src.api.slice(src.api.indexOf('def foto_fikir_quota_used'),src.api.indexOf('def _ff_check_quota'));
 assert.ok(body.includes('image_paths'));
 assert.ok(body.includes('month_start'));
 assert.ok(body.includes('max(1, len(data.get("image_paths") or []))'));
 assert.ok(src.api.includes('kind.in_(["IMAGE", "BRAND"])'));
 assert.ok(src.api.includes('FOTO_FIKIR_QUOTA_LIMIT = 30'));
 assert.ok(src.api.includes('Bu ayın 30 görsel üretim hakkı doldu.'));
});

test('styles list keeps 15 unique ids including the two default styles',()=>{
 assert.ok(src.api.includes('"sade-klinik"'));
 assert.ok(src.api.includes('"derin-lacivert"'));
 assert.ok(src.api.includes('FF_STYLE_NAMES = [style["name"] for style in FF_STYLES]'));
 const styleBlock=src.api.slice(src.api.indexOf('FF_STYLES = ['),src.api.indexOf('FF_STYLE_MAP'));
 assert.equal((styleBlock.match(/\{"id": /g)||[]).length,15);
});

test('mevzuat check exposes remove and warn levels plus the local disclaimer',()=>{
 assert.ok(src.api.includes('"KALDIR"'));
 assert.ok(src.api.includes('"DIKKAT"'));
 assert.ok(src.api.includes('paylaşımı yapan hekimdedir.'));
 assert.ok(src.api.includes('def mevzuat_local_check'));
});

test('web template keeps the full simplified layout with the tools accordion and required ids',()=>{
 for (const token of ['Foto Fikir','Marka Kiti','Reels','mevzuat','ffQuota','ffGenerateBtn',
   'ffPanelMarka','ffPanelIg','ffPanelReels','ffPanelHistory','İçerik Stüdyosu','details'])
   assert.ok(src.web.includes(token), token);
 for (const id of ['ffIdeas','ffTopic','ffIdeasBtn','ffSlidesBtn','ffSlideCount','ffTone','ffSlidesAgain',
   'ffSlides','ffMevzuatBtn','ffMevzuatSummary','ffIncludeName','ffStyles','ffGallery','ffBrandFiles',
   'ffBrandUpload','ffBrandState','ffScenes','ffBrandGenerate','ffIgBtn','ffIgResult','ffReelsTopic',
   'ffReelsBtn','ffReelsResult','ffHistory','ffAlert'])
   assert.ok(new RegExp(`id="${id}"`).test(src.web), id);
 assert.ok(src.web.includes('<details class="ff-tool"'));
});

test('dashboard card markup and the generated webp asset are wired on the home page',()=>{
 assert.ok(src.dash.includes('href="/foto-fikir"'));
 assert.ok(src.dash.includes('dental_ai_foto_fikir_card.webp'));
 const card=fs.statSync(root+'/app/static/dashboard/dental_ai_foto_fikir_card.webp');
 assert.ok(card.size>1000);
});

test('dashboard-v2.css carries both fotofikir image and gradient rules',()=>{
 assert.ok(src.dashCss.includes('.visual-fotofikir img{object-position:center 50%}'));
 assert.ok(src.dashCss.includes('.dashboard-home .visual-fotofikir:before{background:linear-gradient'));
});

test('main.py registers the router and the login-gated web route, base.html links the menu',()=>{
 assert.ok(src.main.includes('from app.foto_fikir_api import foto_fikir_router'));
 assert.ok(src.main.includes('app.include_router(foto_fikir_router)'));
 assert.ok(src.main.includes('@app.get("/foto-fikir"'));
 assert.ok(src.main.includes('name="foto_fikir.html"'));
 assert.ok(src.main.includes('RedirectResponse("/login", status_code=303)'));
 assert.ok(src.base.includes('href="/foto-fikir"'));
 assert.ok(src.base.includes('Foto Fikir'));
});

test('smoke and e2e scripts exist on disk',()=>{
 for (const script of ['scripts/smoke_foto_fikir.py','scripts/test_foto_fikir_e2e.py','scripts/make_foto_fikir_card.py'])
   assert.ok(fs.statSync(root+'/'+script).size>0, script);
});

test('mock image engine overlays Turkish names with a Turkish-capable font',()=>{
 assert.ok(src.api.includes('def foto_fikir_overlay_name'));
 assert.ok(src.api.includes('DejaVuSans.ttf'));
 assert.ok(src.api.includes('_FF_TURKISH_CHARS'));
});

test('user-visible foto fikir text carries no emoji characters',()=>{
 const emoji=/[\u{1F300}-\u{1FAFF}\u{1F000}-\u{1F02F}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE0F}\u{2190}-\u{21FF}]/u;
 assert.ok(!emoji.test(src.api), 'emoji in foto_fikir_api.py');
 assert.ok(!emoji.test(src.web), 'emoji in foto_fikir.html');
});
