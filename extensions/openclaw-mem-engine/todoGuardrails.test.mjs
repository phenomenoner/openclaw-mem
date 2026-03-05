import test from 'node:test';
import assert from 'node:assert/strict';

import {
  todoDedupeCutoffMs,
  isTodoWithinDedupeWindow,
  todoStaleCutoffMs,
  isTodoStale,
} from './todoGuardrails.js';

test('todo dedupe window helper is deterministic', () => {
  const now = 1_700_000_000_000;
  const cutoff = todoDedupeCutoffMs(now, 24);
  assert.equal(cutoff, now - 24 * 60 * 60 * 1000);

  assert.equal(isTodoWithinDedupeWindow(now - 1, now, 24), true);
  assert.equal(isTodoWithinDedupeWindow(now - 25 * 60 * 60 * 1000, now, 24), false);
});

test('todo stale ttl helper is deterministic', () => {
  const now = 1_700_000_000_000;
  const staleCutoff = todoStaleCutoffMs(now, 7);
  assert.equal(staleCutoff, now - 7 * 24 * 60 * 60 * 1000);

  assert.equal(isTodoStale(now - 8 * 24 * 60 * 60 * 1000, now, 7), true);
  assert.equal(isTodoStale(now - 6 * 24 * 60 * 60 * 1000, now, 7), false);
});
