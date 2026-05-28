// Unit tests for lib/revoke.mjs. The chrome.* glue in background.js is not
// exercised here — the manual real-Chrome smoke at release time covers that.

import { test } from "node:test";
import assert from "node:assert/strict";

import { planRevoke, dispatchRevoke } from "../lib/revoke.mjs";

// chrome.downloads.onChanged delivers a DownloadDelta: each changed field is
// { previous, current }. These fixtures mirror real Chrome shape.
const completeDelta = { state: { previous: "in_progress", current: "complete" } };
const interruptedDelta = { state: { previous: "in_progress", current: "interrupted" } };
const inProgressDelta = { state: { previous: "complete", current: "in_progress" } };
const pausedDelta = { paused: { previous: false, current: true } };
const emptyDelta = {};

// In-memory adapter matching the chrome.storage.session promise shape.
function makeStore(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    async get(key) {
      return data.has(key) ? { [key]: data.get(key) } : {};
    },
    async set(obj) {
      for (const [k, v] of Object.entries(obj)) data.set(k, v);
    },
    async remove(key) {
      data.delete(key);
    },
    // Test-only inspector.
    snapshot() {
      return Object.fromEntries(data);
    },
  };
}

function makeTabMessenger() {
  const calls = [];
  return {
    fn: (tabId, msg) => {
      calls.push({ tabId, msg });
      return Promise.resolve();
    },
    calls,
  };
}

test("planRevoke: complete is terminal", () => {
  assert.equal(planRevoke(completeDelta), true);
});

test("planRevoke: interrupted is terminal (covers user cancel)", () => {
  assert.equal(planRevoke(interruptedDelta), true);
});

test("planRevoke: in_progress is not terminal", () => {
  assert.equal(planRevoke(inProgressDelta), false);
});

test("planRevoke: pause delta without state change is not terminal", () => {
  assert.equal(planRevoke(pausedDelta), false);
});

test("planRevoke: empty delta is not terminal", () => {
  assert.equal(planRevoke(emptyDelta), false);
});

test("dispatchRevoke: terminal state messages the tab and clears the entry", async () => {
  const store = makeStore({ 42: { tabId: 7, url: "blob:overleaf/abc" } });
  const tab = makeTabMessenger();
  await dispatchRevoke({ downloadId: 42, change: completeDelta, sessionStore: store, messageTab: tab.fn });
  assert.deepEqual(tab.calls, [{ tabId: 7, msg: { type: "revoke", url: "blob:overleaf/abc" } }]);
  assert.deepEqual(store.snapshot(), {});
});

test("dispatchRevoke: non-terminal state is a no-op", async () => {
  const store = makeStore({ 42: { tabId: 7, url: "blob:overleaf/abc" } });
  const tab = makeTabMessenger();
  await dispatchRevoke({ downloadId: 42, change: inProgressDelta, sessionStore: store, messageTab: tab.fn });
  assert.equal(tab.calls.length, 0);
  assert.deepEqual(store.snapshot(), { 42: { tabId: 7, url: "blob:overleaf/abc" } });
});

test("dispatchRevoke: unknown downloadId is silent (race after SW restart)", async () => {
  const store = makeStore({});
  const tab = makeTabMessenger();
  await dispatchRevoke({ downloadId: 999, change: completeDelta, sessionStore: store, messageTab: tab.fn });
  assert.equal(tab.calls.length, 0);
});

test("dispatchRevoke: messageTab rejection still clears the entry", async () => {
  // The page may have torn down (user navigated away) by the time the download
  // finished. Don't pin the URL on the off chance the tab can be reached again.
  const store = makeStore({ 42: { tabId: 7, url: "blob:overleaf/abc" } });
  const messageTab = () => Promise.reject(new Error("no receiving end"));
  await dispatchRevoke({ downloadId: 42, change: completeDelta, sessionStore: store, messageTab });
  assert.deepEqual(store.snapshot(), {});
});
