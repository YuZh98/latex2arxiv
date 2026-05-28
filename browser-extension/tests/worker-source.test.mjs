// Static checks on worker.js that the pyodide-smoke does not cover.
// pyodide-smoke runs in the Node main thread; it never exercises worker.js as
// a Web Worker, so a chrome.* call left inside the worker source slips past
// every existing CI gate and only fails the first time real Chrome loads it.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WORKER_PATH = path.resolve(__dirname, "..", "worker.js");

const source = fs.readFileSync(WORKER_PATH, "utf-8");

// Strip line and block comments before grepping so explanatory references to
// chrome.runtime do not trip the rule.
function stripComments(code) {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^\\])\/\/[^\n]*$/gm, "$1");
}

const codeOnly = stripComments(source);

test("worker.js does not reference chrome.runtime (unavailable in Web Workers)", () => {
  assert.ok(
    !/\bchrome\.runtime\b/.test(codeOnly),
    "Dedicated Workers have no chrome.runtime; use self.location.href to resolve extension URLs from inside worker.js",
  );
});

test("worker.js does not reference chrome.* extension APIs", () => {
  // Same reasoning — chrome.tabs, chrome.storage, chrome.downloads, etc. are
  // all unavailable in a Worker context. If worker.js needs any of these,
  // marshal the data through the offscreen document instead.
  assert.ok(
    !/\bchrome\.\w+/.test(codeOnly),
    "worker.js references a chrome.* API that does not exist inside a Web Worker",
  );
});
