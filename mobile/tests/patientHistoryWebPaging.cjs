const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
const read = (relative) => fs.readFileSync(path.join(ROOT, relative), "utf8");

test("patient profile initial analysis and treatment queries are bounded", () => {
  const source = read("app/main.py");
  const start = source.indexOf("def patient_detail(");
  const end = source.indexOf("MAX_PATIENT_MEDIA_UPLOAD_FILES", start);
  assert.ok(start >= 0 && end > start, "patient_detail route must be present");
  const route = source.slice(start, end);

  for (const [name, assignment, next] of [
    ["analysis", "analysis_rows = s.exec(", "analyses, analyses_next_cursor"],
    ["treatment", "treatment_rows = s.exec(", "treatments, treatments_next_cursor"],
  ]) {
    const queryStart = route.indexOf(assignment);
    const queryEnd = route.indexOf(next, queryStart);
    assert.ok(queryStart >= 0 && queryEnd > queryStart, name + " query must be present");
    const query = route.slice(queryStart, queryEnd);
    assert.ok(query.includes(".limit(HISTORY_PAGE_SIZE + 1)"), name + " query must use look-ahead limit");
    assert.ok(query.indexOf(".limit(HISTORY_PAGE_SIZE + 1)") < query.lastIndexOf(".all()"));
    assert.match(query, /created_at\.desc\(\),\s*\w+\.id\.desc\(\)/);
  }
});

test("web paging routes use cookie auth, patient ownership and private no-store responses", () => {
  const source = read("app/patient_history_web.py");
  assert.match(source, /get_current_user\(request\)/);
  assert.match(source, /patient\.owner_user_id != user\.id/);
  assert.match(source, /Cache-Control.*private, no-store/);
  assert.match(source, /Vary.*Cookie/);
  assert.match(source, /\/patients\/\{patient_id\}\/history\/analyses\/page/);
  assert.match(source, /\/patients\/\{patient_id\}\/history\/treatments\/page/);
  assert.match(source, /HISTORY_PAGE_SIZE \+ 1/);
  assert.match(source, /Analysis\.patient_id == patient_id/);
  assert.match(source, /Treatment\.patient_id == patient_id/);
});

test("analysis partial preserves voice labels, image groups and result modals", () => {
  const source = read("app/templates/patient_analysis_history_items.html");
  assert.match(source, /voice_review_ids/);
  assert.match(source, /analysisModal-\{\{ analysis\.id \}\}/);
  assert.match(source, /Yüklenen görüntüler/);
  assert.match(source, /Radyografiler/);
  assert.match(source, /analysis_assets\.get/);
  assert.match(source, /Analiz sonucunu aç/);
});

test("treatment partial preserves first-three collapse state across appended pages", () => {
  const source = read("app/templates/patient_treatment_history_items.html");
  assert.match(source, /data-initial-visible/);
  assert.match(source, /first_page/);
  assert.match(source, /treatment\.doctor_note/);
  assert.match(source, /treatment\.result/);
});

test("patient profile loads authenticated server-rendered history pages", () => {
  const source = read("app/templates/patient_detail.html");
  assert.match(source, /patient_analysis_history_items\.html/);
  assert.match(source, /patient_treatment_history_items\.html/);
  assert.match(source, /loadMoreAnalyses/);
  assert.match(source, /loadMoreTreatments/);
  assert.match(source, /credentials: "same-origin"/);
  assert.match(source, /insertAdjacentHTML\("beforeend", payload\.html\)/);
  assert.match(source, /list\.dataset\.expanded/);
});

test("cursor helper rejects unbounded input and binds timestamp plus id", () => {
  const source = read("app/patient_history_pagination.py");
  assert.match(source, /_MAX_CURSOR_CHARS = 192/);
  assert.match(source, /created_at\.isoformat\(\)/);
  assert.match(source, /record_id/);
  assert.match(source, /base64\.b64decode[\s\S]*validate=True/);
  assert.match(source, /HISTORY_PAGE_SIZE = 20/);
});
