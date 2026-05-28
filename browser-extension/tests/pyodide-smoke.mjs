// Pyodide-in-Node smoke test for the latex2arxiv wheel running inside Pyodide.
// Verifies: bundled wheels resolve via emfs://; PyPI deps (Pillow, pyyaml, regex)
// resolve from Pyodide's package index; converter.convert() runs end-to-end on
// a fixture zip; Issues object is JSON-marshallable; output zip reads back as
// non-trivial bytes.

import { loadPyodide } from "pyodide";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { execFileSync } from "node:child_process";
import os from "node:os";

const WHEELS_DIR = process.argv[2];
const FIXTURE_PATH = process.argv[3];
if (!WHEELS_DIR || !FIXTURE_PATH) {
  console.error("usage: node pyodide-smoke.mjs <wheels-dir> <fixture-dir-or-zip>");
  process.exit(1);
}

const wheelFiles = fs.readdirSync(WHEELS_DIR).filter((f) => f.endsWith(".whl"));
if (wheelFiles.length === 0) {
  console.error(`no wheels in ${WHEELS_DIR}`);
  process.exit(1);
}

function readFixtureZip(fixturePath) {
  // Accept a .zip directly or a directory we zip with the system `zip`
  // binary (Overleaf-style: files at top level, no wrapper directory).
  const stat = fs.statSync(fixturePath);
  if (stat.isFile()) return fs.readFileSync(fixturePath);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "l2a-smoke-"));
  const zipPath = path.join(tmp, "fixture.zip");
  execFileSync("zip", ["-rq", zipPath, "."], { cwd: fixturePath });
  return fs.readFileSync(zipPath);
}

const fixtureBytes = readFixtureZip(FIXTURE_PATH);

const t0 = Date.now();
const pyodide = await loadPyodide();
console.log(`pyodide booted in ${Date.now() - t0}ms`);

for (const f of wheelFiles) {
  pyodide.FS.writeFile(`/tmp/${f}`, fs.readFileSync(path.join(WHEELS_DIR, f)));
}
pyodide.FS.writeFile("/tmp/input.zip", fixtureBytes);

await pyodide.loadPackage("micropip");
const micropip = pyodide.pyimport("micropip");

const tInstall = Date.now();
// Install the bundled wheels in dependency order — latex2arxiv last so its
// transitive deps are already satisfied by the bundled bibtexparser/pyparsing.
const installList = wheelFiles
  .sort((a, b) => (a.startsWith("latex2arxiv") ? 1 : -1) - (b.startsWith("latex2arxiv") ? 1 : -1))
  .map((f) => `emfs:/tmp/${f}`);
await micropip.install(pyodide.toPy(installList));
console.log(`bundled wheels installed in ${Date.now() - tInstall}ms`);

// Mirror the worker's PY_RUN string verbatim — if these drift, the smoke
// stops verifying what the worker actually executes in production.
const PY_RUN = `
import json
from pathlib import Path
from converter import convert

issues = convert(
    input_zip=Path("/tmp/input.zip"),
    output_zip=Path("/tmp/output.zip"),
    dry_run=(_l2a_mode == "validate"),
    flatten=bool(_l2a_opts.get("flatten")),
    resize=1600 if _l2a_opts.get("resize") else None,
    guide=bool(_l2a_opts.get("guide")),
)

json.dumps({
    "main_tex": issues.main_tex,
    "errors": list(issues.errors),
    "warnings": list(issues.warnings),
})
`;

async function runConvert(mode, options) {
  pyodide.globals.set("_l2a_mode", mode);
  pyodide.globals.set("_l2a_opts", pyodide.toPy(options));
  return JSON.parse(pyodide.runPython(PY_RUN));
}

// Case A: clean mode + all options engaged — exercises every opts.get() arm.
pyodide.FS.writeFile("/tmp/input.zip", fixtureBytes);
const clean = await runConvert("clean", { flatten: true, resize: true, guide: true });
console.log(`[clean] main_tex=${clean.main_tex}, errors=${clean.errors.length}, warnings=${clean.warnings.length}`);
const outBytes = pyodide.FS.readFile("/tmp/output.zip");
console.log(`[clean] output zip size: ${outBytes.length} bytes`);
if (outBytes.length < 200) {
  console.error("FAIL: clean output zip suspiciously small");
  process.exit(2);
}
pyodide.FS.unlink("/tmp/input.zip");
pyodide.FS.unlink("/tmp/output.zip");

// Case B: validate (dry-run) mode + no opts — exercises the validate branch
// and asserts no /tmp/output.zip materializes.
pyodide.FS.writeFile("/tmp/input.zip", fixtureBytes);
const dry = await runConvert("validate", {});
console.log(`[validate] main_tex=${dry.main_tex}, errors=${dry.errors.length}, warnings=${dry.warnings.length}`);
let dryWroteOutput = false;
try {
  pyodide.FS.readFile("/tmp/output.zip");
  dryWroteOutput = true;
} catch (_) {}
if (dryWroteOutput) {
  console.error("FAIL: validate (dry_run) should not produce /tmp/output.zip");
  process.exit(2);
}

console.log("PASS");
