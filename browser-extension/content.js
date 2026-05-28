// Content script. Runs in the Overleaf project page's isolated world.
// Responsibilities:
//   - Detect the project id from the URL.
//   - Inject the panel UI.
//   - On user action: fetch the project zip (same-origin), hand it to the
//     worker, render diagnostics, and route the output zip to the background
//     service worker for download.
//   - Revoke blob URLs once the service worker confirms the download landed.

// Registered at top-level so SPA navigation in the same tab cannot spawn
// duplicate listeners. The SW posts {type:"revoke", url} from the
// downloads.onChanged handler once the file is on disk.
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "revoke" && typeof msg.url === "string") {
    URL.revokeObjectURL(msg.url);
  }
});

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

// Cap to a sane upper bound so a runaway Overleaf zip cannot OOM the worker
// mid-Pyodide-boot with an opaque crash. 200 MB matches the CLI's friendly
// pre-zip-bomb cap (the CLI's hard cap is 500 MB uncompressed; this is the
// compressed-zip side of the same idea).
const MAX_PROJECT_ZIP_BYTES = 200 * 1024 * 1024;

async function fetchProjectZip(projectId) {
  const url = `/project/${projectId}/download/zip`;
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`Overleaf returned ${res.status} fetching project zip`);
  const contentLength = Number(res.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > MAX_PROJECT_ZIP_BYTES) {
    throw new Error(
      `Overleaf project zip is ${(contentLength / (1024 * 1024)).toFixed(0)} MB; ` +
        `latex2arxiv refuses to load projects over ${MAX_PROJECT_ZIP_BYTES / (1024 * 1024)} MB`,
    );
  }
  return new Uint8Array(await res.arrayBuffer());
}

function spawnWorker() {
  const url = chrome.runtime.getURL("worker.js");
  // Classic worker; worker.js uses importScripts to load Pyodide.
  return new Worker(url);
}

let workerPromise = null;
function getWorker() {
  if (!workerPromise) {
    const worker = spawnWorker();
    workerPromise = new Promise((resolve, reject) => {
      const onMsg = (ev) => {
        if (!ev.data) return;
        if (ev.data.type === "ready") {
          worker.removeEventListener("message", onMsg);
          resolve(worker);
        } else if (ev.data.type === "error") {
          worker.removeEventListener("message", onMsg);
          reject(new Error(ev.data.error));
        }
      };
      worker.addEventListener("message", onMsg);
      worker.postMessage({ type: "init" });
    }).catch((err) => {
      // Init failed: tear the worker down so the half-booted Pyodide instance
      // does not linger. Reset workerPromise so a retry spawns a fresh worker.
      worker.terminate();
      workerPromise = null;
      throw err;
    });
  }
  return workerPromise;
}

function runInWorker(worker, msg) {
  return new Promise((resolve, reject) => {
    const onMsg = (ev) => {
      if (!ev.data) return;
      // Resolve/reject on a matching requestId, OR on a global worker error
      // posted with `type: "error"`. The latter happens when the worker's
      // message handler catches an exception that has no requestId attached
      // — without this branch the per-call listener would leak.
      if (ev.data.requestId === msg.requestId) {
        worker.removeEventListener("message", onMsg);
        if (ev.data.error) reject(new Error(ev.data.error));
        else resolve(ev.data.result);
      } else if (ev.data.type === "error") {
        worker.removeEventListener("message", onMsg);
        reject(new Error(ev.data.error || "worker error"));
      }
    };
    worker.addEventListener("message", onMsg);
    worker.postMessage(msg);
  });
}

function sanitizeFilename(name) {
  // Drop path separators so a malicious filename cannot escape the user's
  // default download directory. Final folder choice is the user's via saveAs.
  return name.replace(/[\\/]/g, "_");
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
      // Build the Blob URL here in the content script — chrome.runtime
      // .sendMessage uses JSON serialization, which would corrupt a
      // Uint8Array. The service worker only needs the URL string.
      const suggestedFilename = sanitizeFilename(
        (panel.querySelector(".l2a-filename").value || "paper-arxiv.zip").trim(),
      );
      const blob = new Blob([result.outputZip], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      chrome.runtime.sendMessage({ type: "download", url, suggestedFilename });
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
