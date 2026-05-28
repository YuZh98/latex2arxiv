// Tests for lib/offscreen-lifecycle.mjs. The chrome.offscreen.* glue in
// background.js is not exercised here — these cases pin the singleton
// behavior with in-memory stubs of has/create.

import { test } from "node:test";
import assert from "node:assert/strict";

import { makeOffscreenManager } from "../lib/offscreen-lifecycle.mjs";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("ensureOffscreen skips createDocument when one already exists", async () => {
  let createCalls = 0;
  const ensure = makeOffscreenManager({
    hasDocument: async () => true,
    createDocument: async () => {
      createCalls += 1;
    },
  });
  await ensure();
  await ensure();
  assert.equal(createCalls, 0);
});

test("ensureOffscreen creates the document on first call when missing", async () => {
  let createCalls = 0;
  let exists = false;
  const ensure = makeOffscreenManager({
    hasDocument: async () => exists,
    createDocument: async () => {
      createCalls += 1;
      exists = true;
    },
  });
  await ensure();
  assert.equal(createCalls, 1);
});

test("ensureOffscreen serializes concurrent callers onto one in-flight create", async () => {
  let createCalls = 0;
  let exists = false;
  const gate = deferred();
  const ensure = makeOffscreenManager({
    hasDocument: async () => exists,
    createDocument: async () => {
      createCalls += 1;
      await gate.promise;
      exists = true;
    },
  });
  const first = ensure();
  const second = ensure();
  const third = ensure();
  gate.resolve();
  await Promise.all([first, second, third]);
  // Without the module-level singleton Promise, each call would invoke
  // createDocument independently and Chrome would reject the second and third
  // with "Only a single offscreen document may be created."
  assert.equal(createCalls, 1);
});

test("ensureOffscreen retries createDocument after a failed attempt", async () => {
  let createCalls = 0;
  let exists = false;
  let failNext = true;
  const ensure = makeOffscreenManager({
    hasDocument: async () => exists,
    createDocument: async () => {
      createCalls += 1;
      if (failNext) {
        failNext = false;
        throw new Error("simulated transient failure");
      }
      exists = true;
    },
  });
  await assert.rejects(() => ensure(), /transient/);
  // After the failure the in-flight Promise must have cleared so the next
  // ensure() can spawn a fresh createDocument call.
  await ensure();
  assert.equal(createCalls, 2);
});

test("ensureOffscreen propagates createDocument rejection to all concurrent callers", async () => {
  let createCalls = 0;
  const ensure = makeOffscreenManager({
    hasDocument: async () => false,
    createDocument: async () => {
      createCalls += 1;
      throw new Error("boom");
    },
  });
  const first = ensure();
  const second = ensure();
  await assert.rejects(() => first, /boom/);
  await assert.rejects(() => second, /boom/);
  assert.equal(createCalls, 1);
});
