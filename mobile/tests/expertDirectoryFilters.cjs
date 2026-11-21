// Uzman dizini filtreleri: branş çipleri + yalnız müsait anahtarı + çekerek yenileme.
// Backend mobile_experts zaten specialty/available destekler; client ve UI bu turda bağlandı.
const fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
const src={
 modern:fs.readFileSync(__dirname+'/../src/modernApi.ts','utf8'),
 screens:fs.readFileSync(__dirname+'/../src/ModernScreens.tsx','utf8'),
 backend:fs.readFileSync(__dirname+'/../../app/mobile_api.py','utf8'),
};

test('getExperts forwards the backend-supported filter parameters',()=>{
 assert.ok(src.modern.includes('opts?:{specialty?:string;available?:boolean}'));
 assert.ok(src.modern.includes('&specialty="+encodeURIComponent(opts.specialty)'));
 assert.ok(src.modern.includes('&available=true'));
});

test('directory renders specialty chips, availability switch and pull-to-refresh',()=>{
 assert.ok(src.screens.includes('specialtyPick,setSpecialtyPick'));
 assert.ok(src.screens.includes('["",...(Array.isArray(EXPERT_SPECIALTIES)?EXPERT_SPECIALTIES:[])]'));
 assert.ok(src.screens.includes('Yalnız müsait uzmanlar'));
 assert.ok(src.screens.includes('refreshControl={typeof RefreshControl!=="undefined"?<RefreshControl refreshing={busy} onRefresh={()=>void load()} tintColor={C.navy}/>:undefined}'));
 assert.ok(src.screens.includes('getExperts(token,q.trim(),{specialty:specialtyPick,available:availableOnly})'));
 assert.ok(src.screens.includes('[token,q,specialtyPick,availableOnly]'));
 // Müsaitlik aboneliği, arama boşken seçili branşla çalışır.
 assert.ok(src.screens.includes('const specialty=q.trim()||specialtyPick'));
});

test('mobile experts endpoint keeps its server-side filter contract',()=>{
 assert.ok(src.backend.includes('specialty:str=Query("",max_length=100),available:bool=False'));
 assert.ok(src.backend.includes('if specialty:q=q.where(ExpertProfile.specialty==specialty)'));
});
