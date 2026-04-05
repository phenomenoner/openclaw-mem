import test from 'node:test';
import assert from 'node:assert/strict';

import { runScopedImportancePolicyLoopV0 } from './importancePolicyLoop.js';

function hit(id, score) {
  return {
    row: {
      id,
      text: id,
      createdAt: 1,
      category: 'other',
      importance: null,
      importance_label: 'unknown',
      scope: 'global',
      trust_tier: 'unknown',
    },
    distance: 0,
    score,
  };
}

function fuseRecall({ vector, fts, limit }) {
  // Keep it simple for unit tests: merge + global sort by score.
  const all = [...(vector ?? []), ...(fts ?? [])]
    .filter((item) => item?.row?.id)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, limit);
  return { order: all };
}

test('policy loop v0: baseline must+nice fills budget without consulting unknown/ignore', async () => {
  const calls = [];

  const result = await runScopedImportancePolicyLoopV0({
    query: 'q',
    limit: 3,
    searchLimit: 10,
    scopePlan: [{ scope: 'global', origin: 'primary' }],
    policyEnabled: true,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
    fuseRecall,
    fallback: { eligible: false, suppressedReason: 'disabled' },
    search: async ({ labels }) => {
      calls.push(labels ? labels.join('+') : 'UNFILTERED');
      if (labels?.includes('must_remember')) return { ftsResults: [], vecResults: [hit('m1', 0.99), hit('m2', 0.98)] };
      if (labels?.includes('nice_to_have')) return { ftsResults: [], vecResults: [hit('n1', 0.7), hit('n2', 0.69)] };
      throw new Error(`unexpected labels=${String(labels)}`);
    },
  });

  assert.equal(result.policyTier, 'must+nice');
  assert.equal(result.selected.length, 3);
  assert.equal(result.tierCounts.length, 2);
  assert.deepEqual(
    result.tierCounts.map((t) => t.tier),
    ['must', 'nice'],
  );
  assert.deepEqual(calls.sort(), ['must_remember', 'nice_to_have'].sort());
});

test('policy loop v0: widens to unknown when must+nice insufficient', async () => {
  const calls = [];

  const result = await runScopedImportancePolicyLoopV0({
    query: 'q',
    limit: 3,
    searchLimit: 10,
    scopePlan: [{ scope: 'global', origin: 'primary' }],
    policyEnabled: true,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
    fuseRecall,
    fallback: { eligible: false, suppressedReason: 'disabled' },
    search: async ({ labels }) => {
      calls.push(labels ? labels.join('+') : 'UNFILTERED');
      if (labels?.includes('must_remember')) return { ftsResults: [], vecResults: [hit('m1', 0.9)] };
      if (labels?.includes('nice_to_have')) return { ftsResults: [], vecResults: [] };
      if (labels?.includes('unknown')) return { ftsResults: [], vecResults: [hit('u1', 0.5), hit('u2', 0.49)] };
      throw new Error(`unexpected labels=${String(labels)}`);
    },
  });

  assert.equal(result.policyTier, 'must+nice+unknown');
  assert.equal(result.selected.length, 3);
  assert.deepEqual(result.tierCounts.map((t) => t.tier), ['must', 'nice', 'unknown']);
  assert.deepEqual(calls, ['must_remember', 'nice_to_have', 'unknown']);
});

test('policy loop v0: widens to ignore when must+nice+unknown insufficient', async () => {
  const calls = [];

  const result = await runScopedImportancePolicyLoopV0({
    query: 'q',
    limit: 2,
    searchLimit: 10,
    scopePlan: [{ scope: 'global', origin: 'primary' }],
    policyEnabled: true,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
    fuseRecall,
    fallback: { eligible: false, suppressedReason: 'disabled' },
    search: async ({ labels }) => {
      calls.push(labels ? labels.join('+') : 'UNFILTERED');
      if (labels?.includes('must_remember')) return { ftsResults: [], vecResults: [] };
      if (labels?.includes('nice_to_have')) return { ftsResults: [], vecResults: [] };
      if (labels?.includes('unknown')) return { ftsResults: [], vecResults: [] };
      if (labels?.includes('ignore')) return { ftsResults: [], vecResults: [hit('i1', 0.2), hit('i2', 0.19)] };
      throw new Error(`unexpected labels=${String(labels)}`);
    },
  });

  assert.equal(result.policyTier, 'must+nice+unknown+ignore');
  assert.equal(result.selected.length, 2);
  assert.deepEqual(result.tierCounts.map((t) => t.tier), ['must', 'nice', 'unknown', 'ignore']);
  assert.deepEqual(calls, ['must_remember', 'nice_to_have', 'unknown', 'ignore']);
});

test('policy loop v0: empty/disabled policy fail-open returns ignore tier with unfiltered search', async () => {
  const calls = [];

  const result = await runScopedImportancePolicyLoopV0({
    query: 'q',
    limit: 2,
    searchLimit: 10,
    scopePlan: [{ scope: 'global', origin: 'primary' }],
    policyEnabled: false,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
    fuseRecall,
    fallback: { eligible: false, suppressedReason: 'disabled' },
    search: async ({ labels }) => {
      calls.push(labels ? labels.join('+') : 'UNFILTERED');
      assert.equal(labels, undefined);
      return { ftsResults: [], vecResults: [hit('x1', 0.9), hit('x2', 0.8)] };
    },
  });

  assert.equal(result.policyTier, 'ignore');
  assert.equal(result.selected.length, 2);
  assert.deepEqual(result.tierCounts.map((t) => t.tier), ['ignore']);
  assert.deepEqual(calls, ['UNFILTERED']);
});
