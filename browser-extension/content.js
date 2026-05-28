// Content script. Pure UI shim — no fetch, no Worker, no blob URLs.
// Responsibilities:
//   - Detect the project id from the URL.
//   - Inject the panel UI.
//   - On user action: send {type:"l2a-run-request", payload:{...}} to the
//     service worker, render the diagnostics it returns, and update status.
//
// The actual fetch + Pyodide + blob handling all live in the offscreen
// document because overleaf.com's CSP refuses workers spawned from a
// chrome-extension:// URL inside the page. See docs/browser-extension-design.md
// for the architecture rationale.

const PROJECT_ID_RE = /^\/project\/([0-9a-f]{24})(?:\/|$)/;

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

async function run({ mode, options, panel }) {
  try {
    // Read projectId at call time, not at panel-build time, so SPA navigation
    // between projects in the same tab keeps actions aimed at the current one.
    const projectId = getProjectId();
    if (!projectId) {
      setStatus(panel, "Not on an Overleaf project page.", "err");
      return;
    }

    setStatus(panel, mode === "validate" ? "Validating…" : "Cleaning…", "info");

    // The offscreen document is spun up on demand by the service worker;
    // the round-trip below covers spawn (first run only, ~10-30s while Pyodide
    // cold-loads), fetch, conversion, and — in clean mode — the save dialog.
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
    if (mode === "clean" && result.downloadDispatched) {
      setStatus(panel, "Done. Choose where to save…", "ok");
    } else {
      setStatus(panel, "Done.", "ok");
    }
  } catch (err) {
    // Surface a short message to the page; log the full exception (which may
    // include Pyodide tracebacks with /tmp/... paths) to the extension console
    // so a developer can still diagnose.
    console.error("latex2arxiv run failed:", err);
    const shortMsg = (err && err.message ? String(err.message) : String(err)).split("\n")[0].slice(0, 200);
    setStatus(panel, `Failed: ${shortMsg}`, "err");
  }
}

function buildPanel() {
  const panel = el("aside", { class: "l2a-panel", "aria-label": "latex2arxiv" });

  panel.append(el("header", { class: "l2a-header" }, "latex2arxiv"));

  const form = el("div", { class: "l2a-form" });
  form.append(el("label", {}, "Output filename"));
  form.append(el("input", { type: "text", class: "l2a-filename", value: "paper-arxiv.zip" }));

  for (const [name, label] of [
    ["flatten", "Flatten \\input / \\subfile into one .tex"],
    ["resize", "Resize images (longest side ≤ 1600 px)"],
    ["guide", "Write arXiv upload guide (.txt)"],
  ]) {
    const lab = el("label", { class: "l2a-check" });
    lab.append(el("input", { type: "checkbox", "data-opt": name }));
    lab.append(label);
    form.append(lab);
  }

  panel.append(form);

  const buttons = el("div", { class: "l2a-actions" });

  function collectOptions() {
    const opts = {};
    for (const cb of panel.querySelectorAll(".l2a-check input")) {
      opts[cb.getAttribute("data-opt")] = cb.checked;
    }
    return opts;
  }

  buttons.append(
    el(
      "button",
      {
        class: "l2a-btn l2a-btn-primary",
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
        onclick: () => run({ mode: "validate", options: collectOptions(), panel }),
      },
      "Just validate",
    ),
  );
  panel.append(buttons);

  panel.append(el("div", { class: "l2a-status" }, "Ready."));
  panel.append(el("div", { class: "l2a-diagnostics" }));

  return panel;
}

function inject() {
  if (!getProjectId()) return;
  if (document.querySelector(".l2a-panel")) return;
  const host = document.body;
  if (!host) return;
  host.append(buildPanel());
}

if (document.readyState === "complete" || document.readyState === "interactive") {
  inject();
} else {
  document.addEventListener("DOMContentLoaded", inject, { once: true });
}
