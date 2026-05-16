import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const plugin = JSON.parse(fs.readFileSync(new URL("./openclaw.plugin.json", import.meta.url), "utf8"));
const indexSource = fs.readFileSync(new URL("./index.ts", import.meta.url), "utf8");

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

test("inline config parser rejects invalid symbolicCanvas shapes", () => {
  assert.match(indexSource, /throw new Error\("symbolicCanvas must be a boolean or object"\)/);
  assert.match(indexSource, /throw new Error\("symbolicCanvas\.autoBuild must be a boolean or object"\)/);
  assert.match(indexSource, /assertAllowedKeys\(obj, \["autoBuild"\], "symbolicCanvas config"\)/);
});
