// Snapshot test for browser-extension/manifest.json. Pins permission +
// host_permissions + WAR shape so permission creep can't land silently:
// adding a sensitive permission to the manifest fails this test and
// forces a deliberate update.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MANIFEST_PATH = path.resolve(__dirname, "..", "manifest.json");
const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf-8"));

test("manifest_version is 3", () => {
  assert.equal(manifest.manifest_version, 3);
});

test("permissions are exactly ['downloads', 'storage']", () => {
  // `storage` is only used for chrome.storage.session, which tracks
  // (downloadId → blob URL) so onChanged can revoke after the file lands.
  // No persistent storage; cleared on browser session end.
  assert.deepEqual(manifest.permissions, ["downloads", "storage"]);
});

test("host_permissions are exactly ['https://www.overleaf.com/*']", () => {
  assert.deepEqual(manifest.host_permissions, ["https://www.overleaf.com/*"]);
});

test("no sensitive permissions are requested", () => {
  const banned = ["<all_urls>", "tabs", "cookies", "webRequest", "nativeMessaging", "history", "bookmarks"];
  // optional_permissions is a silent escalation channel; pin it empty so a
  // future PR cannot add sensitive perms there without tripping this test.
  const all = [
    ...(manifest.permissions || []),
    ...(manifest.host_permissions || []),
    ...(manifest.optional_permissions || []),
    ...(manifest.optional_host_permissions || []),
  ];
  for (const p of banned) {
    assert.ok(!all.includes(p), `manifest must not request '${p}'`);
  }
});

test("no optional permissions are declared", () => {
  assert.ok(
    !manifest.optional_permissions || manifest.optional_permissions.length === 0,
    "manifest.optional_permissions must be empty (silent escalation channel)",
  );
  assert.ok(
    !manifest.optional_host_permissions || manifest.optional_host_permissions.length === 0,
    "manifest.optional_host_permissions must be empty (silent escalation channel)",
  );
});

test("background service worker is background.js as an ES module", () => {
  assert.equal(manifest.background.service_worker, "background.js");
  // ES-module SW so background.js can `import` shared logic from lib/.
  // Pinned to "module" deliberately — flipping back to classic loses the import
  // and would force duplicating the revoke logic across files.
  assert.equal(manifest.background.type, "module");
});

test("minimum_chrome_version is pinned", () => {
  // Pyodide 0.29 + crypto.subtle in workers + modern ES syntax need a recent
  // Chrome floor. Bumping this is a deliberate change that should be visible
  // in PR review.
  assert.equal(manifest.minimum_chrome_version, "120");
});

test("content script only injects on Overleaf project pages", () => {
  assert.deepEqual(manifest.content_scripts.length, 1);
  assert.deepEqual(manifest.content_scripts[0].matches, ["https://www.overleaf.com/project/*"]);
});

test("web_accessible_resources expose only worker.js to Overleaf", () => {
  // worker.js is the only WAR-required entry: it is loaded via
  // `new Worker(chrome.runtime.getURL("worker.js"))` from the content script,
  // which crosses page-origin → extension-origin. Everything the worker
  // itself fetches afterwards (py/run.py, wheels/*, pyodide/*) is
  // same-origin from chrome-extension:// and needs no WAR. Keeping the WAR
  // narrow tightens the page's view of the extension's filesystem.
  assert.equal(manifest.web_accessible_resources.length, 1);
  const war = manifest.web_accessible_resources[0];
  assert.deepEqual(war.matches, ["https://www.overleaf.com/*"]);
  assert.deepEqual(war.resources, ["worker.js"]);
});

test("manifest version is 0.1.1", () => {
  assert.equal(manifest.version, "0.1.1");
});
