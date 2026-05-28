// Wheel index + sha256 verification. Used by the Node smoke test directly
// and by the Node:test unit tests (with tampered fixtures). The browser
// worker mirrors the same logic in worker.js using crypto.subtle.digest;
// keeping the algorithm here and a parallel implementation in worker.js is
// the cost of running the same check in two runtimes.

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

export function verifyWheels(wheelsDir) {
  const indexJsonPath = path.join(wheelsDir, "index.json");
  const index = JSON.parse(fs.readFileSync(indexJsonPath, "utf-8"));
  const entries = index.wheels;
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error(`${indexJsonPath} has no 'wheels' array`);
  }
  for (const entry of entries) {
    if (!entry || typeof entry.name !== "string" || typeof entry.sha256 !== "string") {
      throw new Error(`index.json entry missing name or sha256: ${JSON.stringify(entry)}`);
    }
    const wheelPath = path.join(wheelsDir, entry.name);
    if (!fs.existsSync(wheelPath)) {
      throw new Error(`index.json lists ${entry.name} but the file does not exist in ${wheelsDir}`);
    }
    const actual = crypto.createHash("sha256").update(fs.readFileSync(wheelPath)).digest("hex");
    if (actual !== entry.sha256.toLowerCase()) {
      throw new Error(`sha256 mismatch for ${entry.name}: expected ${entry.sha256}, got ${actual}`);
    }
  }
  return entries;
}
