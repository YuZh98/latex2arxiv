// Web Worker. Hosts the Pyodide runtime + latex2arxiv pipeline.
//
// v0.1 scaffold: boots Pyodide lazily from jsDelivr CDN and exposes a stub
// `run` handler. Two known gates before Chrome Web Store publication:
//   1. Pipeline wiring is stubbed pending the ReDoS-timeout fix shipping in
//      a new latex2arxiv PyPI wheel (then micropip.install replaces the stub).
//   2. MV3 prohibits remotely-hosted code execution from extension contexts.
//      Loading Pyodide from a CDN works for unpacked dev installs but is a
//      Web Store rejection path. Production v0.1.1 must vendor the Pyodide
//      runtime files into the extension package and point indexURL at
//      chrome.runtime.getURL("pyodide/").

const PYODIDE_VERSION = "0.29.4";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

let pyodide = null;

async function loadPyodideRuntime() {
  if (pyodide) return pyodide;
  importScripts(`${PYODIDE_CDN}pyodide.js`);
  pyodide = await self.loadPyodide({ indexURL: PYODIDE_CDN });
  return pyodide;
}

async function init() {
  await loadPyodideRuntime();
  self.postMessage({ type: "ready" });
}

async function runStub({ requestId, mode, options }) {
  // v0.1 stub: confirm the engine booted but do not pretend to clean.
  // outputZip is always null so the panel does not trigger a download —
  // a passthrough of the original input would be a worse failure mode
  // than no download at all.
  const diagnostics = [
    {
      severity: "warn",
      location: "",
      message: `Engine booted (${mode} mode, options ${JSON.stringify(options)}). Pipeline wiring is stubbed; no zip will be produced until v0.1.1 lands the Pyodide-side wheel install.`,
    },
  ];
  self.postMessage({ requestId, result: { diagnostics, outputZip: null } });
}

self.addEventListener("message", async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      await init();
    } else if (msg.type === "run") {
      await runStub(msg);
    }
  } catch (err) {
    if (msg.requestId) {
      self.postMessage({ requestId: msg.requestId, error: err.message });
    } else {
      self.postMessage({ type: "error", error: err.message });
    }
  }
});
