// Web Worker. Hosts the Pyodide runtime + latex2arxiv pipeline.
//
// On init: boots Pyodide, fetches the bundled wheels from the extension's
// web-accessible-resources, writes them to the Pyodide virtual filesystem,
// and installs them via micropip. Transitive deps available in Pyodide's
// own package index (Pillow, pyyaml, regex) resolve automatically; only
// bibtexparser and pyparsing are bundled because they ship as sdists on
// PyPI and micropip cannot build sdists in-browser.
//
// On run: writes the input zip to MEMFS, invokes converter.convert(),
// reads the output zip back, marshals the Issues object to a serializable
// shape, and posts back.
//
// v0.1.1 store-distribution gate: Pyodide itself still loads from the
// jsDelivr CDN here. MV3 prohibits remotely-hosted code at Chrome Web Store
// review. Before Store submission, vendor pyodide.js + pyodide.asm.* + the
// built-in package set into browser-extension/pyodide/ and switch indexURL
// to chrome.runtime.getURL("pyodide/").

const PYODIDE_VERSION = "0.29.4";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

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
  importScripts(`${PYODIDE_CDN}pyodide.js`);
  pyodide = await self.loadPyodide({ indexURL: PYODIDE_CDN });

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

  let parsed;
  let outputZip = null;
  try {
    const payloadJson = pyodide.runPython(PY_RUN);
    parsed = JSON.parse(payloadJson);

    if (mode === "clean") {
      try {
        outputZip = pyodide.FS.readFile("/tmp/output.zip");
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

  const diagnostics = [
    ...parsed.errors.map((m) => ({ severity: "error", message: m, location: null })),
    ...parsed.warnings.map((m) => ({ severity: "warn", message: m, location: null })),
  ];

  const transfer = outputZip ? [outputZip.buffer] : [];
  self.postMessage(
    { requestId, result: { diagnostics, outputZip, mainTex: parsed.main_tex } },
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
