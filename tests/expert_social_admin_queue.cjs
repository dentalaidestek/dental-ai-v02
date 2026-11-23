const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "app", "static", "expert-social-admin.js"),
  "utf8",
);

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function element() {
  const listeners = new Map();
  return {
    children: [],
    hidden: false,
    disabled: false,
    value: "",
    textContent: "",
    style: {},
    addEventListener(name, handler) { listeners.set(name, handler); },
    fire(name) { return listeners.get(name)?.(); },
    replaceChildren(...items) { this.children = [...items]; },
    append(item) { this.children.push(item); },
    appendChild(item) { this.append(item); },
    setAttribute() {},
    querySelectorAll() { return []; },
    remove() { this.removed = true; },
  };
}

function boot(api) {
  const elements = new Map();
  const get = (selector) => {
    if (!elements.has(selector)) {
      const item = element();
      if (selector === "[data-kind]") item.value = "POST";
      if (selector === "[data-status]") item.value = "PENDING";
      elements.set(selector, item);
    }
    return elements.get(selector);
  };
  const root = { querySelector: get };
  const el = (tag, className, text) => Object.assign(element(), {
    tag, className, textContent: text || "",
  });
  const window = {
    DentalSocial: {
      api,
      el,
      button(label, className, handler) {
        const item = el("button", className, label);
        item.addEventListener("click", handler);
        return item;
      },
      labels: { PUBLISHED: "Yayınlandı", PENDING: "İncelemede", REJECTED: "Reddedildi" },
    },
    DentalMediaViewer: { open() {} },
  };
  vm.runInNewContext(source, {
    document: { querySelector: () => root },
    window,
    location: { search: "" },
    URLSearchParams,
    Promise,
    console,
  }, { filename: "expert-social-admin.js" });
  return { get };
}

async function flushMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

const emptyPage = (aging = {}) => ({
  items: [],
  next_cursor: null,
  aging: {
    waiting_human: 0,
    waiting_owner: 0,
    failed: 0,
    over_1h: 0,
    over_24h: 0,
    ...aging,
  },
});

test("changing moderation filters supersedes an in-flight response", async () => {
  const pending = [];
  const api = (url) => {
    const request = deferred();
    pending.push({ url, ...request });
    return request.promise;
  };
  const { get } = boot(api);

  assert.equal(pending.length, 1);
  assert.equal(pending[0].url, "/moderation?kind=POST&status=PENDING");

  get("[data-kind]").value = "COMMENT";
  get("[data-status]").value = "REJECTED";
  get("[data-queue]").fire("click");

  assert.equal(pending.length, 2);
  assert.equal(pending[1].url, "/moderation?kind=COMMENT&status=REJECTED");

  pending[1].resolve(emptyPage());
  await flushMicrotasks();
  const list = get("[data-admin-list]");
  assert.equal(list.children.length, 1);

  pending[0].resolve(emptyPage({ waiting_human: 99 }));
  await flushMicrotasks();
  assert.equal(list.children.length, 1);
  assert.equal(get("[data-queue-aging]").textContent.includes("99"), false);
});

test("switching to reports supersedes an in-flight moderation queue request", async () => {
  const pending = [];
  const api = (url) => {
    const request = deferred();
    pending.push({ url, ...request });
    return request.promise;
  };
  const { get } = boot(api);

  assert.equal(pending.length, 1);
  get("[data-reports]").fire("click");
  assert.equal(pending.length, 2);
  assert.equal(pending[1].url, "/reports");

  pending[1].resolve({ items: [], next_cursor: null });
  await flushMicrotasks();
  const list = get("[data-admin-list]");
  assert.equal(list.children.length, 1);

  pending[0].resolve(emptyPage({ waiting_human: 77 }));
  await flushMicrotasks();
  assert.equal(list.children.length, 1);
  assert.equal(get("[data-queue-aging]").textContent.includes("77"), false);
});
