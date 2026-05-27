// Web Worker. Hosts the Pyodide runtime + latex2arxiv pipeline.
//
// v0.1 scaffold: boots Pyodide lazily and exposes a stub `run` handler that
// echoes back a placeholder diagnostics shape. The real pipeline wiring lands
// in the next iteration once the ReDoS-portable-timeout fix is published in
// the PyPI wheel.

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

async function runStub({ requestId, mode, options, zipBytes }) {
  // Echo a placeholder result. Real implementation in next iteration.
  const diagnostics = [
    {
      severity: "info",
      location: "",
      message: `Engine booted; ${mode} mode with options ${JSON.stringify(options)}. Pipeline wiring lands in v0.1.1.`,
    },
  ];
  const result = { diagnostics, outputZip: mode === "clean" ? zipBytes : null };
  self.postMessage({ requestId, result });
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
