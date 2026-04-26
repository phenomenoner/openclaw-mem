import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { buildToolResultSummary } from './toolResultSummary.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FIXTURE_PATH = path.join(REPO_ROOT, 'tests', 'data', 'SECRET_DETECTOR_GOLDEN.v1.json');

function loadCorpus() {
  const payload = JSON.parse(fs.readFileSync(FIXTURE_PATH, 'utf-8'));
  assert.equal(payload.schema, 'openclaw-mem.secret-detector-golden.v1');
  return payload;
}

function buildMessage(text) {
  return {
    content: [{ type: 'text', text }],
  };
}

test('tool-result summary redacts high-risk golden corpus cases without leaking needles', () => {
  const corpus = loadCorpus();

  for (const entry of corpus.cases) {
    if (entry.class !== 'high_risk') continue;

    const summary = buildToolResultSummary(
      'memory_recall',
      buildMessage(`Tool output ${entry.sample}`),
      true,
      220,
    );

    const redactionAnchor = entry.plugin?.redactionAnchor;
    if (redactionAnchor) {
      assert.equal(
        summary.includes(redactionAnchor),
        true,
        `expected plugin redaction anchor in summary (${entry.id})`,
      );
    }

    for (const [idx, needle] of (entry.episodic?.leakNeedles ?? []).entries()) {
      assert.equal(
        summary.includes(needle),
        false,
        `summary leaked forbidden needle #${idx + 1} (${entry.id})`,
      );
    }
  }
});

test('tool-result summary does not over-block benign golden corpus cases', () => {
  const corpus = loadCorpus();

  for (const entry of corpus.cases) {
    if (entry.class !== 'benign') continue;

    const summary = buildToolResultSummary('memory_recall', buildMessage(entry.sample), true, 220);
    const expectedFragment = entry.sample.slice(0, 18).trim();

    assert.equal(summary.includes('[REDACTED]'), false, `benign sample was redacted (${entry.id})`);
    assert.equal(
      summary.includes(expectedFragment),
      true,
      `benign sample fragment missing from summary (${entry.id})`,
    );
    assert.equal(
      summary.includes('result captured (output redacted)'),
      false,
      `benign sample incorrectly treated as output block (${entry.id})`,
    );
  }
});

test('stdout-like payload summary stays bounded and does not include secret-like text', () => {
  const corpus = loadCorpus();
  const firstHighRisk = corpus.cases.find((entry) => entry.class === 'high_risk');
  assert.ok(firstHighRisk, 'expected at least one high-risk corpus case');

  const summary = buildToolResultSummary(
    'memory_recall',
    buildMessage(`stdout: ${firstHighRisk.sample}`),
    true,
    220,
  );

  assert.equal(summary, 'memory_recall result captured (output redacted)');
  for (const [idx, needle] of (firstHighRisk.episodic?.leakNeedles ?? []).entries()) {
    assert.equal(
      summary.includes(needle),
      false,
      `stdout summary leaked forbidden needle #${idx + 1}`,
    );
  }
});
