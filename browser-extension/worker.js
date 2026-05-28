// Web Worker. Hosts the Pyodide runtime + latex2arxiv pipeline.
//
// On init: boots a locally-vendored Pyodide (no remote code per MV3 Web
// Store policy), fetches the bundled wheels from the extension's
// web-accessible-resources, writes them to the Pyodide virtual filesystem,
// and installs them via micropip. The four Pyodide-managed transitive deps
// (micropip, Pillow, pyyaml, regex) ship under pyodide/ alongside the
// runtime; bibtexparser and pyparsing live under wheels/ because they ship
// as sdists on PyPI and micropip cannot build sdists in-browser.
//
// On run: writes the input zip to MEMFS, invokes converter.convert(),
// reads the output zip back, marshals the Issues object to a serializable
// shape, and posts back.

// chrome.runtime.getURL is the only way to resolve extension assets to a URL
// the worker can fetch. self.location.origin is the same chrome-extension://
// origin, but going through chrome.runtime keeps the call site explicit and
// matches Chrome's documented pattern.
const PYODIDE_BASE = chrome.runtime.getURL("pyodide/");

// Bundled wheels live under browser-extension/wheels/. The list is read from
// wheels/index.json at runtime so a wheel rebuild (which may change minor
// versions) does not require editing this file. Order in the JSON matters for
// micropip resolution: deps before dependents.
const WHEELS_INDEX = "/wheels/index.json";
const PY_RUN_PATH = "/py/run.py";

let pyodide = null;
// Source of the Python entrypoint, fetched once at init() and reused on every
// runPipeline() call. Mirrored by tests/pyodide-smoke.mjs via fs.readFileSync.
let PY_RUN = null;

async function fetchExtensionResource(pathFromRoot) {
  const url = `${self.location.origin}${pathFromRoot}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetch ${pathFromRoot}: HTTP ${res.status}`);
  return res;
}

async function sha256Hex(bytes) {
  const buf = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function init() {
  importScripts(`${PYODIDE_BASE}pyodide.js`);
  pyodide = await self.loadPyodide({ indexURL: PYODIDE_BASE });

  PY_RUN = await (await fetchExtensionResource(PY_RUN_PATH)).text();

  const index = await (await fetchExtensionResource(WHEELS_INDEX)).json();
  const wheels = index.wheels;
  if (!Array.isArray(wheels) || wheels.length === 0) {
    throw new Error("wheels/index.json is empty or malformed");
  }

  for (const entry of wheels) {
    if (!entry || typeof entry.name !== "string" || typeof entry.sha256 !== "string") {
      throw new Error(`wheels/index.json entry missing name or sha256: ${JSON.stringify(entry)}`);
    }
    const bytes = new Uint8Array(await (await fetchExtensionResource(`/wheels/${entry.name}`)).arrayBuffer());
    const actual = await sha256Hex(bytes);
    if (actual !== entry.sha256.toLowerCase()) {
      throw new Error(`sha256 mismatch for ${entry.name}: expected ${entry.sha256}, got ${actual}`);
    }
    pyodide.FS.writeFile(`/tmp/${entry.name}`, bytes);
  }

  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(pyodide.toPy(wheels.map((entry) => `emfs:/tmp/${entry.name}`)));

  self.postMessage({ type: "ready" });
}

async function runPipeline({ requestId, mode, options, zipBytes }) {
  if (!pyodide || !PY_RUN) throw new Error("worker not initialized");

  pyodide.FS.writeFile("/tmp/input.zip", zipBytes);
  pyodide.globals.set("_l2a_mode", mode);
  // toPy converts the JS object into a Python dict so `.get()` works in PY_RUN.
  pyodide.globals.set("_l2a_opts", pyodide.toPy(options || {}));

  let diagnostics;
  let mainTex = null;
  let outputZip = null;
  try {
    const payloadJson = pyodide.runPython(PY_RUN);
    const parsed = JSON.parse(payloadJson);
    mainTex = parsed.main_tex;
    diagnostics = [
      ...parsed.errors.map((m) => ({ severity: "error", message: m, location: null })),
      ...parsed.warnings.map((m) => ({ severity: "warn", message: m, location: null })),
    ];

    if (mode === "clean") {
      try {
        // FS.readFile returns a Uint8Array whose buffer may be a view onto the
        // WASM heap. Copying through `new Uint8Array(...)` lifts the bytes onto
        // a fresh ArrayBuffer so transferring it does not detach Pyodide memory
        // and crash the next runPipeline call.
        outputZip = new Uint8Array(pyodide.FS.readFile("/tmp/output.zip"));
      } catch (_) {
        // convert() aborted before writing the zip; diagnostics already explain.
        outputZip = null;
      }
    }
  } finally {
    // Run cleanup whether convert() threw or returned, so a second click
    // starts from a known state. (Only clears the two paths we wrote;
    // converter.convert() uses tempfile.TemporaryDirectory internally for
    // anything else, which it cleans up itself.)
    for (const p of ["/tmp/input.zip", "/tmp/output.zip"]) {
      try {
        pyodide.FS.unlink(p);
      } catch (_) {}
    }
    for (const name of ["_l2a_mode", "_l2a_opts"]) {
      try {
        pyodide.globals.delete(name);
      } catch (_) {}
    }
  }

  const transfer = outputZip ? [outputZip.buffer] : [];
  self.postMessage(
    { requestId, result: { diagnostics, outputZip, mainTex } },
    transfer,
  );
}

self.addEventListener("message", async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      await init();
    } else if (msg.type === "run") {
      await runPipeline(msg);
    }
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    if (msg && msg.requestId) {
      self.postMessage({ requestId: msg.requestId, error: message });
    } else {
      self.postMessage({ type: "error", error: message });
    }
  }
});
