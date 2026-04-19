import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { mirrorMemoryToGbrain, __private__ } from './gbrainMirror.js';

test('disabled config short-circuits without writing or importing', async () => {
  let called = false;
  const out = await mirrorMemoryToGbrain({
    memory: { id: 'mem-1', text: 'alpha', category: 'fact', importanceLabel: 'nice_to_have', scope: 'global', createdAt: 1 },
    config: { enabled: false, mirrorRoot: '/tmp/unused' },
    runner: async () => {
      called = true;
      throw new Error('should not run');
    },
  });

  assert.equal(called, false);
  assert.equal(out.receipt.attempted, false);
  assert.equal(out.receipt.mirrored, false);
  assert.equal(out.receipt.imported, false);
});

test('writes mirror markdown and runs gbrain import on store', async () => {
  const mirrorRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'gbrain-mirror-'));
  let runnerArgs = null;

  const out = await mirrorMemoryToGbrain({
    memory: {
      id: 'mem-2',
      text: 'remember this rollout decision',
      category: 'decision',
      importance: 0.8,
      importanceLabel: 'must_remember',
      scope: 'project.alpha',
      createdAt: 1710000000000,
    },
    config: { enabled: true, mirrorRoot, command: 'gbrain', commandArgs: ['--json'], timeoutMs: 2500 },
    runner: async ({ command, args, timeoutMs, env }) => {
      runnerArgs = { command, args, timeoutMs, env };
      return { ok: true, exitCode: 0, stdout: 'imported', stderr: '', errorCode: null, errorMessage: null };
    },
    env: { OPENAI_API_KEY: 'sk-test' },
  });

  const markdown = await fs.readFile(path.join(mirrorRoot, 'mem-2.md'), 'utf8');
  assert.match(markdown, /memory_id: "mem-2"/);
  assert.match(markdown, /category: "decision"/);
  assert.match(markdown, /# remember this rollout decision/);
  assert.equal(out.receipt.mirrored, true);
  assert.equal(out.receipt.imported, true);
  assert.deepEqual(runnerArgs, {
    command: 'gbrain',
    args: ['--json', 'import', mirrorRoot, '--workers', '1'],
    timeoutMs: 2500,
    env: { OPENAI_API_KEY: 'sk-test' },
  });
});

test('can mirror without immediate import', async () => {
  const mirrorRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'gbrain-mirror-'));
  let called = false;

  const out = await mirrorMemoryToGbrain({
    memory: { id: 'mem-3', text: 'alpha', category: 'fact', importanceLabel: 'nice_to_have', scope: 'global', createdAt: 1 },
    config: { enabled: true, mirrorRoot, importOnStore: false },
    runner: async () => {
      called = true;
      throw new Error('should not run');
    },
  });

  assert.equal(called, false);
  assert.equal(out.receipt.mirrored, true);
  assert.equal(out.receipt.imported, false);
  assert.equal(out.receipt.importSkipped, true);
});

test('receiptBase clamps timeout and trims arg list', () => {
  const base = __private__.receiptBase({ enabled: true, mirrorRoot: '/tmp/x', timeoutMs: 999999, commandArgs: [' a ', '', 1] });
  assert.equal(base.timeoutMs, 30000);
  assert.deepEqual(base.commandArgs, ['a']);
});
