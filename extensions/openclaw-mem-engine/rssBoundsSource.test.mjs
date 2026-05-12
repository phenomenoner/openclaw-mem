import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("./index.ts", import.meta.url), "utf8");
const schema = JSON.parse(fs.readFileSync(new URL("./openclaw.plugin.json", import.meta.url), "utf8"));

test("autoCapture has front-loaded RSS input bounds before candidate extraction", () => {
  assert.match(source, /AUTO_CAPTURE_MAX_SCANNED_USER_MESSAGES = 64/);
  assert.match(source, /AUTO_CAPTURE_MAX_TEXT_BLOCKS_PER_MESSAGE = 8/);
  assert.match(source, /AUTO_CAPTURE_MAX_TOTAL_INPUT_CHARS = 120_000/);
  assert.match(source, /userMessages\.slice\(-maxMessages\)/);
  assert.match(source, /maxTotalInputChars - stats\.scannedTextChars/);
  assert.match(source, /maxMessages: autoCaptureCfg\.maxScannedUserMessages/);
  assert.match(source, /scanned: \{\s*userMessages: extracted\.stats\.scannedUserMessages/s);
});

test("prompt hook dedupe map has a hard cap", () => {
  assert.match(source, /PROMPT_MUTATION_HOOK_DEDUPE_MAX_ENTRIES = 1024/);
  assert.match(source, /function capPromptMutationHookRuns/);
  assert.match(source, /capPromptMutationHookRuns\(promptMutationHookRuns, PROMPT_MUTATION_HOOK_DEDUPE_MAX_ENTRIES\)/);
});

test("plugin schema exposes bounded RSS knobs", () => {
  const routeAuto = schema.configSchema.properties.autoRecall.oneOf[1].properties.routeAuto.properties;
  assert.equal(routeAuto.maxBufferBytes.default, 524288);
  assert.equal(routeAuto.maxBufferBytes.maximum, 2097152);

  const autoCapture = schema.configSchema.properties.autoCapture.oneOf[1].properties;
  assert.equal(autoCapture.maxScannedUserMessages.default, 24);
  assert.equal(autoCapture.maxScannedUserMessages.maximum, 64);
  assert.equal(autoCapture.maxTextBlocksPerMessage.default, 4);
  assert.equal(autoCapture.maxTotalInputChars.default, 48000);
  assert.equal(autoCapture.maxTotalInputChars.maximum, 120000);
});
