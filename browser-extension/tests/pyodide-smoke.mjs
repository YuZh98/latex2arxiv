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
import { fileURLToPath } from "node:url";
import { verifyWheels } from "./lib/wheels-integrity.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PY_RUN_PATH = path.resolve(__dirname, "..", "py", "run.py");

const WHEELS_DIR = process.argv[2];
const FIXTURE_PATH = process.argv[3];
if (!WHEELS_DIR || !FIXTURE_PATH) {
  console.error("usage: node pyodide-smoke.mjs <wheels-dir> <fixture-dir-or-zip>");
  process.exit(1);
}

// Read the same index.json the worker reads in production. Going through
// the index — not fs.readdirSync — is what makes the smoke a faithful
// rehearsal of init(): an index entry that does not exist on disk fails
// here the same way it would fail in the browser. verifyWheels also pins
// sha256 so the smoke catches the same tampering the worker would.
const wheelEntries = verifyWheels(WHEELS_DIR);

const cleanupDirs = [];
process.on("exit", () => {
  for (const d of cleanupDirs) {
    try {
      fs.rmSync(d, { recursive: true, force: true });
    } catch (_) {}
  }
});

function readFixtureZip(fixturePath) {
  // Accept a .zip directly or a directory we zip with the system `zip`
  // binary (Overleaf-style: files at top level, no wrapper directory).
  const stat = fs.statSync(fixturePath);
  if (stat.isFile()) return fs.readFileSync(fixturePath);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "l2a-smoke-"));
  cleanupDirs.push(tmp);
  const zipPath = path.join(tmp, "fixture.zip");
  execFileSync("zip", ["-rq", zipPath, "."], { cwd: fixturePath });
  return fs.readFileSync(zipPath);
}

const fixtureBytes = readFixtureZip(FIXTURE_PATH);

const t0 = Date.now();
const pyodide = await loadPyodide();
console.log(`pyodide booted in ${Date.now() - t0}ms`);

for (const entry of wheelEntries) {
  pyodide.FS.writeFile(`/tmp/${entry.name}`, fs.readFileSync(path.join(WHEELS_DIR, entry.name)));
}
pyodide.FS.writeFile("/tmp/input.zip", fixtureBytes);

await pyodide.loadPackage("micropip");
const micropip = pyodide.pyimport("micropip");

const tInstall = Date.now();
// Honour the order from index.json — deps before dependents — instead of
// re-sorting here. If the index ordering is wrong, the smoke fails the way
// the worker would.
const installList = wheelEntries.map((entry) => `emfs:/tmp/${entry.name}`);
await micropip.install(pyodide.toPy(installList));
console.log(`bundled wheels installed in ${Date.now() - tInstall}ms`);

// Load the same Python entrypoint the worker fetches at init time. Both
// sides resolve the same file on disk — if drift creeps in, only one
// place can be the source of truth, and that place is browser-extension/py/run.py.
const PY_RUN = fs.readFileSync(PY_RUN_PATH, "utf-8");

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
