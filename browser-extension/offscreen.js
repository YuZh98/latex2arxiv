// Offscreen document. Lives at chrome-extension:// origin (NOT subject to the
// host page's CSP), so it can spawn the Pyodide worker that overleaf.com's
// strict-dynamic + https:-only `script-src` refuses to load from a content
// script. Fetches the project zip from Overleaf via host_permissions cookies,
// runs the pipeline in the worker, and posts diagnostics + a blob URL string
// back through the service worker.
//
// JSON-safe boundary: the output zip Uint8Array crosses worker -> offscreen
// via Worker.postMessage (structured clone, survives). It MUST NOT be sent on
// from here through chrome.runtime.sendMessage (JSON-only, corrupts typed
// arrays). The bytes stay in this document; only the blob URL string leaves.

const WORKER_URL = chrome.runtime.getURL("worker.js");
const MAX_PROJECT_ZIP_BYTES = 200 * 1024 * 1024;

let workerPromise = null;
function getWorker() {
  if (!workerPromise) {
    const worker = new Worker(WORKER_URL);
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

async function fetchProjectZip(projectId) {
  // Cross-origin fetch from chrome-extension:// to overleaf.com. The
  // credentials enum is literal — "same-origin" only sends cookies when the
  // request URL matches the document origin, which is never true here. With
  // host_permissions in the manifest covering the host, an extension context
  // using "include" attaches cookies AND skips the CORS preflight (the
  // extension is the privileged caller).
  const url = `https://www.overleaf.com/project/${projectId}/download/zip`;
  let res = await fetch(url, { credentials: "include" });
  if (res.status === 401 || res.status === 403) {
    // Single retry; the first cold fetch on a fresh extension load sometimes
    // races the cookie handshake. No backoff — a second failure is real.
    await new Promise((r) => setTimeout(r, 100));
    res = await fetch(url, { credentials: "include" });
  }
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

function sanitizeFilename(name) {
  return name.replace(/[\\/]/g, "_");
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg) return false;
  if (msg.type === "l2a-run" && msg.payload) {
    (async () => {
      try {
        const { projectId, mode, options, suggestedFilename } = msg.payload;
        const worker = await getWorker();
        const zipBytes = await fetchProjectZip(projectId);
        const result = await runInWorker(worker, {
          type: "run",
          requestId: crypto.randomUUID(),
          mode,
          options,
          zipBytes,
        });
        let blobUrl = null;
        let filename = null;
        if (mode === "clean" && result.outputZip) {
          const blob = new Blob([result.outputZip], { type: "application/zip" });
          blobUrl = URL.createObjectURL(blob);
          filename = sanitizeFilename((suggestedFilename || "paper-arxiv.zip").trim());
        }
        sendResponse({
          diagnostics: result.diagnostics,
          mainTex: result.mainTex,
          summary: result.summary,
          blobUrl,
          filename,
        });
      } catch (err) {
        const message = err && err.message ? String(err.message) : String(err);
        sendResponse({ error: message });
      }
    })();
    return true;
  }
  if (msg.type === "l2a-revoke" && typeof msg.url === "string") {
    URL.revokeObjectURL(msg.url);
    return false;
  }
  return false;
});
