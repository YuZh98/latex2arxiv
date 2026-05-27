// Content script. Runs in the Overleaf project page's isolated world.
// Responsibilities:
//   - Detect the project id from the URL.
//   - Inject the panel UI.
//   - On user action: fetch the project zip (same-origin), hand it to the
//     worker, render diagnostics, and route the output zip to the background
//     service worker for download.

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

async function fetchProjectZip(projectId) {
  const url = `/project/${projectId}/download/zip`;
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`Overleaf returned ${res.status} fetching project zip`);
  return new Uint8Array(await res.arrayBuffer());
}

function spawnWorker() {
  const url = chrome.runtime.getURL("worker.js");
  return new Worker(url, { type: "module" });
}

let workerPromise = null;
function getWorker() {
  if (!workerPromise) {
    workerPromise = (async () => {
      const worker = spawnWorker();
      await new Promise((resolve, reject) => {
        const onMsg = (ev) => {
          if (ev.data && ev.data.type === "ready") {
            worker.removeEventListener("message", onMsg);
            resolve();
          } else if (ev.data && ev.data.type === "error") {
            reject(new Error(ev.data.error));
          }
        };
        worker.addEventListener("message", onMsg);
        worker.postMessage({ type: "init" });
      });
      return worker;
    })();
  }
  return workerPromise;
}

function runInWorker(worker, msg) {
  return new Promise((resolve, reject) => {
    const onMsg = (ev) => {
      if (ev.data && ev.data.requestId === msg.requestId) {
        worker.removeEventListener("message", onMsg);
        if (ev.data.error) reject(new Error(ev.data.error));
        else resolve(ev.data.result);
      }
    };
    worker.addEventListener("message", onMsg);
    worker.postMessage(msg);
  });
}

async function run({ projectId, mode, options, panel }) {
  try {
    setStatus(panel, "Loading engine…", "info");
    const worker = await getWorker();

    setStatus(panel, "Fetching project from Overleaf…", "info");
    const zipBytes = await fetchProjectZip(projectId);

    setStatus(panel, mode === "validate" ? "Validating…" : "Cleaning…", "info");
    const result = await runInWorker(worker, {
      type: "run",
      requestId: crypto.randomUUID(),
      mode,
      options,
      zipBytes,
    });

    renderDiagnostics(panel, result.diagnostics);

    if (mode === "clean" && result.outputZip) {
      const suggestedFilename = (panel.querySelector(".l2a-filename").value || "paper-arxiv.zip").trim();
      chrome.runtime.sendMessage({
        type: "download",
        zipBytes: result.outputZip,
        suggestedFilename,
      });
      setStatus(panel, "Done. Choose where to save…", "ok");
    } else {
      setStatus(panel, "Done.", "ok");
    }
  } catch (err) {
    setStatus(panel, `Failed: ${err.message}`, "err");
  }
}

function buildPanel(projectId) {
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
        onclick: () => run({ projectId, mode: "clean", options: collectOptions(), panel }),
      },
      "Clean for arXiv",
    ),
  );
  buttons.append(
    el(
      "button",
      {
        class: "l2a-btn",
        onclick: () => run({ projectId, mode: "validate", options: collectOptions(), panel }),
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
  const projectId = getProjectId();
  if (!projectId) return;
  if (document.querySelector(".l2a-panel")) return;
  const host = document.body;
  if (!host) return;
  host.append(buildPanel(projectId));
}

if (document.readyState === "complete" || document.readyState === "interactive") {
  inject();
} else {
  document.addEventListener("DOMContentLoaded", inject, { once: true });
}
