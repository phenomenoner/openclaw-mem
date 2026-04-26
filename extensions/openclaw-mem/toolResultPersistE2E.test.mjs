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
        toolCallId: 'call-json-stdout',
        message: buildMessage(
          JSON.stringify({
            status: 'error',
            stdout: `trace ${highRisk.sample}`,
            stderr: `synthetic failure trace ${highRisk.episodic.leakNeedles?.[0] || 'needle'}`,
            meta: { section: 'diagnostics' },
          }),
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
        toolCallId: 'call-json-benign',
        message: buildMessage(
          JSON.stringify({
            doc_type: 'api_reference',
            section: 'authentication',
            guidance: 'Bearer token docs should explain rotation policy and vault usage.',
          }),
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
        toolCallId: 'call-json-escaped-keys-doc',
        message: buildMessage(
          'Docs note: use JSON-escaped keys \\"stdout\\" and \\"stderr\\" in examples. This sentence is documentation text, not a live output payload.',
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
        toolCallId: 'call-json-malformed-quoted-output-doc',
        message: buildMessage(
          '{"note":"guide says, "stdout": "sample" and "stderr": "sample" are docs labels", "status":"ok"',
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
        toolCallId: 'call-json-malformed-nested-quoted-output-doc',
        message: buildMessage(
          '{"outer":{"items":[{"note":"guide says labels "stdout": "sample" and "stderr": "sample" are docs labels"}],"status":"ok"}',
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
        toolCallId: 'call-json-malformed-array-quoted-output-doc',
        message: buildMessage(
          '[{"note":"guide says labels "stdout": "sample" and "stderr": "sample" are docs labels"},{"status":"ok"}',
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
        toolCallId: 'call-json-malformed-keylike-stdout',
        message: buildMessage('{"stdout":"synthetic trace line"'),
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
        toolCallId: 'call-json-malformed-nested-keylike-stdout',
        message: buildMessage('{"outer":{"items":[{"stdout":"synthetic trace line"}],"status":"error"}'),
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
        toolCallId: 'call-json-malformed-array-keylike-stdout',
        message: buildMessage(
          `[{"meta":"ok"},{"stdout":"synthetic trace ${highRisk.sample} ${highRisk.episodic.leakNeedles?.[0] || 'needle'}"}`,
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
    assert.equal(resultRows.length, 12, 'expected exactly twelve tool.result rows');

    const highRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-high');
    const stdoutRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-stdout');
    const jsonStdoutRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-json-stdout');
    const jsonBenignRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-json-benign');
    const jsonEscapedKeysDocRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-json-escaped-keys-doc');
    const jsonMalformedQuotedOutputDocRow = resultRows.find(
      (row) => row.json?.payload?.tool_call_id === 'call-json-malformed-quoted-output-doc',
    );
    const jsonMalformedNestedQuotedOutputDocRow = resultRows.find(
      (row) => row.json?.payload?.tool_call_id === 'call-json-malformed-nested-quoted-output-doc',
    );
    const jsonMalformedArrayQuotedOutputDocRow = resultRows.find(
      (row) => row.json?.payload?.tool_call_id === 'call-json-malformed-array-quoted-output-doc',
    );
    const jsonMalformedKeylikeStdoutRow = resultRows.find(
      (row) => row.json?.payload?.tool_call_id === 'call-json-malformed-keylike-stdout',
    );
    const jsonMalformedNestedKeylikeStdoutRow = resultRows.find(
      (row) => row.json?.payload?.tool_call_id === 'call-json-malformed-nested-keylike-stdout',
    );
    const jsonMalformedArrayKeylikeStdoutRow = resultRows.find(
      (row) => row.json?.payload?.tool_call_id === 'call-json-malformed-array-keylike-stdout',
    );
    const benignRow = resultRows.find((row) => row.json?.payload?.tool_call_id === 'call-benign');
    assert.ok(highRow, 'missing high-risk tool.result row');
    assert.ok(stdoutRow, 'missing stdout/stderr-style tool.result row');
    assert.ok(jsonStdoutRow, 'missing structured JSON stdout/stderr tool.result row');
    assert.ok(jsonBenignRow, 'missing structured benign JSON tool.result row');
    assert.ok(jsonEscapedKeysDocRow, 'missing escaped output-key docs tool.result row');
    assert.ok(jsonMalformedQuotedOutputDocRow, 'missing malformed JSON-like quoted output-key docs tool.result row');
    assert.ok(
      jsonMalformedNestedQuotedOutputDocRow,
      'missing malformed nested JSON-like quoted output-key docs tool.result row',
    );
    assert.ok(
      jsonMalformedArrayQuotedOutputDocRow,
      'missing malformed array-first JSON-like quoted output-key docs tool.result row',
    );
    assert.ok(jsonMalformedKeylikeStdoutRow, 'missing malformed JSON-like key-like stdout tool.result row');
    assert.ok(
      jsonMalformedNestedKeylikeStdoutRow,
      'missing malformed nested JSON-like key-like stdout tool.result row',
    );
    assert.ok(
      jsonMalformedArrayKeylikeStdoutRow,
      'missing malformed array-first JSON-like key-like stdout tool.result row',
    );
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

    const jsonStdoutSummary = String(jsonStdoutRow.json.summary || '');
    const jsonStdoutResultSummary = String(jsonStdoutRow.json?.payload?.result_summary || '');

    assert.equal(
      jsonStdoutSummary,
      expectedStdoutSummary,
      'structured JSON stdout/stderr summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonStdoutResultSummary,
      expectedStdoutSummary,
      'structured JSON stdout/stderr payload summary should collapse to bounded redacted posture',
    );
    assert.equal(jsonStdoutSummary.length <= summaryCap + 1, true, 'structured JSON stdout/stderr summary should stay bounded');
    assert.equal(jsonStdoutRow.raw.includes('"stdout"'), false, 'structured JSON stdout/stderr JSONL row should not include stdout key');
    assert.equal(jsonStdoutRow.raw.includes('"stderr"'), false, 'structured JSON stdout/stderr JSONL row should not include stderr key');
    for (const needle of highRisk.episodic.leakNeedles || []) {
      assert.equal(jsonStdoutSummary.includes(needle), false, `structured JSON stdout/stderr summary leaked needle: ${needle}`);
      assert.equal(
        jsonStdoutResultSummary.includes(needle),
        false,
        `structured JSON stdout/stderr payload summary leaked needle: ${needle}`,
      );
      assert.equal(jsonStdoutRow.raw.includes(needle), false, `structured JSON stdout/stderr JSONL row leaked needle: ${needle}`);
    }
    assert.equal(jsonStdoutRow.raw.includes(highRisk.sample), false, 'structured JSON stdout/stderr JSONL row leaked full sample');

    const jsonBenignSummary = String(jsonBenignRow.json.summary || '');
    const jsonBenignResultSummary = String(jsonBenignRow.json?.payload?.result_summary || '');

    assert.equal(jsonBenignSummary.length <= summaryCap + 1, true, 'structured benign JSON summary should stay bounded');
    assert.equal(jsonBenignSummary.includes('[REDACTED]'), false, 'structured benign JSON summary should not be redacted');
    assert.equal(
      jsonBenignResultSummary.includes('[REDACTED]'),
      false,
      'structured benign JSON payload summary should not be redacted',
    );
    assert.equal(jsonBenignSummary.includes('api_reference'), true, 'structured benign JSON summary should preserve useful docs text');
    assert.equal(
      jsonBenignSummary.includes('result captured (output redacted)'),
      false,
      'structured benign JSON summary should not be treated as blocked stdout payload',
    );

    const jsonEscapedKeysDocSummary = String(jsonEscapedKeysDocRow.json.summary || '');
    const jsonEscapedKeysDocResultSummary = String(jsonEscapedKeysDocRow.json?.payload?.result_summary || '');

    assert.equal(jsonEscapedKeysDocSummary.length <= summaryCap + 1, true, 'escaped output-key docs summary should stay bounded');
    assert.equal(
      jsonEscapedKeysDocSummary.includes('Docs note'),
      true,
      'escaped output-key docs summary should preserve useful docs text',
    );
    assert.equal(
      jsonEscapedKeysDocResultSummary.includes('Docs note'),
      true,
      'escaped output-key docs payload summary should preserve useful docs text',
    );
    assert.equal(
      jsonEscapedKeysDocSummary.includes('result captured (output redacted)'),
      false,
      'escaped output-key docs summary should not collapse to blocked stdout posture',
    );
    assert.equal(
      jsonEscapedKeysDocResultSummary.includes('result captured (output redacted)'),
      false,
      'escaped output-key docs payload summary should not collapse to blocked stdout posture',
    );
    for (const needle of highRisk.episodic.leakNeedles || []) {
      assert.equal(
        jsonEscapedKeysDocSummary.includes(needle),
        false,
        `escaped output-key docs summary leaked high-risk needle: ${needle}`,
      );
      assert.equal(
        jsonEscapedKeysDocResultSummary.includes(needle),
        false,
        `escaped output-key docs payload summary leaked high-risk needle: ${needle}`,
      );
      assert.equal(
        jsonEscapedKeysDocRow.raw.includes(needle),
        false,
        `escaped output-key docs JSONL row leaked high-risk needle: ${needle}`,
      );
    }

    const jsonMalformedQuotedOutputDocSummary = String(jsonMalformedQuotedOutputDocRow.json.summary || '');
    const jsonMalformedQuotedOutputDocResultSummary = String(
      jsonMalformedQuotedOutputDocRow.json?.payload?.result_summary || '',
    );

    assert.equal(
      jsonMalformedQuotedOutputDocSummary.length <= summaryCap + 1,
      true,
      'malformed JSON-like quoted output-key docs summary should stay bounded',
    );
    assert.equal(
      jsonMalformedQuotedOutputDocSummary.includes('guide says'),
      true,
      'malformed JSON-like quoted output-key docs summary should preserve useful docs text',
    );
    assert.equal(
      jsonMalformedQuotedOutputDocResultSummary.includes('guide says'),
      true,
      'malformed JSON-like quoted output-key docs payload summary should preserve useful docs text',
    );
    assert.equal(
      jsonMalformedQuotedOutputDocSummary.includes('result captured (output redacted)'),
      false,
      'malformed JSON-like quoted output-key docs summary should not collapse to blocked stdout posture',
    );
    assert.equal(
      jsonMalformedQuotedOutputDocResultSummary.includes('result captured (output redacted)'),
      false,
      'malformed JSON-like quoted output-key docs payload summary should not collapse to blocked stdout posture',
    );

    const jsonMalformedNestedQuotedOutputDocSummary = String(jsonMalformedNestedQuotedOutputDocRow.json.summary || '');
    const jsonMalformedNestedQuotedOutputDocResultSummary = String(
      jsonMalformedNestedQuotedOutputDocRow.json?.payload?.result_summary || '',
    );

    assert.equal(
      jsonMalformedNestedQuotedOutputDocSummary.length <= summaryCap + 1,
      true,
      'malformed nested JSON-like quoted output-key docs summary should stay bounded',
    );
    assert.equal(
      jsonMalformedNestedQuotedOutputDocSummary.includes('guide says'),
      true,
      'malformed nested JSON-like quoted output-key docs summary should preserve useful docs text',
    );
    assert.equal(
      jsonMalformedNestedQuotedOutputDocResultSummary.includes('guide says'),
      true,
      'malformed nested JSON-like quoted output-key docs payload summary should preserve useful docs text',
    );
    assert.equal(
      jsonMalformedNestedQuotedOutputDocSummary.includes('result captured (output redacted)'),
      false,
      'malformed nested JSON-like quoted output-key docs summary should not collapse to blocked stdout posture',
    );
    assert.equal(
      jsonMalformedNestedQuotedOutputDocResultSummary.includes('result captured (output redacted)'),
      false,
      'malformed nested JSON-like quoted output-key docs payload summary should not collapse to blocked stdout posture',
    );

    const jsonMalformedArrayQuotedOutputDocSummary = String(jsonMalformedArrayQuotedOutputDocRow.json.summary || '');
    const jsonMalformedArrayQuotedOutputDocResultSummary = String(
      jsonMalformedArrayQuotedOutputDocRow.json?.payload?.result_summary || '',
    );

    assert.equal(
      jsonMalformedArrayQuotedOutputDocSummary.length <= summaryCap + 1,
      true,
      'malformed array-first JSON-like quoted output-key docs summary should stay bounded',
    );
    assert.equal(
      jsonMalformedArrayQuotedOutputDocSummary.includes('guide says'),
      true,
      'malformed array-first JSON-like quoted output-key docs summary should preserve useful docs text',
    );
    assert.equal(
      jsonMalformedArrayQuotedOutputDocResultSummary.includes('guide says'),
      true,
      'malformed array-first JSON-like quoted output-key docs payload summary should preserve useful docs text',
    );
    assert.equal(
      jsonMalformedArrayQuotedOutputDocSummary.includes('result captured (output redacted)'),
      false,
      'malformed array-first JSON-like quoted output-key docs summary should not collapse to blocked stdout posture',
    );
    assert.equal(
      jsonMalformedArrayQuotedOutputDocResultSummary.includes('result captured (output redacted)'),
      false,
      'malformed array-first JSON-like quoted output-key docs payload summary should not collapse to blocked stdout posture',
    );

    const jsonMalformedKeylikeStdoutSummary = String(jsonMalformedKeylikeStdoutRow.json.summary || '');
    const jsonMalformedKeylikeStdoutResultSummary = String(jsonMalformedKeylikeStdoutRow.json?.payload?.result_summary || '');

    assert.equal(
      jsonMalformedKeylikeStdoutSummary,
      expectedStdoutSummary,
      'malformed JSON-like key-like stdout summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonMalformedKeylikeStdoutResultSummary,
      expectedStdoutSummary,
      'malformed JSON-like key-like stdout payload summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonMalformedKeylikeStdoutRow.raw.includes('"stdout"'),
      false,
      'malformed JSON-like key-like stdout JSONL row should not include stdout key text',
    );

    const jsonMalformedNestedKeylikeStdoutSummary = String(jsonMalformedNestedKeylikeStdoutRow.json.summary || '');
    const jsonMalformedNestedKeylikeStdoutResultSummary = String(
      jsonMalformedNestedKeylikeStdoutRow.json?.payload?.result_summary || '',
    );

    assert.equal(
      jsonMalformedNestedKeylikeStdoutSummary,
      expectedStdoutSummary,
      'malformed nested JSON-like key-like stdout summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonMalformedNestedKeylikeStdoutResultSummary,
      expectedStdoutSummary,
      'malformed nested JSON-like key-like stdout payload summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonMalformedNestedKeylikeStdoutRow.raw.includes('"stdout"'),
      false,
      'malformed nested JSON-like key-like stdout JSONL row should not include stdout key text',
    );

    const jsonMalformedArrayKeylikeStdoutSummary = String(jsonMalformedArrayKeylikeStdoutRow.json.summary || '');
    const jsonMalformedArrayKeylikeStdoutResultSummary = String(
      jsonMalformedArrayKeylikeStdoutRow.json?.payload?.result_summary || '',
    );

    assert.equal(
      jsonMalformedArrayKeylikeStdoutSummary,
      expectedStdoutSummary,
      'malformed array-first JSON-like key-like stdout summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonMalformedArrayKeylikeStdoutResultSummary,
      expectedStdoutSummary,
      'malformed array-first JSON-like key-like stdout payload summary should collapse to bounded redacted posture',
    );
    assert.equal(
      jsonMalformedArrayKeylikeStdoutRow.raw.includes('"stdout"'),
      false,
      'malformed array-first JSON-like key-like stdout JSONL row should not include stdout key text',
    );
    for (const needle of highRisk.episodic.leakNeedles || []) {
      assert.equal(
        jsonMalformedArrayKeylikeStdoutSummary.includes(needle),
        false,
        `malformed array-first JSON-like key-like stdout summary leaked needle: ${needle}`,
      );
      assert.equal(
        jsonMalformedArrayKeylikeStdoutResultSummary.includes(needle),
        false,
        `malformed array-first JSON-like key-like stdout payload summary leaked needle: ${needle}`,
      );
      assert.equal(
        jsonMalformedArrayKeylikeStdoutRow.raw.includes(needle),
        false,
        `malformed array-first JSON-like key-like stdout JSONL row leaked needle: ${needle}`,
      );
    }
    assert.equal(
      jsonMalformedArrayKeylikeStdoutRow.raw.includes(highRisk.sample),
      false,
      'malformed array-first JSON-like key-like stdout JSONL row leaked full sample',
    );

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
