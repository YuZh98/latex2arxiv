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

function formatBytes(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return null;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function renderGuide(panel, guideText, suggestedFilename) {
  const box = panel.querySelector(".l2a-guide");
  box.innerHTML = "";
  if (!guideText) return;
  const details = el("details", { class: "l2a-guide-details" });
  details.append(el("summary", {}, "arXiv upload guide"));
  details.append(el("pre", { class: "l2a-guide-pre" }, guideText));
  const saveBtn = el(
    "button",
    {
      class: "l2a-btn l2a-guide-save",
      title: "Save this guide as a .txt file alongside your downloads.",
      onclick: () => {
        // Build a one-shot blob URL in the content-script context. Page CSP
        // does not block <a download> for blob: URLs (we already verified
        // worker spawn was the only blocked path). Revoke immediately after
        // the click so the URL does not pin the bytes for the page lifetime.
        const blob = new Blob([guideText], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const stem = (suggestedFilename || "paper-arxiv.zip").replace(/\.zip$/i, "");
        const a = document.createElement("a");
        a.href = url;
        a.download = `${stem}_UPLOAD_GUIDE.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // Revoke after a tick so Chrome has resolved the download from the URL.
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
    },
    "Save as .txt",
  );
  details.append(saveBtn);
  box.append(details);
}

function renderSummary(panel, mode, summary, mainTex) {
  const box = panel.querySelector(".l2a-summary");
  box.innerHTML = "";
  if (!summary) return;
  const parts = [];
  if (mainTex) parts.push(`main: ${mainTex}`);
  if (typeof summary.keptCount === "number") parts.push(`${summary.keptCount} kept`);
  if (typeof summary.removedCount === "number") parts.push(`${summary.removedCount} removed`);
  // In validate mode sizes_output_bytes is undefined; only the input + the
  // uncompressed total are meaningful. Skip any undefined / NaN values so the
  // panel never shows "NaN MB".
  const inSize = formatBytes(summary.sizesInputBytes);
  const outSize = formatBytes(summary.sizesOutputBytes);
  if (mode === "clean" && inSize && outSize) {
    parts.push(`${inSize} → ${outSize}`);
  } else if (inSize) {
    parts.push(`input ${inSize}`);
  }
  box.append(el("div", { class: "l2a-summary-line" }, parts.join(" · ")));
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
    panel.querySelector(".l2a-summary").innerHTML = "";
    panel.querySelector(".l2a-guide").innerHTML = "";

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
    renderSummary(panel, mode, result.summary, result.mainTex);
    renderGuide(panel, result.guideText, suggestedFilename);
    if (mode === "clean" && result.downloadDispatched) {
      setStatus(panel, "Done. Choose where to save…", "ok");
    } else {
      setStatus(panel, "Done.", "ok");
    }
  } catch (err) {
    console.error("latex2arxiv run failed:", err);
    const rawMsg = err && err.message ? String(err.message) : String(err);
    // Typed branch: the pipeline raises this exact message when --main does
    // not match any .tex in the archive. Point the user back to the field
    // they just typed rather than surfacing a generic failure.
    panel.querySelector(".l2a-summary").innerHTML = "";
    panel.querySelector(".l2a-guide").innerHTML = "";
    const mainMissing = rawMsg.match(/--main '([^']+)' not found in archive/);
    if (mainMissing) {
      setStatus(
        panel,
        `Main file '${mainMissing[1]}' not found in your project. Check the Main .tex (override) field under Advanced.`,
        "err",
      );
      return;
    }
    const shortMsg = rawMsg.split("\n")[0].slice(0, 200);
    setStatus(panel, `Failed: ${shortMsg}`, "err");
  }
}

function buildPanel() {
  const panel = el("aside", { class: "l2a-panel", "aria-label": "latex2arxiv" });

  panel.append(el("header", { class: "l2a-header" }, "latex2arxiv"));

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

  const checkboxes = [
    ["flatten", "Flatten \\input / \\subfile into one .tex", "Inline every \\input/\\include/\\subfile into the main .tex so the submission ships a single source file."],
    ["resize", "Resize images (longest side ≤ 1600 px)", "Downscale every raster image so its longest side is at most 1600 px. Skips already-small images."],
    ["guide", "Write arXiv upload guide (.txt)", "Show a short text guide in this panel after Clean for arXiv. The guide can be saved as a .txt file."],
  ];
  for (const [name, label, hint] of checkboxes) {
    const lab = el("label", { class: "l2a-check", title: hint });
    lab.append(el("input", { type: "checkbox", "data-opt": name }));
    lab.append(label);
    form.append(lab);
  }

  // Advanced disclosure — discoverable to the user who needs an override,
  // invisible to the 90% case where auto-detect works.
  const advanced = el("details", { class: "l2a-advanced" });
  advanced.append(el("summary", {}, "Advanced"));
  advanced.append(
    el(
      "div",
      { class: "l2a-hint" },
      "Override auto-detected main .tex if needed (e.g. when two candidates share the same name pattern).",
    ),
  );
  advanced.append(el("label", {}, "Main .tex (override)"));
  advanced.append(
    el("input", {
      type: "text",
      class: "l2a-main",
      placeholder: "leave blank to auto-detect",
      title: "Filename only, no path. Example: main_bj.tex. Leave blank to use the heuristic that picks the .tex file containing \\documentclass.",
    }),
  );
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
        title: "Dry-run: show diagnostics without producing or downloading any output.",
        onclick: () => run({ mode: "validate", options: collectOptions(), panel }),
      },
      "Just validate",
    ),
  );
  panel.append(buttons);

  panel.append(el("div", { class: "l2a-status" }, "Ready."));
  panel.append(el("div", { class: "l2a-summary" }));
  panel.append(el("div", { class: "l2a-guide" }));
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
