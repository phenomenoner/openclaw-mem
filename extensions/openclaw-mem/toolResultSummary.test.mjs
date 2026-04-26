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

test('structured JSON stdout/stderr payloads collapse to redacted-output posture while benign JSON stays informative', () => {
  const corpus = loadCorpus();
  const firstHighRisk = corpus.cases.find((entry) => entry.class === 'high_risk');
  assert.ok(firstHighRisk, 'expected at least one high-risk corpus case');

  const structuredBlocked = buildToolResultSummary(
    'memory_recall',
    buildMessage(
      JSON.stringify({
        stdout: `trace ${firstHighRisk.sample}`,
        stderr: `failure ${firstHighRisk.episodic?.leakNeedles?.[0] || 'needle'}`,
        status: 'error',
      }),
    ),
    true,
    220,
  );

  assert.equal(structuredBlocked, 'memory_recall result captured (output redacted)');
  for (const [idx, needle] of (firstHighRisk.episodic?.leakNeedles ?? []).entries()) {
    assert.equal(
      structuredBlocked.includes(needle),
      false,
      `structured JSON summary leaked forbidden needle #${idx + 1}`,
    );
  }

  const structuredBenign = buildToolResultSummary(
    'memory_recall',
    buildMessage(
      JSON.stringify({
        doc_type: 'api_reference',
        section: 'authentication',
        guidance: 'Bearer token docs should explain rotation policy and vault usage.',
      }),
    ),
    true,
    220,
  );

  assert.equal(structuredBenign.includes('api_reference'), true, 'benign structured JSON should remain informative');
  assert.equal(
    structuredBenign.includes('result captured (output redacted)'),
    false,
    'benign structured JSON should not collapse to output redacted posture',
  );
});

test('benign prose mentioning JSON-escaped "stdout"/"stderr" keys stays informative', () => {
  const summary = buildToolResultSummary(
    'memory_recall',
    buildMessage(
      'Docs note: use JSON-escaped keys \\"stdout\\" and \\"stderr\\" in examples. This sentence is documentation text, not a live output payload.',
    ),
    true,
    220,
  );

  assert.equal(summary.includes('Docs note'), true, 'benign prose should preserve useful docs context');
  assert.equal(
    summary.includes('result captured (output redacted)'),
    false,
    'benign prose should not collapse to output redacted posture',
  );
});

test('malformed JSON-like prose with quoted output-key terms inside string content stays informative', () => {
  const summary = buildToolResultSummary(
    'memory_recall',
    buildMessage(
      '{"note":"guide says, "stdout": "sample" and "stderr": "sample" are docs labels", "status":"ok"',
    ),
    true,
    240,
  );

  assert.equal(summary.includes('guide says'), true, 'malformed JSON-like docs prose should preserve useful context');
  assert.equal(
    summary.includes('result captured (output redacted)'),
    false,
    'malformed JSON-like docs prose should not collapse to output redacted posture',
  );
});

test('malformed JSON-like payload with true output key still collapses to redacted-output posture', () => {
  const summary = buildToolResultSummary(
    'memory_recall',
    buildMessage('{"stdout":"synthetic trace line"'),
    true,
    240,
  );

  assert.equal(summary, 'memory_recall result captured (output redacted)');
});

test('nested malformed JSON-like boundary keeps quoted output-key prose informative but still blocks true nested output keys', () => {
  const nestedQuotedDocsSummary = buildToolResultSummary(
    'memory_recall',
    buildMessage(
      '{"outer":{"items":[{"note":"guide says labels "stdout": "sample" and "stderr": "sample" are docs labels"}],"status":"ok"}',
    ),
    true,
    240,
  );

  assert.equal(
    nestedQuotedDocsSummary.includes('guide says'),
    true,
    'nested malformed JSON-like docs prose should preserve useful context',
  );
  assert.equal(
    nestedQuotedDocsSummary.includes('result captured (output redacted)'),
    false,
    'nested malformed JSON-like docs prose should not collapse to output redacted posture',
  );

  const nestedTrueOutputSummary = buildToolResultSummary(
    'memory_recall',
    buildMessage('{"outer":{"items":[{"stdout":"synthetic trace line"}],"status":"error"}'),
    true,
    240,
  );

  assert.equal(nestedTrueOutputSummary, 'memory_recall result captured (output redacted)');
});

test('array-first malformed JSON-like boundary keeps quoted output-key prose informative but still blocks true nested output keys', () => {
  const arrayQuotedDocsSummary = buildToolResultSummary(
    'memory_recall',
    buildMessage(
      '[{"note":"guide says labels "stdout": "sample" and "stderr": "sample" are docs labels"},{"status":"ok"}',
    ),
    true,
    240,
  );

  assert.equal(
    arrayQuotedDocsSummary.includes('guide says'),
    true,
    'array-first malformed JSON-like docs prose should preserve useful context',
  );
  assert.equal(
    arrayQuotedDocsSummary.includes('result captured (output redacted)'),
    false,
    'array-first malformed JSON-like docs prose should not collapse to output redacted posture',
  );

  const syntheticNeedle = 'sk-proj-ARRAYROOTBOUNDARYNEEDLE1234567890';
  const arrayLikeOutputKeys = [
    'stdout',
    'stderr',
    'raw_stdout',
    'raw_stderr',
    'tool_output',
    'command_output',
  ];

  for (const outputKey of arrayLikeOutputKeys) {
    const aliasSummary = buildToolResultSummary(
      'memory_recall',
      buildMessage(`[{"meta":"ok"},{"${outputKey}":"synthetic trace line ${syntheticNeedle}"}`),
      true,
      240,
    );

    assert.equal(aliasSummary, 'memory_recall result captured (output redacted)');
    assert.equal(
      aliasSummary.includes(syntheticNeedle),
      false,
      `array-first malformed JSON-like ${outputKey} summary must not leak synthetic needle`,
    );
  }
});
