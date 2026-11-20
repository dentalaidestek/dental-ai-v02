const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const template=fs.readFileSync(path.join(__dirname,'../../app/templates/patient_detail.html'),'utf8');
const start=template.indexOf('(function () {\n    const grid = document.getElementById("patientMediaGrid");');
const end=template.indexOf('function openPatientMediaGallery()',start);
const galleryScript=template.slice(start,end);

test('web clinical gallery starts with a bounded page and displays the full record count',()=>{
  assert.match(template,/patient_media_total/);
  assert.match(template,/CLINICAL_MEDIA_GALLERY_PAGE_SIZE \+ 1/);
  assert.match(template,/data-url="\/patients\/\{\{ patient\.id \}\}\/media\/page"/);
  assert.match(template,/data-next-before="\{\{ patient_media_next_before or '' \}\}"/);
  assert.match(template,/id="patientMediaLoadMore"/);
});

test('web gallery loads later pages with the authenticated same-origin session',()=>{
  assert.ok(start>=0 && end>start,'gallery interaction script must be present');
  assert.match(galleryScript,/credentials:\s*"same-origin"/);
  assert.match(galleryScript,/method:\s*"GET"/);
  assert.match(galleryScript,/\?before=/);
  assert.match(galleryScript,/payload\.items\.length > 40/);
  assert.match(galleryScript,/payload\.next_before/);
});

test('selection survives pagination and never exceeds the four-image analysis cap',()=>{
  assert.match(galleryScript,/const selected = new Set\(\)/);
  assert.match(galleryScript,/selected\.add\(id\)/);
  assert.match(galleryScript,/selected\.delete\(id\)/);
  assert.match(galleryScript,/selected\.size >= maxAnalysisImages/);
  assert.match(galleryScript,/ids\.length > maxAnalysisImages/);
});

test('dynamic gallery cards use DOM text nodes and exact same-origin media paths',()=>{
  assert.match(galleryScript,/document\.createElement\("article"\)/);
  assert.match(galleryScript,/checkmark\.textContent = "✓"/);
  assert.match(galleryScript,/badge\.textContent = type/);
  assert.match(galleryScript,/item\.url !== base \+ "\/file"/);
  assert.match(galleryScript,/item\.thumbnail_url !== base \+ "\/thumbnail"/);
  assert.match(galleryScript,/item\.delete_url !== base \+ "\/delete"/);
  assert.doesNotMatch(galleryScript,/innerHTML/);
});

test('web thumbnails are used for cards while the original remains the full-size preview source',()=>{
  assert.match(template,/data-src="\/patients\/\{\{ patient\.id \}\}\/media\/\{\{ media\.id \}\}\/file"/);
  assert.match(template,/src="\/patients\/\{\{ patient\.id \}\}\/media\/\{\{ media\.id \}\}\/thumbnail"/);
  assert.match(galleryScript,/image\.src = item\.thumbnail_url/);
});
