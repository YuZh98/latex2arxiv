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

test("permissions are exactly ['downloads', 'storage', 'offscreen']", () => {
  // `storage` is only used for chrome.storage.session, which tracks
  // (downloadId → blob URL) so onChanged can revoke after the file lands.
  // `offscreen` is required to call chrome.offscreen.createDocument; the
  // offscreen document hosts the Pyodide worker because overleaf.com's CSP
  // refuses chrome-extension:// workers spawned from the content script.
  // No persistent storage; cleared on browser session end.
  assert.deepEqual(manifest.permissions, ["downloads", "storage", "offscreen"]);
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

test("web_accessible_resources is absent (no page-facing surface)", () => {
  // v0.1.2 retires the last WAR entry. The worker is now spawned from the
  // offscreen document (chrome-extension:// origin), which loads worker.js
  // same-origin — no WAR needed. Keeping web_accessible_resources empty (or
  // absent) removes the page's view of every extension file and tightens the
  // Chrome Web Store review surface.
  assert.ok(
    !manifest.web_accessible_resources || manifest.web_accessible_resources.length === 0,
    "web_accessible_resources must be empty in v0.1.2; pages no longer load extension files directly",
  );
});

test("manifest version is 0.1.2", () => {
  assert.equal(manifest.version, "0.1.2");
});
