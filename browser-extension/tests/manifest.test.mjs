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

test("permissions are exactly ['downloads']", () => {
  assert.deepEqual(manifest.permissions, ["downloads"]);
});

test("host_permissions are exactly ['https://www.overleaf.com/*']", () => {
  assert.deepEqual(manifest.host_permissions, ["https://www.overleaf.com/*"]);
});

test("no sensitive permissions are requested", () => {
  const banned = ["<all_urls>", "tabs", "cookies", "storage", "webRequest", "nativeMessaging", "history", "bookmarks"];
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

test("background service worker is background.js (classic, not module)", () => {
  assert.equal(manifest.background.service_worker, "background.js");
  // Pin the absence of `type: "module"` — the worker uses importScripts, which
  // would break under module type. Catches an accidental migration.
  assert.ok(manifest.background.type === undefined, "background.type must remain unset (classic worker)");
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

test("web_accessible_resources expose worker, py/run.py, and wheels to Overleaf", () => {
  assert.equal(manifest.web_accessible_resources.length, 1);
  const war = manifest.web_accessible_resources[0];
  assert.deepEqual(war.matches, ["https://www.overleaf.com/*"]);
  for (const required of ["worker.js", "py/run.py", "wheels/index.json", "wheels/*.whl"]) {
    assert.ok(war.resources.includes(required), `WAR is missing required entry '${required}'`);
  }
});
