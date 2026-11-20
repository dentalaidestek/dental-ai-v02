const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const ts = require("typescript");
const { test } = require("node:test");

const helperSource = fs.readFileSync(
  require.resolve("../src/socialMediaViewer.ts"),
  "utf8",
);
const compiled = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleRecord = { exports: {} };
vm.runInNewContext(compiled, {
  exports: moduleRecord.exports,
  module: moduleRecord,
  Number,
  Math,
  Set,
  Array,
});
const viewer = moduleRecord.exports;

test("social media viewer accepts only bounded first-party media receipts", () => {
  const valid = [
    { id: 4, url: "/api/expert-social/media/4" },
    { id: 5, url: "/api/expert-social/media/5" },
  ];
  assert.equal(
    JSON.stringify(viewer.normalizeSocialMediaItems(valid)),
    JSON.stringify(valid),
  );
  assert.equal(JSON.stringify(viewer.normalizeSocialMediaItems([
    ...valid,
    { id: 6, url: "/api/expert-social/media/6" },
    { id: 7, url: "/api/expert-social/media/7" },
    { id: 8, url: "/api/expert-social/media/8" },
  ])), "[]");
  assert.equal(JSON.stringify(viewer.normalizeSocialMediaItems([
    { id: 4, url: "https://attacker.example/api/expert-social/media/4" },
  ])), "[]");
  assert.equal(JSON.stringify(viewer.normalizeSocialMediaItems([
    { id: 4, url: "/api/expert-social/media/5" },
  ])), "[]");
  assert.equal(JSON.stringify(viewer.normalizeSocialMediaItems([
    { id: 4, url: "/api/expert-social/media/4" },
    { id: 4, url: "/api/expert-social/media/4" },
  ])), "[]");
});

test("social media zoom is finite and clamped to the web viewer's 1x–5x range", () => {
  assert.equal(viewer.clampSocialZoom(0.2), 1);
  assert.equal(viewer.clampSocialZoom(2.5), 2.5);
  assert.equal(viewer.clampSocialZoom(9), 5);
  assert.equal(viewer.clampSocialZoom(Number.NaN), 1);
  assert.equal(viewer.pinchSocialZoom(2, 100, 150), 3);
  assert.equal(viewer.pinchSocialZoom(2, 0, 150), 2);
});

test("social media pan is bounded to the scaled image and reset at fit size", () => {
  const landscape = viewer.clampSocialPan(500, -30, 400, 800, 1600, 900, 2);
  assert.equal(landscape.x, 200);
  assert.equal(landscape.y, 0);
  const portrait = viewer.clampSocialPan(-900, 900, 400, 800, 800, 1600, 2);
  assert.equal(portrait.x, -200);
  assert.equal(portrait.y, 400);
  assert.equal(JSON.stringify(viewer.clampSocialPan(50, 50, 400, 800, 900, 1600, 1)), JSON.stringify({ x: 0, y: 0 }));
  assert.equal(JSON.stringify(viewer.clampSocialPan(50, 50, 0, 800, 900, 1600, 2)), JSON.stringify({ x: 0, y: 0 }));
});

test("horizontal swipe changes media only at fit size and outside the vertical gesture threshold", () => {
  assert.equal(viewer.socialSwipeDirection(-90, 10, 1), 1);
  assert.equal(viewer.socialSwipeDirection(90, 10, 1), -1);
  assert.equal(viewer.socialSwipeDirection(-90, 80, 1), 0);
  assert.equal(viewer.socialSwipeDirection(-90, 0, 2), 0);
  assert.equal(viewer.socialSwipeDirection(-20, 0, 1), 0);
});

test("media navigation never wraps or leaves the current bounded gallery", () => {
  assert.equal(viewer.nextSocialMediaIndex(0, 1, 3), 1);
  assert.equal(viewer.nextSocialMediaIndex(2, -1, 3), 1);
  assert.equal(viewer.nextSocialMediaIndex(2, 1, 3), null);
  assert.equal(viewer.nextSocialMediaIndex(0, -1, 3), null);
  assert.equal(viewer.nextSocialMediaIndex(0, 1, 0), null);
});

test("native Dental Flow viewer wires pinch, pan, swipe, retry and authenticated media loading", () => {
  const component = fs.readFileSync(
    require.resolve("../src/NativeSocialMediaViewer.tsx"),
    "utf8",
  );
  const screen = fs.readFileSync(
    require.resolve("../src/SocialScreens.tsx"),
    "utf8",
  );
  for (const handler of ["onTouchStart={onTouchStart}", "onTouchMove={onTouchMove}", "onTouchEnd={onTouchEnd}", "onTouchCancel="]) {
    assert.ok(component.includes(handler), handler);
  }
  assert.ok(component.includes("api.socialImageSource(active.url, token)"));
  assert.ok(component.includes('accessibilityLabel="Görseli yeniden yükle"'));
  assert.ok(component.includes('accessibilityLabel="Önceki görsel"'));
  assert.ok(component.includes('accessibilityLabel="Sonraki görsel"'));
  assert.ok(component.includes("requestKeyRef.current !== requestKey"));
  assert.ok(component.includes("}, [visible, token, initialIndex, itemsKey]);"));
  assert.ok(component.includes("opacity: loading || failed ? 0 : 1"));
  assert.ok(screen.includes("NativeSocialMediaViewer"));
  assert.ok(screen.includes("onImage={(media, index) => setImage({ media, index })}"));
  // a1429501 moved session identity into socialSessionKey so bearer tokens never enter React keys;
  // the remount/reset contract is unchanged (sessionKey rotates with user.id, token and session epoch).
  assert.ok(screen.includes('key={`${sessionKey}:media:${image.media.map((item) => item.id).join(",")}`}'));
  assert.ok(screen.includes("setImage(null);"));
  assert.ok(screen.includes("}, [sessionKey]);"));
});
