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

const result = await pyodide.runPythonAsync(`
import json
from pathlib import Path
from converter import convert

issues = convert(
    input_zip=Path("/tmp/input.zip"),
    output_zip=Path("/tmp/output.zip"),
    dry_run=False,
)

def issue_to_dict(i):
    return {
        "severity": getattr(i, "severity", None),
        "message": getattr(i, "message", str(i)),
        "location": getattr(i, "location", None),
    }

payload = {
    "main_tex": issues.main_tex,
    "errors": [issue_to_dict(i) for i in issues.errors],
    "warnings": [issue_to_dict(i) for i in issues.warnings],
}
json.dumps(payload)
`);

const issues = JSON.parse(result);
console.log(`main_tex: ${issues.main_tex}`);
console.log(`errors: ${issues.errors.length}`);
console.log(`warnings: ${issues.warnings.length}`);

const outBytes = pyodide.FS.readFile("/tmp/output.zip");
console.log(`output zip size: ${outBytes.length} bytes`);

if (outBytes.length < 200) {
  console.error("FAIL: output zip suspiciously small");
  process.exit(2);
}

console.log("PASS");
