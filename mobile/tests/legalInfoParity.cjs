// Ana sayfa ⋮ penceresi bilgi sayfaları + profil destek kartı sözleşmeleri.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const src=f=>fs.readFileSync(require.resolve('../src/'+f),'utf8');
const app=fs.readFileSync(require('node:path').join(__dirname,'../App.tsx'),'utf8');
const legal=src('legalContent.ts');
const profile=src('NativePatientProfile.tsx');
const infoPage=fs.readFileSync(require('node:path').join(__dirname,'../../app/templates/info_page.html'),'utf8');
const legalTexts=fs.readFileSync(require('node:path').join(__dirname,'../../app/legal_texts.py'),'utf8');

test('home three-dot window hosts the about/contact/rules/privacy pages',()=>{
 for(const entry of ['["Hakkımızda",()=>setInfoDoc(LEGAL_DOCS.about)]','["İletişim",()=>setInfoDoc(LEGAL_DOCS.contact)]','["Kullanım ve Topluluk Kuralları",()=>setInfoDoc(LEGAL_DOCS.rules)]','["Gizlilik",()=>setInfoDoc(LEGAL_DOCS.privacy)]'])
  assert.ok(app.includes(entry),'menu entry missing: '+entry);
 assert.match(app,/\{infoDoc&&<View style=\{\{position:"absolute"/);
 assert.match(app,/accessibilityLabel="Sayfayı kapat"/);
});

test('legal content mirrors the shipped web documents',()=>{
 for(const key of ['about','contact','rules','privacy'])
  assert.match(legal,new RegExp(`key:"${key}",title:"`));
 assert.match(legal,/destek@dentalai\.tr/);
 // Community rules must cover the requested conduct rules.
 for(const keyword of ['Hakaret','küfür','Taciz','Spam','yaptırım','Sorun Bildir'])
  assert.ok(legal.includes(keyword),'rules content must mention '+keyword);
});

test('patient profile offers the support request entry instead of quick actions',()=>{
 assert.ok(profile.includes(`button('Destek Talebi Oluştur',actions.support)`));
 assert.doesNotMatch(profile,/HIZLI İŞLEMLER/);
 assert.doesNotMatch(profile,/actionColors/);
 assert.doesNotMatch(profile,/actionHandlers/);
 // Treatment creation entry stays in the clinical history card (web parity).
 assert.match(profile,/button\('Yeni Tedavi',newTreatment/);
 // App wires the support action to the existing support requests screen.
 assert.match(app,/support:\(\)=>root\(\)\?\.navigate\("SupportRequests"\)/);
});

test('web legal index and contact page expose the new documents',()=>{
 for(const href of ['/legal/community','/legal/about','/legal/contact'])
  assert.ok(infoPage.includes('href="'+href+'"'),'info page link missing: '+href);
 assert.ok(infoPage.includes('destek@dentalai.tr'));
 assert.ok(legalTexts.includes('"community"')&&legalTexts.includes('"about"')&&legalTexts.includes('"contact"'));
});
