"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const template = fs.readFileSync(
  path.join(__dirname, "..", "app", "templates", "analysis_new.html"),
  "utf8",
);
const scriptMatch = template.match(/<script>\s*([\s\S]*?)\s*<\/script>/);
assert.ok(scriptMatch, "analysis_new.html must keep its upload-limit guard script");
const script = scriptMatch[1];

function createForm({ existingCount = 0, files = [] } = {}) {
  let selectedFiles = [...files];
  let inputValue = selectedFiles.length ? "selected" : "";
  const handlers = {};
  const fileInput = {
    get files() {
      return selectedFiles;
    },
    get value() {
      return inputValue;
    },
    set value(value) {
      inputValue = value;
      if (value === "") selectedFiles = [];
    },
    addEventListener(name, callback) {
      handlers[`file:${name}`] = callback;
    },
  };
  const form = {
    dataset: {
      analysisImageLimit: "4",
      existingImageCount: String(existingCount),
      analysisMaxImageBytes: String(15 * 1024 * 1024),
      // Browser dataset mapping for data-analysis-max-batch-bytes.
      analysisMaxBatchBytes: String(48 * 1024 * 1024),
    },
    querySelector(selector) {
      assert.equal(selector, 'input[name="images"]');
      return fileInput;
    },
    addEventListener(name, callback) {
      handlers[name] = callback;
    },
  };
  const alerts = [];
  vm.runInNewContext(script, {
    document: {
      querySelector(selector) {
        assert.equal(selector, ".analysis-compact-form");
        return form;
      },
    },
    window: {
      alert(message) {
        alerts.push(message);
      },
    },
  });
  return {
    fileInput,
    handlers,
    alerts,
    submit() {
      let prevented = false;
      handlers.submit({ preventDefault() { prevented = true; } });
      return prevented;
    },
    change() {
      handlers["file:change"]();
    },
  };
}

test("web clinical-only analysis can submit without an image", () => {
  const form = createForm();
  assert.equal(form.submit(), false);
  assert.deepEqual(form.alerts, []);
});

test("web analysis accepts a valid image below the byte limits", () => {
  const form = createForm({
    files: [{ name: "synthetic.png", size: 2 * 1024 * 1024 }],
  });
  form.change();
  assert.equal(form.fileInput.files.length, 1);
  assert.deepEqual(form.alerts, []);
  assert.equal(form.submit(), false);
});

test("web analysis counts saved patient media together with one new image", () => {
  const form = createForm({
    existingCount: 3,
    files: [{ name: "synthetic-fourth.png", size: 1024 }],
  });
  form.change();
  assert.equal(form.fileInput.files.length, 1);
  assert.deepEqual(form.alerts, []);
  assert.equal(form.submit(), false);
});

test("web analysis rejects a fifth image across saved and new media", () => {
  const form = createForm({
    existingCount: 3,
    files: [
      { name: "synthetic-fourth.png", size: 1024 },
      { name: "synthetic-fifth.png", size: 1024 },
    ],
  });
  form.change();
  assert.equal(form.fileInput.files.length, 0);
  assert.match(form.alerts[0], /en fazla 4 görüntü/);
});

test("web analysis rejects a single image larger than the per-file cap", () => {
  const form = createForm({
    files: [{ name: "synthetic-large.png", size: 15 * 1024 * 1024 + 1 }],
  });
  form.change();
  assert.equal(form.fileInput.files.length, 0);
  assert.match(form.alerts[0], /15 MiB/);
});

test("web analysis accepts a batch exactly at the aggregate byte cap", () => {
  const form = createForm({
    files: Array.from({ length: 4 }, (_, index) => ({
      name: `synthetic-${index}.png`,
      size: 12 * 1024 * 1024,
    })),
  });
  form.change();
  assert.equal(form.fileInput.files.length, 4);
  assert.deepEqual(form.alerts, []);
  assert.equal(form.submit(), false);
});

test("web analysis rejects an aggregate batch above the byte cap", () => {
  const form = createForm({
    files: Array.from({ length: 4 }, (_, index) => ({
      name: `synthetic-${index}.png`,
      size: 13 * 1024 * 1024,
    })),
  });
  form.change();
  assert.equal(form.fileInput.files.length, 0);
  assert.match(form.alerts[0], /toplamı en fazla 48 MiB/);
});

test("web markup and validator use the same aggregate-byte dataset contract", () => {
  const formTag = template.match(/<form\\b[^>]*class="[^"]*analysis-compact-form[^"]*"[^>]*>/);
  assert.ok(formTag, "analysis composer form must expose its upload contract");
  assert.match(formTag[0], /data-analysis-max-batch-bytes=/);
  assert.match(script, /form\\.dataset\\.analysisMaxBatchBytes/);
  assert.doesNotMatch(script, /form\\.dataset\\.analysisBatchMaxBytes/);
});
