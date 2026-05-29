// Pure UI helpers shared between content.js (classic script) and tests.
//
// Dual-format: when loaded as a content_script it attaches helpers to
// globalThis.l2aPure; when required from a node:test it sets module.exports.
// No DOM, no chrome.* — these stay testable in pure node:test.

"use strict";

function formatBytes(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return null;
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / (1024 * 1024)).toFixed(2) + " MB";
}

// Build the summary line shown below the diagnostics.
//
// Validate mode is a dry run: the pipeline reports what would be kept and
// removed, but does not produce an output zip. Past-tense wording would
// imply the action happened — so validate uses "would keep / would remove"
// and clean uses "kept / removed". Validate also skips the size delta
// because sizes_output_bytes is undefined in dry-run.
function formatSummary(mode, summary, mainTex) {
  if (!summary) return null;
  const parts = [];
  if (mainTex) parts.push("main: " + mainTex);
  const kept = summary.keptCount;
  const removed = summary.removedCount;
  if (mode === "validate") {
    if (typeof kept === "number") parts.push("would keep " + kept);
    if (typeof removed === "number") parts.push("would remove " + removed);
  } else {
    if (typeof kept === "number") parts.push(kept + " kept");
    if (typeof removed === "number") parts.push(removed + " removed");
  }
  const inSize = formatBytes(summary.sizesInputBytes);
  const outSize = formatBytes(summary.sizesOutputBytes);
  if (mode === "clean" && inSize && outSize) {
    parts.push(inSize + " → " + outSize);
  } else if (inSize) {
    parts.push("input " + inSize);
  }
  return parts.length ? parts.join(" · ") : null;
}

// Status line text. Past tense for clean (action ran); explicit "no zip
// produced" for validate so the user knows nothing was written.
function statusLineDone(mode, downloadDispatched) {
  if (mode === "clean") {
    return downloadDispatched ? "Cleaned. Choose where to save…" : "Cleaned.";
  }
  return "Validation complete — no zip produced.";
}

// Clamp a panel/pill top so it stays inside the viewport with a margin.
// Pure — no DOM. Falls back to margin if the element is taller than the
// viewport (degenerate case; better to pin to top than push off-screen).
function clampTop(top, height, viewportH, margin) {
  const maxTop = Math.max(margin, viewportH - height - margin);
  if (top < margin) return margin;
  if (top > maxTop) return maxTop;
  return top;
}

// State reducer for the dock-and-expand surface. Only two states; events
// are 'pill-click' (expand), 'close-click' (collapse), and 'init' (honor
// the persisted value as-is). Unknown events are no-ops.
function nextState(current, event) {
  if (event === "pill-click") return "expanded";
  if (event === "close-click") return "collapsed";
  return current;
}

const __exports = { formatBytes, formatSummary, statusLineDone, clampTop, nextState };

if (typeof globalThis !== "undefined") {
  globalThis.l2aPure = __exports;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = __exports;
}
