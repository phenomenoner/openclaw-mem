import test from 'node:test';
import assert from 'node:assert/strict';

import { runWeiJiMemoryPreflight, __private__ } from './weiJiMemoryPreflight.js';

test('disabled config short-circuits without subprocess call', async () => {
  let called = false;
  const out = await runWeiJiMemoryPreflight({
    intent: { text: 'remember me' },
    config: { enabled: false },
    runner: async () => {
      called = true;
      throw new Error('should not run');
    },
  });

  assert.equal(called, false);
  assert.equal(out.allowed, true);
  assert.equal(out.blocked, false);
  assert.equal(out.receipt.enabled, false);
  assert.equal(out.receipt.attempted, false);
});

test('fail-open allows memory write when subprocess is missing', async () => {
  const out = await runWeiJiMemoryPreflight({
    intent: { text: 'remember me' },
    config: {
      enabled: true,
      command: 'weiji-memory-preflight',
      failMode: 'open',
    },
    runner: async () => ({
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      errorCode: 'ENOENT',
      errorMessage: 'spawn ENOENT',
    }),
  });

  assert.equal(out.allowed, true);
  assert.equal(out.blocked, false);
  assert.equal(out.receipt.runtimeFailed, true);
  assert.equal(out.receipt.errorCode, 'ENOENT');
  assert.equal(out.receipt.decision, 'allow');
});

test('fail-closed blocks memory write when subprocess is missing', async () => {
  const out = await runWeiJiMemoryPreflight({
    intent: { text: 'remember me' },
    config: {
      enabled: true,
      command: 'weiji-memory-preflight',
      failMode: 'closed',
    },
    runner: async () => ({
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      errorCode: 'ENOENT',
      errorMessage: 'spawn ENOENT',
    }),
  });

  assert.equal(out.allowed, false);
  assert.equal(out.blocked, true);
  assert.equal(out.receipt.runtimeFailed, true);
  assert.equal(out.receipt.decision, 'block');
});

test('queued result blocks when failOnQueued is enabled', async () => {
  const stdout = JSON.stringify({
    wrapper: 'weiji-memory-preflight',
    ok: false,
    exit_code: 40,
    fail_reason: 'memory_write_queued_for_review',
    result: {
      memory_governor: {
        status: 'queued',
        review_required: true,
      },
    },
  });

  const out = await runWeiJiMemoryPreflight({
    intent: { text: 'remember me' },
    config: {
      enabled: true,
      command: 'weiji-memory-preflight',
      failOnQueued: true,
      failMode: 'open',
    },
    runner: async () => ({
      ok: false,
      exitCode: 40,
      stdout,
      stderr: '',
      errorCode: null,
      errorMessage: 'non-zero',
    }),
  });

  assert.equal(out.allowed, false);
  assert.equal(out.blocked, true);
  assert.equal(out.receipt.policyBlock, true);
  assert.equal(out.receipt.wrapperExitCode, 40);
  assert.equal(out.receipt.governorStatus, 'queued');
});

test('parseJsonLoose can recover json line from noisy output', () => {
  const payload = __private__.parseJsonLoose('noise\n{"ok":true}\nmore-noise');
  assert.deepEqual(payload, { ok: true });
});
