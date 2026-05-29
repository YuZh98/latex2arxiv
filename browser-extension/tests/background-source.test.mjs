// Source-level pin: chrome.storage.session.setAccessLevel must be called at
// background.js top level so the content script can read/write the UI state
// key (chrome.storage.session defaults to TRUSTED_CONTEXTS, which excludes
// content scripts). Dropping this call silently breaks the panel-state
// persistence across hard refresh — the kind of regression a smoke test
// could miss because in-memory state still works within one page lifetime.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.resolve(__dirname, "..", "background.js"), "utf-8");

test("background.js opts content scripts into chrome.storage.session", () => {
  assert.match(
    SRC,
    /chrome\.storage\.session\s*\.setAccessLevel\(\s*\{\s*accessLevel:\s*["']TRUSTED_AND_UNTRUSTED_CONTEXTS["']/,
    "background.js must call chrome.storage.session.setAccessLevel({accessLevel:'TRUSTED_AND_UNTRUSTED_CONTEXTS'})",
  );
});

test("setAccessLevel runs at top level (not inside a handler)", () => {
  // Heuristic: the setAccessLevel call should appear before the first
  // chrome.runtime.onMessage.addListener registration. If it lands inside a
  // handler it does not run on SW wake.
  const setIdx = SRC.search(/chrome\.storage\.session\s*\.setAccessLevel/);
  const onMsgIdx = SRC.search(/chrome\.runtime\.onMessage\.addListener/);
  assert.ok(setIdx !== -1, "setAccessLevel call must exist");
  assert.ok(onMsgIdx !== -1, "onMessage listener must exist");
  assert.ok(setIdx < onMsgIdx, "setAccessLevel must precede the onMessage listener (i.e., be top-level)");
});
