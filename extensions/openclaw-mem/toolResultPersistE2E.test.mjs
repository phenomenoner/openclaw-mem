import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import plugin from './index.ts';

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

function createFakeApi({ stateDir, pluginConfig }) {
  const handlers = new Map();

  return {
    pluginConfig,
    config: {
      plugins: {
        slots: { memory: 'openclaw-mem-engine' },
        entries: { 'openclaw-mem-engine': { enabled: true } },
      },
    },
    runtime: {
      state: {
        resolveStateDir: () => stateDir,
      },
    },
    resolvePath: (raw) => {
      if (path.isAbsolute(raw)) return raw;
      if (raw.startsWith('~/')) {
        return path.join(process.env.HOME || stateDir, raw.slice(2));
      }
      return path.resolve(stateDir, raw);
    },
    logger: {
      info: () => {},
      warn: () => {},
    },
    on: (name, handler) => {
      handlers.set(name, handler);
    },
    _handlers: handlers,
  };
}

test('tool_result_persist runtime path writes redacted/non-leaking episodic tool.result lines (including stdout/stderr collapse)', () => {
  const corpus = loadCorpus();
  const highRisk = corpus.cases.find(
    (entry) => entry.class === 'high_risk' && entry?.plugin?.redactionAnchor && (entry?.episodic?.leakNeedles || []).length > 0,
  );
  const benign = corpus.cases.find((entry) => entry.class === 'benign');

  assert.ok(highRisk, 'expected high-risk fixture case');
  assert.ok(benign, 'expected benign fixture case');

  const summaryCap = 96;
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'openclaw-mem-tool-result-persist-e2e-'));

  try {
    const api = createFakeApi({
      stateDir: tmpRoot,
      pluginConfig: {
        enabled: true,
        captureMessage: false,
        redactSensitive: true,
        episodes: {
          enabled: true,
          outputPath: 'memory/openclaw-mem-episodes.e2e.jsonl',
          captureToolCall: false,
          captureToolResult: true,
          captureOpsAlert: false,
          captureConversationUser: false,
          captureConversationAssistant: false,
          maxSummaryLength: summaryCap,
        },
      },
    });

    plugin.register(api);

    const handler = api._handlers.get('tool_result_persist');
    assert.equal(typeof handler, 'function', 'plugin should register tool_result_persist hook');

    handler(
      {
        toolName: 'memory_recall',
        toolCallId: 'call-high',
        message: buildMessage(`Tool output ${highRisk.sample}`),
      },
      {
        sessionKey: 'session-1',
        agentId: 'agent-1',
        toolName: 'memory_recall',
      },
    );

    handler(
      {
        toolName: 'memory_recall',
        toolCallId: 'call-stdout',
        message: buildMessage(
          `stdout: ${highRisk.sample}\nstderr: synthetic failure trace ${highRisk.episodic.leakNeedles?.[0] || 'needle'}`,
        ),
      },
      {
        sessionKey: 'session-1',
        agentId: 'agent-1',
        toolName: 'memory_recall',
      },
    );

    handler(
      {
        toolName: 'memory_recall',
        toolCallId: 'call-benign',
        message: buildMessage(benign.sample),
      },
      {
        sessionKey: 'session-1',
        agentId: 'agent-1',
        toolName: 'memory_recall',
      },
    );

    const spoolPath = path.join(tmpRoot, 'memory', 'openclaw-mem-episodes.e2e.jsonl');
    assert.equal(fs.existsSync(spoolPath), true, 'expected episodic spool file');

    const rawLines = fs
      .readFileSync(spoolPath, 'utf-8')
      .split(/\r?\n/)
      .filter(Boolean);

    const parsed = rawLines.map((line) => ({ raw: line, json: JSON.parse(line) }));
    const resultRows = parsed.filter((row) => row.json.type === 'tool.result');
    assert.equal(resultRows.length, 3, 'expected exactly three tool.result rows');

    const highRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-high');
    const stdoutRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-stdout');
    const benignRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-benign');
    assert.ok(highRow, 'missing high-risk tool.result row');
    assert.ok(stdoutRow, 'missing stdout/stderr-style tool.result row');
    assert.ok(benignRow, 'missing benign tool.result row');

    const highSummary = String(highRow.json.summary || '');
    const highResultSummary = String(highRow.json?.payload?.result_summary || '');
    const highAnchor = highRisk.plugin.redactionAnchor;

    assert.equal(highSummary.includes(highAnchor), true, 'high-risk summary should include redaction anchor');
    assert.equal(highResultSummary.includes(highAnchor), true, 'high-risk payload summary should include redaction anchor');
    assert.equal(highSummary.length <= summaryCap + 1, true, 'high-risk summary should stay bounded');

    for (const needle of highRisk.episodic.leakNeedles || []) {
      assert.equal(highSummary.includes(needle), false, `high-risk summary leaked needle: ${needle}`);
      assert.equal(highResultSummary.includes(needle), false, `high-risk payload summary leaked needle: ${needle}`);
      assert.equal(highRow.raw.includes(needle), false, `high-risk JSONL row leaked needle: ${needle}`);
    }
    assert.equal(highRow.raw.includes(highRisk.sample), false, 'high-risk JSONL row leaked full sample');

    const stdoutSummary = String(stdoutRow.json.summary || '');
    const stdoutResultSummary = String(stdoutRow.json?.payload?.result_summary || '');
    const expectedStdoutSummary = 'memory_recall result captured (output redacted)';

    assert.equal(stdoutSummary, expectedStdoutSummary, 'stdout/stderr summary should collapse to bounded redacted posture');
    assert.equal(
      stdoutResultSummary,
      expectedStdoutSummary,
      'stdout/stderr payload summary should collapse to bounded redacted posture',
    );
    assert.equal(stdoutSummary.length <= summaryCap + 1, true, 'stdout/stderr summary should stay bounded');
    assert.equal(stdoutRow.raw.includes('stdout:'), false, 'stdout/stderr JSONL row should not include raw stdout text');
    assert.equal(stdoutRow.raw.includes('stderr:'), false, 'stdout/stderr JSONL row should not include raw stderr text');
    for (const needle of highRisk.episodic.leakNeedles || []) {
      assert.equal(stdoutSummary.includes(needle), false, `stdout/stderr summary leaked needle: ${needle}`);
      assert.equal(stdoutResultSummary.includes(needle), false, `stdout/stderr payload summary leaked needle: ${needle}`);
      assert.equal(stdoutRow.raw.includes(needle), false, `stdout/stderr JSONL row leaked needle: ${needle}`);
    }
    assert.equal(stdoutRow.raw.includes(highRisk.sample), false, 'stdout/stderr JSONL row leaked full sample');

    const benignSummary = String(benignRow.json.summary || '');
    const benignResultSummary = String(benignRow.json?.payload?.result_summary || '');
    const benignFragment = benign.sample.slice(0, 18).trim();

    assert.equal(benignSummary.length <= summaryCap + 1, true, 'benign summary should stay bounded');
    assert.equal(benignSummary.includes('[REDACTED]'), false, 'benign summary should not be redacted');
    assert.equal(benignResultSummary.includes('[REDACTED]'), false, 'benign payload summary should not be redacted');
    assert.equal(benignSummary.includes(benignFragment), true, 'benign summary should preserve useful text');
    assert.equal(
      benignSummary.includes('result captured (output redacted)'),
      false,
      'benign summary should not be treated as blocked stdout payload',
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
