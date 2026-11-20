const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
  const source=fs.readFileSync(filename,'utf8');
  module._compile(ts.transpileModule(source,{compilerOptions:{
    module:ts.ModuleKind.CommonJS,
    target:ts.ScriptTarget.ES2020
  }}).outputText,filename);
};

test('standalone patient-media route accepts only a positive safe numeric patient id',()=>{
  const {resolvePatientMediaRouteId}=require('../src/patientMediaRoute.ts');
  assert.equal(resolvePatientMediaRouteId(36),36);
  for(const value of [0,-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'36',null,undefined,{},[]]){
    assert.equal(resolvePatientMediaRouteId(value),null,String(value));
  }
});

test('root MediaGallery route delegates to the owner-scoped native archive',()=>{
  const app=fs.readFileSync(require.resolve('../App.tsx'),'utf8');
  assert.match(app,/import NativePatientMedia from ["']\.\/src\/NativePatientMedia["']/);
  assert.match(app,/resolvePatientMediaRouteId/);
  const route=app.match(/<Stack\.Screen name="MediaGallery"[\s\S]*?<\/Stack\.Screen>/)?.[0]||'';
  assert.ok(route,'standalone media route must remain registered');
  assert.match(route,/resolvePatientMediaRouteId\(p\.route\.params\?\.patientId\)/);
  assert.match(route,/userId=\{user\.id\}/);
  assert.match(route,/patientId=\{patientId\}/);
  assert.match(route,/onAnalysis=\{id=>p\.navigation\.navigate\("AnalysisResult",\{id\}\)\}/);
  assert.doesNotMatch(route,/<MediaGallery\b/);
});

test('duplicate legacy gallery and its non-durable direct upload path are removed',()=>{
  const screens=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
  assert.doesNotMatch(screens,/export function MediaGallery/);
  assert.doesNotMatch(screens,/uploadPatientMedia/);
  assert.doesNotMatch(screens,/deleteAllPatientMedia/);
});

test('canonical media pagination keeps the current getMedia TypeScript signature',()=>{
  const native=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
  const api=fs.readFileSync(require.resolve('../src/modernApi.ts'),'utf8');
  const legacy=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
  assert.match(api,/export const getMedia=async\(t:string,p:number,before\?:number\)/);
  assert.match(native,/getMedia\(token,patientId,more\?cursor\?\?undefined:undefined\)/);
  assert.doesNotMatch(legacy,/getMedia\(/);
  assert.doesNotMatch(legacy,/export function MediaGallery/);
});

test('native archive retains web-matched metadata, batch limits, receipts and recovery',()=>{
  const native=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
  const web=fs.readFileSync(require.resolve('../../app/templates/patient_detail.html'),'utf8');
  assert.match(native,/allowsMultipleSelection:\s*true/);
  assert.match(native,/CLINICAL_MEDIA_PICKER_MAX_FILES/);
  assert.match(native,/getPatientMediaUpload\(token,patientId,original\.requestKey\)/);
  assert.match(native,/encryptClinicalMediaFile/);
  assert.match(native,/CLINICAL_MEDIA_MAX_FILE_BYTES/);
  assert.match(native,/CLINICAL_MEDIA_MAX_BATCH_BYTES/);
  assert.match(native,/deleteAllPatientMedia/);
  assert.match(native,/ANALYSIS_MAX_IMAGES/);
  assert.match(native,/mediaToothNumber/);
  assert.match(native,/mediaNote/);
  assert.match(web,/name="files"[^>]*multiple/);
  assert.match(web,/patientMediaToothNumber/);
  assert.match(web,/patientMediaNote/);
  assert.match(web,/patientMediaAnalyzeSelected/);
  assert.match(web,/media\/delete-all/);
});

 
test('native clinical media paging is owner-scoped, bounded and private',()=>{
  const mobile=fs.readFileSync(require.resolve('../../app/mobile_api.py'),'utf8');
  const block=mobile.split('@router.get("/patients/{patient_id}/media")')[1]?.split('@router.delete("/patients/{patient_id}/media/{media_id}")')[0]||'';
  assert.ok(block,'canonical mobile media page route must remain mounted');
  assert.match(block,/_mobile_private_no_store\(response\)/);
  assert.match(block,/Patient\.owner_user_id\s*==\s*user\.id/);
  assert.match(block,/PatientMedia\.owner_user_id\s*==\s*user\.id/);
  assert.match(block,/PatientMedia\.id\.desc\(\)\.limit\(limit\s*\+\s*1\)/);
  assert.match(block,/PatientMedia\.id\s*<\s*before/);
  assert.doesNotMatch(block,/\.offset\(/);
});

test('native thumbnails recheck ownership after lazy R2 generation and stay private',()=>{
  const modern=fs.readFileSync(require.resolve('../../app/mobile_modern_api_v3.py'),'utf8');
  const main=fs.readFileSync(require.resolve('../../app/main.py'),'utf8');
  const block=modern.split('@router.get("/patients/{patient_id}/media/{media_id}/thumbnail")')[1]?.split('@router.get("/patients/{patient_id}/media/{media_id}")')[0]||'';
  assert.ok(block,'native thumbnail route must be mounted');
  assert.match(block,/_user_owned_patient\(s,user,patient_id\)/);
  assert.match(block,/if not row or row\.patient_id!=patient_id or row\.owner_user_id!=user\.id/);
  assert.match(block,/ensure_thumbnail\(file_path\)/);
  assert.match(block,/delete_thumbnail\(file_path\)/);
  assert.match(block,/Cache-Control.*private, no-store/);
  assert.match(block,/Vary.*Authorization/);
  assert.match(main,/app\.include_router\(mobile_router\)[\s\S]*app\.include_router\(mobile_modern_router\)/);
  assert.match(main,/mobile_modern_router\.routes\[:\]\s*=\s*\[route for route in mobile_modern_router\.routes/);
});
