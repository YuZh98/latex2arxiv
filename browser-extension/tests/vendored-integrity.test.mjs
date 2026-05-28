// Re-verify the sha256 hashes recorded in pyodide/integrity.json against the
// committed files. Catches partial extractions, accidental hand-edits, and
// tampered cached Pyodide assets at Chrome Web Store review.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PYODIDE_DIR = path.resolve(__dirname, "..", "pyodide");
const INTEGRITY_PATH = path.join(PYODIDE_DIR, "integrity.json");

const integrity = JSON.parse(fs.readFileSync(INTEGRITY_PATH, "utf-8"));

function verifyIntegrityAt(dir) {
  const data = JSON.parse(fs.readFileSync(path.join(dir, "integrity.json"), "utf-8"));
  for (const entry of data.files) {
    const actual = crypto.createHash("sha256").update(fs.readFileSync(path.join(dir, entry.path))).digest("hex");
    if (actual !== entry.sha256) {
      throw new Error(`sha256 mismatch for ${entry.path}: expected ${entry.sha256}, got ${actual}`);
    }
  }
}

test("integrity.json declares a pyodide_version", () => {
  assert.equal(typeof integrity.pyodide_version, "string");
  assert.match(integrity.pyodide_version, /^\d+\.\d+\.\d+$/);
});

test("integrity.json declares at least one file", () => {
  assert.ok(Array.isArray(integrity.files) && integrity.files.length > 0);
});

test("every declared file is present on disk", () => {
  for (const entry of integrity.files) {
    const p = path.join(PYODIDE_DIR, entry.path);
    assert.ok(fs.existsSync(p), `missing: ${entry.path}`);
  }
});

test("every declared sha256 matches the file on disk", () => {
  for (const entry of integrity.files) {
    const p = path.join(PYODIDE_DIR, entry.path);
    const actual = crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
    assert.equal(actual, entry.sha256, `sha256 mismatch for ${entry.path}`);
  }
});

test("integrity.json has no duplicate paths", () => {
  const seen = new Set();
  for (const entry of integrity.files) {
    assert.ok(!seen.has(entry.path), `duplicate path: ${entry.path}`);
    seen.add(entry.path);
  }
});

test("core runtime files are present", () => {
  // Cheap regression guard against a future trim that accidentally drops one
  // of the four files loadPyodide() needs at boot. The script's own selector
  // is the source of truth; this test pins the floor.
  const REQUIRED = new Set(["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "pyodide-lock.json", "python_stdlib.zip"]);
  const paths = new Set(integrity.files.map((e) => e.path));
  for (const r of REQUIRED) {
    assert.ok(paths.has(r), `core runtime file missing from vendored set: ${r}`);
  }
});

test("a tampered file in a fixture dir is detected as a sha256 mismatch", (t) => {
  // Negative path: copy the real layout into a tempdir, flip one byte in the
  // first vendored file, and assert verifyIntegrityAt throws. Catches the
  // empty-loop / silent-pass regression class.
  const fixtureDir = fs.mkdtempSync(path.join(os.tmpdir(), "l2a-pyodide-fixture-"));
  t.after(() => fs.rmSync(fixtureDir, { recursive: true, force: true }));
  fs.cpSync(PYODIDE_DIR, fixtureDir, { recursive: true });
  const target = path.join(fixtureDir, integrity.files[0].path);
  const bytes = fs.readFileSync(target);
  bytes[0] = bytes[0] ^ 0x01;
  fs.writeFileSync(target, bytes);
  assert.throws(() => verifyIntegrityAt(fixtureDir), /sha256 mismatch/);
});
