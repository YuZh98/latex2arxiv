// Source-level pins for the v0.1.10 storage architecture:
//
//   - background.js MUST NOT call chrome.storage.session.setAccessLevel —
//     reintroducing it would re-open the SW-private revoke namespace
//     (String(downloadId) keys) to every content script in the page, which
//     is precisely the collision risk v0.1.10 closes.
//
//   - content.js MUST use chrome.storage.local (not .session) for the
//     UI_STATE_KEY persistence path. chrome.storage.session is gated on
//     setAccessLevel from a trusted context; on any cold-SW path that does
//     not first trigger a Validate/Clean message, the SW never wakes and
//     the access level never gets set. local has no such gate.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BG_SRC = fs.readFileSync(path.resolve(__dirname, "..", "background.js"), "utf-8");
const CS_SRC = fs.readFileSync(path.resolve(__dirname, "..", "content.js"), "utf-8");
const CSS_SRC = fs.readFileSync(path.resolve(__dirname, "..", "panel.css"), "utf-8");

test("background.js does NOT call chrome.storage.session.setAccessLevel", () => {
  assert.doesNotMatch(
    BG_SRC,
    /chrome\.storage\.session\s*\.setAccessLevel/,
    "background.js must not opt content scripts into chrome.storage.session; that re-opens the SW-private revoke namespace.",
  );
});

test("content.js reads UI_STATE_KEY from chrome.storage.local (not session)", () => {
  assert.match(
    CS_SRC,
    /chrome\.storage\.local\.get\s*\(\s*UI_STATE_KEY\s*\)/,
    "content.js must read UI_STATE_KEY from chrome.storage.local.",
  );
  assert.doesNotMatch(
    CS_SRC,
    /chrome\.storage\.session\.get\s*\(\s*UI_STATE_KEY\s*\)/,
    "content.js must not read UI_STATE_KEY from chrome.storage.session.",
  );
});

test("content.js writes UI_STATE_KEY to chrome.storage.local (not session)", () => {
  // Pattern matches `chrome.storage.local.set({ [UI_STATE_KEY]: ... })`.
  assert.match(
    CS_SRC,
    /chrome\.storage\.local\.set\s*\(\s*\{\s*\[\s*UI_STATE_KEY\s*\]/,
    "content.js must write UI_STATE_KEY to chrome.storage.local.",
  );
  assert.doesNotMatch(
    CS_SRC,
    /chrome\.storage\.session\.set\s*\(\s*\{\s*\[\s*UI_STATE_KEY\s*\]/,
    "content.js must not write UI_STATE_KEY to chrome.storage.session.",
  );
});

test(".l2a-panel declares box-sizing: border-box AFTER all: initial", () => {
  // `all: initial` resets box-sizing to its initial value (content-box). A
  // subsequent `box-sizing: border-box` in the same rule overrides the
  // reset. If `box-sizing` is removed or reordered above `all: initial`,
  // the panel reverts to content-box; ResizeObserver reads offsetHeight
  // (border-box) and showActive writes style.height (content-box), and
  // the stored uiState.height drifts +26px (padding 24 + border 2) per
  // reload until max-height clamps it.
  const panelRule = CSS_SRC.match(/\.l2a-panel\s*\{([^}]*)\}/);
  assert.ok(panelRule, ".l2a-panel rule must exist in panel.css");
  const body = panelRule[1];
  const idxAll = body.indexOf("all: initial");
  const idxBB = body.indexOf("box-sizing: border-box");
  assert.ok(idxAll !== -1, ".l2a-panel must declare `all: initial`");
  assert.ok(idxBB !== -1, ".l2a-panel must declare `box-sizing: border-box`");
  assert.ok(idxBB > idxAll, "`box-sizing: border-box` must come AFTER `all: initial` in .l2a-panel");
});

test("background.js still calls chrome.storage.session for the revoke handshake", () => {
  // Sanity: removing setAccessLevel must not accidentally also remove the
  // SW-internal revoke storage; that still lives in chrome.storage.session
  // (now SW-private at default TRUSTED_CONTEXTS). The pattern requires a
  // functional call (`.get`/`.set`/`.remove(`) — a bare reference like a
  // comment would otherwise satisfy the assertion.
  assert.match(
    BG_SRC,
    /chrome\.storage\.session\.(get|set|remove)\s*[:(]/,
    "background.js must still call chrome.storage.session.{get,set,remove} for the download-revoke handshake.",
  );
});
