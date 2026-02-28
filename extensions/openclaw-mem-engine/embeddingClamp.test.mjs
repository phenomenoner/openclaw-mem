import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CLIP_MARKER,
  clampEmbeddingInput,
  resolveEmbeddingClampConfig,
} from './embeddingClamp.js';

test('resolveEmbeddingClampConfig defaults', () => {
  const cfg = resolveEmbeddingClampConfig(undefined);
  assert.equal(typeof cfg.maxChars, 'number');
  assert.equal(typeof cfg.headChars, 'number');
  assert.ok(cfg.maxChars > 0);
  assert.ok(cfg.headChars >= 0);
});

test('clampEmbeddingInput no-op when under limits', () => {
  const cfg = { maxChars: 50, headChars: 10 };
  const input = 'hello world';
  const out = clampEmbeddingInput(input, cfg);
  assert.equal(out.text, input);
  assert.equal(out.clipped, false);
});

test('clampEmbeddingInput preserves head and tail with marker', () => {
  const cfg = { maxChars: 40, headChars: 8 };
  const input = 'A'.repeat(100) + 'TAIL'.repeat(30);
  const out = clampEmbeddingInput(input, cfg);

  assert.equal(out.text.length, cfg.maxChars);
  assert.equal(out.clipped, true);
  assert.ok(out.text.startsWith('A'.repeat(cfg.headChars)));
  assert.ok(out.text.includes(CLIP_MARKER));

  const tailBudget = cfg.maxChars - cfg.headChars - CLIP_MARKER.length;
  assert.ok(out.text.endsWith(input.slice(input.length - tailBudget)));
});

test('clampEmbeddingInput tail-only when headChars=0', () => {
  const cfg = { maxChars: 30, headChars: 0 };
  const input = '0123456789'.repeat(10);
  const out = clampEmbeddingInput(input, cfg);
  assert.equal(out.text, input.slice(input.length - cfg.maxChars));
  assert.equal(out.text.length, cfg.maxChars);
});

test('clampEmbeddingInput enforces maxBytes (utf8)', () => {
  // '漢' is 3 bytes in UTF-8.
  const input = '漢'.repeat(2000);
  const cfg = { maxChars: 6000, headChars: 10, maxBytes: 3000 };
  const out = clampEmbeddingInput(input, cfg);

  assert.equal(out.clipped, true);
  assert.ok(out.clampedBytes <= cfg.maxBytes);
});
