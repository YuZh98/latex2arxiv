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

test("background.js still references chrome.storage.session for the revoke handshake", () => {
  // Sanity: removing setAccessLevel must not accidentally also remove the
  // SW-internal revoke storage; that still lives in chrome.storage.session
  // (now SW-private at default TRUSTED_CONTEXTS).
  assert.match(
    BG_SRC,
    /chrome\.storage\.session/,
    "background.js still owns chrome.storage.session for the download-revoke handshake.",
  );
});
