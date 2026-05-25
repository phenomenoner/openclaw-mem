import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const plugin = JSON.parse(fs.readFileSync(new URL("./openclaw.plugin.json", import.meta.url), "utf8"));
const indexSource = fs.readFileSync(new URL("./index.ts", import.meta.url), "utf8");

test("plugin schema exposes retrievalBackend disabled-by-default config", () => {
  const retrieval = plugin.configSchema.properties.retrievalBackend;
  assert.equal(retrieval.type, "object");
  assert.equal(retrieval.additionalProperties, false);
  assert.deepEqual(retrieval.properties.backend.enum, ["lancedb", "qdrant-edge"]);
  assert.equal(retrieval.properties.backend.default, "lancedb");
  assert.equal(retrieval.properties.qdrantEdge.properties.enabled.default, false);
  assert.deepEqual(retrieval.properties.qdrantEdge.properties.fallbackBackend.enum, ["lancedb"]);
  assert.equal(retrieval.properties.qdrantEdge.properties.fallbackBackend.default, "lancedb");
  assert.equal(retrieval.properties.qdrantEdge.properties.searchCommand.default, "python3");
  assert.equal(retrieval.properties.qdrantEdge.properties.timeoutMs.default, 1500);
});

test("plugin ui hints use retrievalBackend naming", () => {
  assert.ok(plugin.uiHints["retrievalBackend.backend"]);
  assert.ok(plugin.uiHints["retrievalBackend.qdrantEdge.enabled"]);
  assert.ok(plugin.uiHints["retrievalBackend.qdrantEdge.shardRoot"]);
  assert.ok(plugin.uiHints["retrievalBackend.qdrantEdge.searchCommand"]);
  assert.match(indexSource, /"retrievalBackend\.backend"/);
  assert.match(indexSource, /"retrievalBackend\.qdrantEdge\.enabled"/);
  assert.match(indexSource, /"retrievalBackend\.qdrantEdge\.shardRoot"/);
  assert.match(indexSource, /"retrievalBackend\.qdrantEdge\.searchCommand"/);
});

test("inline config parser rejects non-object retrievalBackend", () => {
  assert.match(indexSource, /throw new Error\("retrievalBackend config must be an object"\)/);
  assert.match(indexSource, /Array\.isArray\(cfg\.retrievalBackend\)/);
});

test("plugin schema exposes symbolicCanvas autoBuild disabled-by-default config", () => {
  const symbolic = plugin.configSchema.properties.symbolicCanvas;
  assert.equal(symbolic.type, "object");
  assert.equal(symbolic.additionalProperties, false);
  assert.equal(symbolic.properties.autoBuild.properties.enabled.default, false);
  assert.equal(symbolic.properties.autoBuild.properties.outputDir.default, "memory/symbolic-canvas-auto");
  assert.equal(symbolic.properties.autoBuild.properties.minMessages.default, 4);
  assert.ok(plugin.uiHints["symbolicCanvas.autoBuild.enabled"]);
  assert.ok(plugin.uiHints["symbolicCanvas.autoBuild.outputDir"]);
  assert.match(indexSource, /"symbolicCanvas\.autoBuild\.enabled"/);
  assert.match(indexSource, /runSymbolicCanvasAutoBuild/);
});
