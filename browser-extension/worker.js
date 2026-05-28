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

// Bundled wheels live under browser-extension/wheels/. Order matters for
// micropip resolution: deps before dependents.
const BUNDLED_WHEELS = [
  "pyparsing-3.3.2-py3-none-any.whl",
  "bibtexparser-1.4.4-py3-none-any.whl",
  "latex2arxiv-1.2.2-py3-none-any.whl",
];

let pyodide = null;

async function fetchWheel(filename) {
  const url = `${self.location.origin}/wheels/${filename}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetch ${filename}: HTTP ${res.status}`);
  return new Uint8Array(await res.arrayBuffer());
}

async function init() {
  importScripts(`${PYODIDE_CDN}pyodide.js`);
  pyodide = await self.loadPyodide({ indexURL: PYODIDE_CDN });

  for (const f of BUNDLED_WHEELS) {
    pyodide.FS.writeFile(`/tmp/${f}`, await fetchWheel(f));
  }

  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(pyodide.toPy(BUNDLED_WHEELS.map((f) => `emfs:/tmp/${f}`)));

  self.postMessage({ type: "ready" });
}

async function runPipeline({ requestId, mode, options, zipBytes }) {
  if (!pyodide) throw new Error("worker not initialized");

  pyodide.FS.writeFile("/tmp/input.zip", zipBytes);

  // Pin the conversion call + JSON marshalling on the Python side so we keep
  // a single source of truth for which Issues fields cross the boundary.
  pyodide.globals.set("_l2a_mode", mode);
  pyodide.globals.set("_l2a_opts", pyodide.toPy(options || {}));

  const payloadJson = pyodide.runPython(`
import json
from pathlib import Path
from converter import convert

opts = _l2a_opts if hasattr(_l2a_opts, "to_py") is False else _l2a_opts.to_py()
if hasattr(opts, "to_py"):
    opts = opts.to_py()

issues = convert(
    input_zip=Path("/tmp/input.zip"),
    output_zip=Path("/tmp/output.zip"),
    dry_run=(_l2a_mode == "validate"),
    flatten=bool(opts.get("flatten")),
    resize=1600 if opts.get("resize") else None,
    guide=bool(opts.get("guide")),
)

def _to_dict(i):
    return {
        "severity": getattr(i, "severity", None),
        "message": getattr(i, "message", str(i)),
        "location": getattr(i, "location", None),
    }

json.dumps({
    "main_tex": issues.main_tex,
    "errors": [_to_dict(i) for i in issues.errors],
    "warnings": [_to_dict(i) for i in issues.warnings],
})
  `);

  const parsed = JSON.parse(payloadJson);
  const diagnostics = [
    ...parsed.errors.map((e) => ({ ...e, severity: "error" })),
    ...parsed.warnings.map((e) => ({ ...e, severity: "warn" })),
  ];

  let outputZip = null;
  if (mode === "clean") {
    try {
      outputZip = pyodide.FS.readFile("/tmp/output.zip");
    } catch (_) {
      // convert() aborted before writing the zip; diagnostics already explain.
      outputZip = null;
    }
  }

  // Clear MEMFS between runs so a second click starts from a known state.
  for (const p of ["/tmp/input.zip", "/tmp/output.zip"]) {
    try {
      pyodide.FS.unlink(p);
    } catch (_) {}
  }

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
