import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');

const FIXTURE_PATH = path.join(REPO_ROOT, 'tests', 'data', 'SECRET_DETECTOR_GOLDEN.v1.json');
const MEM_ENGINE_TS_PATH = path.join(REPO_ROOT, 'extensions', 'openclaw-mem-engine', 'index.ts');
const SIDECAR_PLUGIN_TS_PATH = path.join(REPO_ROOT, 'extensions', 'openclaw-mem', 'index.ts');

function loadCorpus() {
  const payload = JSON.parse(fs.readFileSync(FIXTURE_PATH, 'utf-8'));
  assert.equal(payload.schema, 'openclaw-mem.secret-detector-golden.v1');
  return payload;
}

test('shared secret-detector corpus maps to mem-engine and sidecar/plugin source anchors', () => {
  const corpus = loadCorpus();
  const memEngineTs = fs.readFileSync(MEM_ENGINE_TS_PATH, 'utf-8');
  const pluginTs = fs.readFileSync(SIDECAR_PLUGIN_TS_PATH, 'utf-8');

  for (const entry of corpus.cases) {
    if (entry.class !== 'high_risk') continue;

    if (entry.mem_engine?.detectorAnchor) {
      assert.ok(
        memEngineTs.includes(entry.mem_engine.detectorAnchor),
        `missing mem-engine detector anchor for ${entry.id}`,
      );
    }
    if (entry.mem_engine?.redactionAnchor) {
      assert.ok(
        memEngineTs.includes(entry.mem_engine.redactionAnchor),
        `missing mem-engine redaction anchor for ${entry.id}`,
      );
    }
    if (entry.plugin?.redactionAnchor) {
      assert.ok(
        pluginTs.includes(entry.plugin.redactionAnchor),
        `missing plugin redaction anchor for ${entry.id}`,
      );
    }
  }
});

test('autoCapture receipt block remains aggregate-only and non-leaking', () => {
  const corpus = loadCorpus();
  const memEngineTs = fs.readFileSync(MEM_ENGINE_TS_PATH, 'utf-8');

  const receiptMatch = memEngineTs.match(
    /function buildAutoCaptureLifecycleReceipt\([\s\S]*?\n}\n\nfunction renderAutoRecallReceiptComment/,
  );
  assert.ok(receiptMatch, 'missing buildAutoCaptureLifecycleReceipt function');
  const receiptBlock = receiptMatch[0];

  for (const forbidden of corpus.receipt_expectations?.memEngineAutoCapture?.forbidFields ?? []) {
    assert.equal(
      receiptBlock.includes(forbidden),
      false,
      `receipt block leaked forbidden field marker: ${forbidden}`,
    );
  }

  for (const entry of corpus.cases) {
    for (const needle of entry.episodic?.leakNeedles ?? []) {
      assert.equal(
        receiptBlock.includes(needle),
        false,
        `receipt block should not contain golden leak needle for ${entry.id}`,
      );
    }
  }
});
