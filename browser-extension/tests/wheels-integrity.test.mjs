// Tests for lib/wheels-integrity.mjs. Cover happy path (real wheels dir),
// schema breaks (missing name/sha256), missing file, and tamper detection.

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

import { verifyWheels } from "./lib/wheels-integrity.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REAL_WHEELS_DIR = path.resolve(__dirname, "..", "wheels");

function makeFixture(entries, files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "l2a-wheels-"));
  fs.writeFileSync(path.join(dir, "index.json"), JSON.stringify({ wheels: entries }));
  for (const [name, bytes] of Object.entries(files)) {
    fs.writeFileSync(path.join(dir, name), bytes);
  }
  return dir;
}

function sha256Hex(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

test("real wheels dir passes integrity check", () => {
  const entries = verifyWheels(REAL_WHEELS_DIR);
  assert.ok(Array.isArray(entries) && entries.length >= 1, "real wheels dir should have at least one wheel");
});

test("missing sha256 field throws", () => {
  const bytes = Buffer.from("fake wheel");
  const dir = makeFixture([{ name: "fake-1.0-py3-none-any.whl" }], { "fake-1.0-py3-none-any.whl": bytes });
  assert.throws(() => verifyWheels(dir), /missing name or sha256/);
});

test("missing name field throws", () => {
  const dir = makeFixture([{ sha256: "deadbeef" }], {});
  assert.throws(() => verifyWheels(dir), /missing name or sha256/);
});

test("missing wheel file throws", () => {
  const dir = makeFixture(
    [{ name: "ghost-1.0-py3-none-any.whl", sha256: "deadbeef" }],
    {}, // no actual file
  );
  assert.throws(() => verifyWheels(dir), /file does not exist/);
});

test("sha256 mismatch (one tampered byte) throws", () => {
  const real = Buffer.from("the original payload");
  const tampered = Buffer.from(real);
  tampered[0] = real[0] ^ 0x01; // flip one bit
  const realHash = sha256Hex(real);
  const dir = makeFixture(
    [{ name: "tampered-1.0-py3-none-any.whl", sha256: realHash }],
    { "tampered-1.0-py3-none-any.whl": tampered },
  );
  assert.throws(() => verifyWheels(dir), /sha256 mismatch/);
});

test("empty wheels array throws", () => {
  const dir = makeFixture([], {});
  assert.throws(() => verifyWheels(dir), /no 'wheels' array/);
});
