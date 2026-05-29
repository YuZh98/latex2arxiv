// Content script. Pure UI shim — no fetch, no Worker, no blob URLs.
// Responsibilities:
//   - Detect the project id from the URL.
//   - Inject the panel UI (pill + expanded panel, dock-and-expand pattern).
//   - On user action: send {type:"l2a-run-request", payload:{...}} to the
//     service worker, render the diagnostics it returns, and update status.
//
// The actual fetch + Pyodide + blob handling all live in the offscreen
// document because overleaf.com's CSP refuses workers spawned from a
// chrome-extension:// URL inside the page. See docs/browser-extension-design.md
// for the architecture rationale.
//
// Pure helpers (formatSummary, statusLineDone, clampTop, nextState) live in
// lib/ui-pure.js, loaded as a sibling content script and attached to
// globalThis.l2aPure. The DOM wiring + pointer events here are covered by
// the manual real-Chrome smoke; the pure helpers are covered by
// tests/ui-pure.test.mjs.

const PROJECT_ID_RE = /^\/project\/([0-9a-f]{24})(?:\/|$)/;
const PANEL_VIEWPORT_MARGIN = 12;
const UI_STATE_KEY = "l2a-ui-state";
// Drag threshold: distinguish a click (open the pill) from a drag-start.
const DRAG_PX_THRESHOLD = 4;

const pure = globalThis.l2aPure;

function getProjectId() {
  const m = window.location.pathname.match(PROJECT_ID_RE);
  return m ? m[1] : null;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c);
  return node;
}

function renderDiagnostics(panel, diagnostics) {
  const list = panel.querySelector(".l2a-diagnostics");
  list.innerHTML = "";
  if (!diagnostics || diagnostics.length === 0) {
    list.append(el("div", { class: "l2a-ok" }, "No issues. Submission-ready."));
    return;
  }
  for (const d of diagnostics) {
    list.append(el("div", { class: `l2a-issue l2a-${d.severity}` }, `${d.location || ""}  ${d.message}`));
  }
}

function setStatus(panel, text, kind = "info") {
  const s = panel.querySelector(".l2a-status");
  s.textContent = text;
  s.dataset.kind = kind;
}

function renderGuide(panel, mode, guideText, suggestedFilename, guideRequested) {
  const box = panel.querySelector(".l2a-guide");
  box.innerHTML = "";
  // Validate is a dry run; the guide is only written in Clean. Surface the
  // mismatch directly so a user who checked the box does not silently get
  // nothing back.
  if (mode === "validate" && guideRequested) {
    box.append(
      el(
        "div",
        { class: "l2a-guide-note" },
        "Upload guide is only generated in Clean for arXiv — run that to produce it.",
      ),
    );
    return;
  }
  if (!guideText) return;
  // Prominent ready row so the guide is not missed below the summary line.
  // The Save button is the primary affordance; "View" expands the text for
  // users who want to read before saving.
  const ready = el("div", { class: "l2a-guide-ready" });
  ready.append(el("span", { class: "l2a-guide-ready-label" }, "✓ Upload guide ready"));
  const saveBtn = el(
    "button",
    {
      class: "l2a-btn l2a-guide-save",
      title: "Save this guide as a .txt file alongside your downloads.",
      onclick: () => {
        const blob = new Blob([guideText], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const stem = (suggestedFilename || "paper-arxiv.zip").replace(/\.zip$/i, "");
        const a = document.createElement("a");
        a.href = url;
        a.download = `${stem}_UPLOAD_GUIDE.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
    },
    "Save as .txt",
  );
  ready.append(saveBtn);
  box.append(ready);
  const details = el("details", { class: "l2a-guide-details" });
  details.append(el("summary", {}, "View guide text"));
  details.append(el("pre", { class: "l2a-guide-pre" }, guideText));
  box.append(details);
}

function renderSummary(panel, mode, summary, mainTex) {
  const box = panel.querySelector(".l2a-summary");
  box.innerHTML = "";
  const line = pure.formatSummary(mode, summary, mainTex);
  if (!line) return;
  box.append(el("div", { class: "l2a-summary-line" }, line));
}

async function run({ mode, options, panel }) {
  try {
    const projectId = getProjectId();
    if (!projectId) {
      setStatus(panel, "Not on an Overleaf project page.", "err");
      return;
    }

    // Normalize + validate the main override. Pipeline matches p.name exactly,
    // so a path separator is unreachable and a non-.tex extension fails
    // confusingly. Bail with a clear panel error instead.
    if (options.main) {
      if (/[\\/]/.test(options.main)) {
        setStatus(panel, "Main .tex must be a filename only, not a path.", "err");
        return;
      }
      // Auto-append `.tex` only when the value has no other extension.
      if (!/\.[^./\\]+$/.test(options.main)) {
        options.main = options.main + ".tex";
      }
    }

    setStatus(panel, mode === "validate" ? "Validating…" : "Cleaning…", "info");
    panel.querySelector(".l2a-summary").innerHTML = "";
    panel.querySelector(".l2a-guide").innerHTML = "";

    const suggestedFilename = (panel.querySelector(".l2a-filename").value || "paper-arxiv.zip").trim();
    const result = await chrome.runtime.sendMessage({
      type: "l2a-run-request",
      payload: { projectId, mode, options, suggestedFilename },
    });
    if (!result) {
      throw new Error("no response from background worker");
    }
    if (result.error) {
      throw new Error(result.error);
    }

    renderDiagnostics(panel, result.diagnostics);
    renderSummary(panel, mode, result.summary, result.mainTex);
    renderGuide(panel, mode, result.guideText, suggestedFilename, !!options.guide);
    setStatus(panel, pure.statusLineDone(mode, !!result.downloadDispatched), "ok");
  } catch (err) {
    console.error("latex2arxiv run failed:", err);
    const rawMsg = err && err.message ? String(err.message) : String(err);
    const mainMissing = rawMsg.match(/--main '([^']+)' not found in archive/);
    if (mainMissing) {
      setStatus(
        panel,
        `Main file '${mainMissing[1]}' not found in your project. Check the Main .tex (override) field.`,
        "err",
      );
      return;
    }
    const shortMsg = rawMsg.split("\n")[0].slice(0, 200);
    setStatus(panel, `Failed: ${shortMsg}`, "err");
  }
}

// ---------- Dock-and-expand UI state ----------
//
// Two visible surfaces sharing one Y coordinate:
//   - .l2a-pill    collapsed icon docked on the right edge
//   - .l2a-panel   expanded full panel, anchored to the right edge
//
// Vertical position is shared between the two (closing the panel leaves the
// pill at the same Y; expanding from the pill restores the panel there).
// Height is panel-only (the pill is a fixed size). State persists in
// chrome.storage.session so a hard refresh restores the user's last layout.

const uiState = {
  mode: "expanded", // "expanded" | "collapsed"
  top: null, // px from top of viewport; null = not yet positioned
  height: null, // px panel height; null = use CSS default
};

async function loadUiState() {
  try {
    const s = await chrome.storage.session.get(UI_STATE_KEY);
    if (s && s[UI_STATE_KEY]) {
      const stored = s[UI_STATE_KEY];
      if (stored.mode === "expanded" || stored.mode === "collapsed") uiState.mode = stored.mode;
      if (typeof stored.top === "number") uiState.top = stored.top;
      if (typeof stored.height === "number") uiState.height = stored.height;
    }
  } catch (_) {
    // chrome.storage may be unavailable in early page lifecycle; fall back to defaults.
  }
}

let saveTimer = null;
function saveUiStateDebounced() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    try {
      // Promise-returning; bare try/catch only catches sync throws, so chain
      // .catch as well. Saving the UI layout is best-effort by design — a
      // dropped write just means the next reload starts from defaults.
      chrome.storage.session.set({ [UI_STATE_KEY]: { ...uiState } }).catch(() => {});
    } catch (_) {}
  }, 200);
}

function applyTop(elem) {
  const rect = elem.getBoundingClientRect();
  let top = uiState.top;
  if (top === null) {
    top = Math.max(PANEL_VIEWPORT_MARGIN, window.innerHeight - rect.height - PANEL_VIEWPORT_MARGIN);
    uiState.top = top;
  }
  top = pure.clampTop(top, rect.height, window.innerHeight, PANEL_VIEWPORT_MARGIN);
  uiState.top = top;
  elem.style.top = top + "px";
}

function showActive() {
  const panel = document.querySelector(".l2a-panel");
  const pill = document.querySelector(".l2a-pill");
  if (!panel || !pill) return;
  if (uiState.mode === "expanded") {
    pill.style.display = "none";
    panel.style.display = "";
    if (typeof uiState.height === "number") {
      panel.style.height = uiState.height + "px";
    }
    applyTop(panel);
  } else {
    panel.style.display = "none";
    pill.style.display = "";
    applyTop(pill);
  }
}

function transition(event) {
  const next = pure.nextState(uiState.mode, event);
  if (next === uiState.mode) return;
  uiState.mode = next;
  showActive();
  saveUiStateDebounced();
}

function attachVerticalDrag(elem, handle) {
  let dragging = false;
  let pointerId = null;
  let startY = 0;
  let startTop = 0;
  let moved = false;

  handle.addEventListener("pointerdown", (e) => {
    // Left button only; ignore clicks on inner form controls.
    if (e.button !== 0) return;
    if (e.target.closest("button, input, select, textarea, summary, a")) return;
    dragging = true;
    moved = false;
    pointerId = e.pointerId;
    startY = e.clientY;
    startTop = uiState.top ?? 0;
    try {
      handle.setPointerCapture(pointerId);
    } catch (_) {}
  });

  handle.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const delta = e.clientY - startY;
    if (!moved && Math.abs(delta) < DRAG_PX_THRESHOLD) return;
    moved = true;
    const rect = elem.getBoundingClientRect();
    const next = pure.clampTop(startTop + delta, rect.height, window.innerHeight, PANEL_VIEWPORT_MARGIN);
    uiState.top = next;
    elem.style.top = next + "px";
  });

  function endDrag() {
    if (!dragging) return;
    dragging = false;
    try {
      handle.releasePointerCapture(pointerId);
    } catch (_) {}
    pointerId = null;
    if (moved) saveUiStateDebounced();
  }

  handle.addEventListener("pointerup", endDrag);
  handle.addEventListener("pointercancel", endDrag);

  // Expose so a click handler can suppress its action immediately after a drag.
  return { wasDragged: () => moved };
}

function buildPill() {
  const pill = el("aside", {
    class: "l2a-pill",
    "aria-label": "latex2arxiv (click to expand)",
    title: "latex2arxiv — click to open",
  });
  // Icon is rendered via CSS background-image (extension-origin load,
  // doesn't need web_accessible_resources). Avoids <img src> from the page
  // context which MV3 blocks without WAR.
  pill.addEventListener("click", () => transition("pill-click"));
  return pill;
}

function buildPanel() {
  const panel = el("aside", { class: "l2a-panel", "aria-label": "latex2arxiv" });

  const header = el("header", { class: "l2a-header" });
  header.append(el("span", { class: "l2a-header-title" }, "latex2arxiv"));
  const close = el(
    "button",
    {
      class: "l2a-close",
      "aria-label": "Minimize",
      title: "Minimize to right edge",
      onclick: () => transition("close-click"),
    },
    "×",
  );
  header.append(close);
  panel.append(header);

  const form = el("div", { class: "l2a-form" });
  form.append(el("label", {}, "Output filename"));
  form.append(
    el("input", {
      type: "text",
      class: "l2a-filename",
      value: "paper-arxiv.zip",
      title: "Suggested filename for the cleaned output. Chrome will still show a Save As dialog.",
    }),
  );

  form.append(el("label", {}, "Main .tex (override)"));
  form.append(
    el("input", {
      type: "text",
      class: "l2a-main",
      placeholder: "leave blank to auto-detect",
      title:
        "Filename only, no path. Either 'main_bj' or 'main_bj.tex' works. Leave blank to use the heuristic that picks the .tex file containing \\documentclass.",
    }),
  );
  form.append(
    el(
      "div",
      { class: "l2a-hint" },
      "Auto-detect picks the .tex containing \\documentclass. Override here if it picks the wrong one.",
    ),
  );

  const guideLab = el("label", {
    class: "l2a-check",
    title: "Show a short text guide in this panel after Clean for arXiv. The guide can be saved as a .txt file.",
  });
  guideLab.append(el("input", { type: "checkbox", "data-opt": "guide" }));
  guideLab.append("Write arXiv upload guide (.txt)");
  form.append(guideLab);

  const advanced = el("details", { class: "l2a-advanced" });
  advanced.append(el("summary", {}, "Advanced"));
  const advancedCheckboxes = [
    [
      "flatten",
      "Flatten \\input / \\subfile into one .tex",
      "Inline every \\input/\\include/\\subfile into the main .tex so the submission ships a single source file.",
    ],
    [
      "resize",
      "Resize images (longest side ≤ 1600 px)",
      "Downscale every raster image so its longest side is at most 1600 px. Skips already-small images.",
    ],
  ];
  for (const [name, label, hint] of advancedCheckboxes) {
    const lab = el("label", { class: "l2a-check", title: hint });
    lab.append(el("input", { type: "checkbox", "data-opt": name }));
    lab.append(label);
    advanced.append(lab);
  }
  form.append(advanced);

  panel.append(form);

  const buttons = el("div", { class: "l2a-actions" });

  function collectOptions() {
    const opts = {};
    for (const cb of panel.querySelectorAll(".l2a-check input")) {
      opts[cb.getAttribute("data-opt")] = cb.checked;
    }
    const mainInput = panel.querySelector(".l2a-main");
    const mainValue = mainInput ? mainInput.value.trim() : "";
    if (mainValue) opts.main = mainValue;
    return opts;
  }

  buttons.append(
    el(
      "button",
      {
        class: "l2a-btn l2a-btn-primary",
        title: "Run the full pipeline, then download the cleaned, arXiv-ready zip.",
        onclick: () => run({ mode: "clean", options: collectOptions(), panel }),
      },
      "Clean for arXiv",
    ),
  );
  buttons.append(
    el(
      "button",
      {
        class: "l2a-btn",
        title: "Run arXiv preflight checks without producing a zip.",
        onclick: () => run({ mode: "validate", options: collectOptions(), panel }),
      },
      "Validate",
    ),
  );
  panel.append(buttons);

  panel.append(el("div", { class: "l2a-status" }, "Ready."));
  panel.append(el("div", { class: "l2a-summary" }));
  panel.append(el("div", { class: "l2a-guide" }));
  panel.append(el("div", { class: "l2a-diagnostics" }));

  // Vertical drag via the panel header (excluding inner buttons).
  attachVerticalDrag(panel, header);

  // ResizeObserver persists user height changes. The pill is a fixed size so
  // we only observe the panel.
  if (typeof ResizeObserver === "function") {
    const ro = new ResizeObserver(() => {
      const h = panel.offsetHeight;
      if (typeof h === "number" && h > 0 && h !== uiState.height) {
        uiState.height = h;
        // After resize, re-clamp top: a taller panel may push the bottom edge
        // past the viewport even though the top stayed put.
        applyTop(panel);
        saveUiStateDebounced();
      }
    });
    ro.observe(panel);
  }

  return panel;
}

async function inject() {
  if (!getProjectId()) return;
  if (document.querySelector(".l2a-panel") || document.querySelector(".l2a-pill")) return;
  const host = document.body;
  if (!host) return;

  await loadUiState();

  const panel = buildPanel();
  const pill = buildPill();

  // Park both off-screen before append to prevent a one-frame flash at the
  // document-flow position; the real top is set in showActive() once the
  // active element is measured.
  panel.style.top = "-10000px";
  pill.style.top = "-10000px";
  host.append(pill);
  host.append(panel);

  showActive();
}

function clampActiveToViewport() {
  const active =
    uiState.mode === "expanded" ? document.querySelector(".l2a-panel") : document.querySelector(".l2a-pill");
  if (!active || active.style.display === "none") return;
  const rect = active.getBoundingClientRect();
  const top = pure.clampTop(uiState.top ?? rect.top, rect.height, window.innerHeight, PANEL_VIEWPORT_MARGIN);
  if (top !== uiState.top) {
    uiState.top = top;
    active.style.top = top + "px";
    saveUiStateDebounced();
  }
}

window.addEventListener("resize", clampActiveToViewport);

if (document.readyState === "complete" || document.readyState === "interactive") {
  inject();
} else {
  document.addEventListener("DOMContentLoaded", inject, { once: true });
}
