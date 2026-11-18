const ts = require("typescript");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test } = require("node:test");

require.extensions[".ts"] = (module, filename) => {
  const source = fs.readFileSync(filename, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  module._compile(output, filename);
};

const {
  createModerationResumeGate,
  isSocialAppResume,
  selectOwnedModerationCandidates,
} = require("../src/socialModerationRefresh.ts");

test("resume moderation candidates include only owned pending/rejected posts and are capped", () => {
  const posts = [
    { id: 1, owned: true, status: "PENDING" },
    { id: 2, owned: false, status: "PENDING" },
    { id: 3, owned: true, status: "PUBLISHED" },
    { id: 4, owned: true, status: "REJECTED" },
    { id: 5, owned: true, status: "PENDING" },
    { id: 6, owned: true, status: "PENDING" },
    { id: 7, owned: true, status: "PENDING" },
    { id: 8, owned: true, status: "PENDING" },
    { id: 9, owned: true, status: "PENDING" },
  ];
  assert.deepEqual(
    selectOwnedModerationCandidates(posts).map((post) => post.id),
    [1, 4, 5, 6, 7],
  );
  assert.deepEqual(selectOwnedModerationCandidates(posts, 100).map((post) => post.id), [1, 4, 5, 6, 7]);
  assert.deepEqual(selectOwnedModerationCandidates(posts, 0), []);
});

test("resume detection is limited to background/inactive to active transitions", () => {
  assert.equal(isSocialAppResume("background", "active"), true);
  assert.equal(isSocialAppResume("inactive", "active"), true);
  assert.equal(isSocialAppResume("active", "active"), false);
  assert.equal(isSocialAppResume("active", "background"), false);
  assert.equal(isSocialAppResume(null, "active"), false);
});

test("moderation resume gate suppresses focus/app-state duplicates and invalid clocks", () => {
  const allow = createModerationResumeGate(15_000);
  assert.equal(allow(100_000), true);
  assert.equal(allow(100_001), false);
  assert.equal(allow(114_999), false);
  assert.equal(allow(115_000), true);
  assert.equal(allow(Number.NaN), false);
  assert.equal(allow(110_000), false, "a backwards clock must not bypass the cooldown");
  assert.equal(allow(130_000), true);
});
