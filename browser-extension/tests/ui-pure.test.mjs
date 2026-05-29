// Unit tests for the pure UI helpers in lib/ui-pure.js. DOM wiring,
// pointer events, and chrome.* are not covered here — the manual
// real-Chrome smoke at release time owns those.

import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { formatBytes, formatSummary, statusLineDone, clampTop, nextState } = require("../lib/ui-pure.js");

// ---------- formatBytes ----------

test("formatBytes: small bytes", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(512), "512 B");
});

test("formatBytes: KB threshold", () => {
  assert.equal(formatBytes(1024), "1.0 KB");
  assert.equal(formatBytes(1536), "1.5 KB");
});

test("formatBytes: MB", () => {
  assert.equal(formatBytes(1024 * 1024), "1.00 MB");
  assert.equal(formatBytes(12.34 * 1024 * 1024), "12.34 MB");
});

test("formatBytes: non-number is null", () => {
  assert.equal(formatBytes(undefined), null);
  assert.equal(formatBytes(NaN), null);
  assert.equal(formatBytes("123"), null);
});

// ---------- formatSummary ----------

test("formatSummary: validate uses 'would keep / would remove' (no past-tense action)", () => {
  const out = formatSummary("validate", { keptCount: 7, removedCount: 58, sizesInputBytes: 1024 * 1024 }, "main.tex");
  assert.equal(out, "main: main.tex · would keep 7 · would remove 58 · input 1.00 MB");
});

test("formatSummary: clean uses past tense with size delta", () => {
  const out = formatSummary(
    "clean",
    { keptCount: 7, removedCount: 58, sizesInputBytes: 12 * 1024 * 1024, sizesOutputBytes: 1.5 * 1024 * 1024 },
    "main.tex",
  );
  assert.equal(out, "main: main.tex · 7 kept · 58 removed · 12.00 MB → 1.50 MB");
});

test("formatSummary: validate never shows a size delta even if sizesOutputBytes leaks in", () => {
  const out = formatSummary("validate", { keptCount: 7, removedCount: 58, sizesInputBytes: 1024 * 1024, sizesOutputBytes: 1024 }, null);
  assert.equal(out, "would keep 7 · would remove 58 · input 1.00 MB");
  assert.ok(!out.includes("→"));
});

test("formatSummary: missing summary returns null", () => {
  assert.equal(formatSummary("clean", null, null), null);
  assert.equal(formatSummary("clean", undefined, null), null);
});

test("formatSummary: missing counts are omitted (no NaN, no empty fragments)", () => {
  const out = formatSummary("clean", { sizesInputBytes: 1024 }, null);
  assert.equal(out, "input 1.0 KB");
});

test("formatSummary: no main, no sizes returns just counts", () => {
  const out = formatSummary("validate", { keptCount: 1, removedCount: 0 }, null);
  assert.equal(out, "would keep 1 · would remove 0");
});

// ---------- statusLineDone ----------

test("statusLineDone: validate explicitly says no zip produced", () => {
  assert.equal(statusLineDone("validate", false), "Validation complete — no zip produced.");
  // Even if downloadDispatched is somehow true in validate, the user-facing
  // text stays honest about the mode.
  assert.equal(statusLineDone("validate", true), "Validation complete — no zip produced.");
});

test("statusLineDone: clean with dispatched download prompts save", () => {
  assert.equal(statusLineDone("clean", true), "Cleaned. Choose where to save…");
});

test("statusLineDone: clean without dispatched download is just 'Cleaned.'", () => {
  assert.equal(statusLineDone("clean", false), "Cleaned.");
});

// ---------- clampTop ----------

test("clampTop: in-range value passes through", () => {
  assert.equal(clampTop(100, 280, 800, 12), 100);
});

test("clampTop: below margin pins to margin", () => {
  assert.equal(clampTop(-50, 280, 800, 12), 12);
});

test("clampTop: above maxTop pins to maxTop", () => {
  // viewportH 800 - height 280 - margin 12 = maxTop 508
  assert.equal(clampTop(700, 280, 800, 12), 508);
});

test("clampTop: element taller than viewport pins to margin (degenerate)", () => {
  // maxTop = max(12, 200 - 400 - 12) = max(12, -212) = 12
  assert.equal(clampTop(50, 400, 200, 12), 12);
  assert.equal(clampTop(0, 400, 200, 12), 12);
});

test("clampTop: viewport-edge math (right above maxTop)", () => {
  // viewport 600 - height 100 - margin 12 = 488 max
  assert.equal(clampTop(489, 100, 600, 12), 488);
  assert.equal(clampTop(488, 100, 600, 12), 488);
});

// ---------- nextState ----------

test("nextState: pill-click expands", () => {
  assert.equal(nextState("collapsed", "pill-click"), "expanded");
  // Already expanded → still expanded (idempotent).
  assert.equal(nextState("expanded", "pill-click"), "expanded");
});

test("nextState: close-click collapses", () => {
  assert.equal(nextState("expanded", "close-click"), "collapsed");
  assert.equal(nextState("collapsed", "close-click"), "collapsed");
});

test("nextState: unknown event is a no-op (defensive)", () => {
  assert.equal(nextState("expanded", "wat"), "expanded");
  assert.equal(nextState("collapsed", undefined), "collapsed");
});
