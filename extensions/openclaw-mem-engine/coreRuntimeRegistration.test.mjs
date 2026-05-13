import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "index.ts"), "utf8");

test("core runtime registration uses explicit capability/legacy/skipped branches", () => {
  assert.match(source, /registerMemoryCapability\?\s*:/, "declares capability host seam");
  assert.match(source, /registerMemoryRuntime\?\s*:/, "declares legacy runtime host seam");
  assert.match(source, /typeof runtimeHost\.registerMemoryCapability === "function"/, "checks capability function before registering");
  assert.match(source, /else if \(typeof runtimeHost\.registerMemoryRuntime === "function"\)/, "checks legacy function as fallback");
  assert.match(source, /core memory runtime registration skipped \(host lacks capability hook\)/, "logs skipped path on older hosts");
  assert.doesNotMatch(source, /registerMemoryCapability\?\.\([\s\S]*\?\?/, "does not use void-return nullish chaining for registration dispatch");
});

test("core runtime read previews are direct, bounded, and path-safe", () => {
  assert.match(source, /async getScalarById\(id: string\)/, "has direct single-row lookup");
  assert.match(source, /sliceRuntimeMemoryText\(row\?\.text \?\? "", params\.from, params\.lines\)/, "applies line slicing to readFile output");
  assert.match(source, /nextFrom: sliced\.nextFrom/, "returns continuation when sliced");
  assert.match(source, /sanitizeRuntimeMemoryIdForPath\(item\.row\.id\)/, "sanitizes synthetic paths");
  assert.doesNotMatch(source, /\(await db\.listScalars\(\)\)\.filter\(\(row\) => row\.id === id\)/, "does not scan full table for readFile by id");
});
