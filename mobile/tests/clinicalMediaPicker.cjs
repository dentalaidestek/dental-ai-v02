const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
 const source=fs.readFileSync(filename,'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 module._compile(output,filename);
};

const {
 normalizeClinicalMediaAssets,
 CLINICAL_MEDIA_PICKER_MAX_FILES,
 CLINICAL_MEDIA_PICKER_MAX_BYTES
}=require('../src/clinicalMediaPicker.ts');

const asset=(overrides={})=>({
 uri:'file:///cache/clinical-image.jpg',
 fileName:'clinical-image.jpg',
 mimeType:'image/jpeg',
 fileSize:1024,
 ...overrides
});

test('normalizes JPEG, PNG and WebP assets without changing their source URI',()=>{
 const input=[
  asset(),
  asset({uri:'content://media/external/images/2',fileName:'bitewing.png',mimeType:'image/png'}),
  asset({uri:'file:///cache/scan.webp',fileName:'scan.webp',mimeType:'image/webp'})
 ];
 const result=normalizeClinicalMediaAssets(input);
 assert.deepEqual(result.map(item=>item.type),['image/jpeg','image/png','image/webp']);
 assert.deepEqual(result.map(item=>item.name),['clinical-image.jpg','bitewing.png','scan.webp']);
 assert.deepEqual(result.map(item=>item.uri),input.map(item=>item.uri));
});

test('uses a declared supported MIME for opaque Android content URIs',()=>{
 const result=normalizeClinicalMediaAssets([asset({
  uri:'content://com.android.providers.media.documents/document/image%3A42',
  fileName:null,
  mimeType:'image/webp'
 })]);
 assert.equal(result[0].name,'klinik-0.webp');
 assert.equal(result[0].type,'image/webp');
});

test('rejects unsupported MIME types and unsupported explicit filenames',()=>{
 assert.throws(()=>normalizeClinicalMediaAssets([asset({mimeType:'image/heic',fileName:'scan.heic'})]),/Yalnızca JPEG/);
 assert.throws(()=>normalizeClinicalMediaAssets([asset({mimeType:'',fileName:'scan.heic'})]),/uzantısı desteklenmiyor/);
});

test('rejects disagreement between a supported filename and source URI extension',()=>{
 assert.throws(()=>normalizeClinicalMediaAssets([asset({
  uri:'file:///cache/image.png',
  fileName:'image.jpg',
  mimeType:null
 })]),/uzantısı eşleşmiyor/);
});

test('rejects MIME and filename disagreement before encryption or upload',()=>{
 assert.throws(()=>normalizeClinicalMediaAssets([asset({
  uri:'content://media/opaque/42',
  fileName:'image.png',
  mimeType:'image/jpeg'
 })]),/Dosya adı ve görüntü türü eşleşmiyor/);
});

test('rejects negative and non-finite picker byte counts',()=>{
 for(const fileSize of [-1,Number.NaN,Number.POSITIVE_INFINITY,Number.NEGATIVE_INFINITY]){
  assert.throws(()=>normalizeClinicalMediaAssets([asset({fileSize})]),/boyutu geçersiz/);
 }
});

test('enforces the 12 MB per-image limit and 12-file picker limit',()=>{
 assert.equal(normalizeClinicalMediaAssets([asset({fileSize:CLINICAL_MEDIA_PICKER_MAX_BYTES})]).length,1);
 assert.throws(()=>normalizeClinicalMediaAssets([asset({fileSize:CLINICAL_MEDIA_PICKER_MAX_BYTES+1})]),/12 MiB/);
 assert.equal(normalizeClinicalMediaAssets(Array.from({length:CLINICAL_MEDIA_PICKER_MAX_FILES},(_,i)=>asset({
  uri:`content://media/${i}`,fileName:null,mimeType:'image/jpeg'
 }))).length,CLINICAL_MEDIA_PICKER_MAX_FILES);
 assert.throws(()=>normalizeClinicalMediaAssets(Array.from({length:CLINICAL_MEDIA_PICKER_MAX_FILES+1},()=>asset())),/1–12/);
});

test('rejects non-local, traversing and control-character URIs',()=>{
 for(const uri of ['https://example.invalid/image.jpg','file:///cache/../private.jpg','content://media/\u0000image']){
  assert.throws(()=>normalizeClinicalMediaAssets([asset({uri})]),/kaynağı geçersiz/);
 }
});

test('rejects path-bearing and oversized filenames',()=>{
 assert.throws(()=>normalizeClinicalMediaAssets([asset({fileName:'../patient.jpg'})]),/dosya adı geçersiz/);
 assert.throws(()=>normalizeClinicalMediaAssets([asset({fileName:'x'.repeat(256)+'.jpg'})]),/dosya adı geçersiz/);
});

test('fails closed when neither URI, filename nor MIME identifies a supported format',()=>{
 assert.throws(()=>normalizeClinicalMediaAssets([asset({
  uri:'content://media/opaque/42',
  fileName:null,
  mimeType:null
 })]),/türü belirlenemedi/);
});


test('enforces a 96 MiB aggregate archive picker budget using reported actual sizes',()=>{
 const count=8;
 const accepted=Array.from({length:count},(_,i)=>asset({uri:`content://media/${i}`,fileName:null,mimeType:'image/jpeg',fileSize:CLINICAL_MEDIA_PICKER_MAX_BYTES}));
 assert.equal(normalizeClinicalMediaAssets(accepted).length,8);
 const rejected=[...accepted,asset({uri:'content://media/extra',fileName:null,mimeType:'image/jpeg',fileSize:1})];
 assert.throws(()=>normalizeClinicalMediaAssets(rejected),/toplam boyut en fazla 96 MiB/);
});
