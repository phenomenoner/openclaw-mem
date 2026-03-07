import test from 'node:test';
import assert from 'node:assert/strict';

import { runTierFirstV1, selectTierQuotaV1 } from './tierSelection.js';

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

function bucket(tier, hits) {
  return {
    plan: {
      tier,
      labels: tier === 'must' ? ['must_remember'] : tier === 'nice' ? ['nice_to_have'] : ['unknown'],
    },
    fused: hits,
  };
}

function selectedIds(result) {
  return result.selected.map((item) => item.row.id);
}

test('tier_quota_v1 caps must saturation and still reserves nice recall', () => {
  const result = selectTierQuotaV1({
    buckets: [
      bucket('must', [hit('m1', 0.99), hit('m2', 0.98), hit('m3', 0.97), hit('m4', 0.96)]),
      bucket('nice', [hit('n1', 0.7), hit('n2', 0.69)]),
      bucket('unknown', [hit('u1', 0.4)]),
    ],
    limit: 4,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
  });

  assert.deepEqual(selectedIds(result), ['m1', 'm2', 'n1', 'n2']);
  assert.equal(result.selectedByTier.must, 2);
  assert.equal(result.selectedByTier.nice, 2);
  assert.equal(result.quota.wildcardUsed, 0);
});

test('tier_quota_v1 handles candidates fewer than quota without overfilling', () => {
  const result = selectTierQuotaV1({
    buckets: [
      bucket('must', [hit('m1', 0.91)]),
      bucket('nice', [hit('n1', 0.81)]),
      bucket('unknown', [hit('u1', 0.51)]),
    ],
    limit: 5,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
  });

  assert.deepEqual(selectedIds(result), ['m1', 'n1', 'u1']);
  assert.equal(result.selected.length, 3);
  assert.equal(result.quota.wildcardUsed, 0);
});

test('tier_quota_v1 wildcard spill fills remaining slots by global score', () => {
  const result = selectTierQuotaV1({
    buckets: [
      bucket('must', [hit('m1', 0.9), hit('m2', 0.8), hit('m3', 0.7)]),
      bucket('nice', [hit('n1', 0.95)]),
      bucket('unknown', [hit('u1', 0.99), hit('u2', 0.6)]),
    ],
    limit: 5,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 0 },
  });

  assert.deepEqual(selectedIds(result), ['m1', 'm2', 'n1', 'u1', 'm3']);
  assert.equal(result.selectedByTier.must, 3);
  assert.equal(result.selectedByTier.nice, 1);
  assert.equal(result.selectedByTier.unknown, 1);
  assert.equal(result.quota.wildcardUsed, 2);
});

test('tier_quota_v1 is robust when must/unknown tiers are empty', () => {
  const result = selectTierQuotaV1({
    buckets: [bucket('must', []), bucket('nice', [hit('n1', 0.9), hit('n2', 0.8), hit('n3', 0.7)]), bucket('unknown', [])],
    limit: 3,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
  });

  assert.deepEqual(selectedIds(result), ['n1', 'n2', 'n3']);
  assert.equal(result.selectedByTier.nice, 3);
  assert.equal(result.quota.wildcardUsed, 1);
});

test('tier_quota_v1 respects limit when quota sum exceeds budget', () => {
  const result = selectTierQuotaV1({
    buckets: [
      bucket('must', [hit('m1', 0.99), hit('m2', 0.98)]),
      bucket('nice', [hit('n1', 0.6), hit('n2', 0.59)]),
      bucket('unknown', [hit('u1', 0.4)]),
    ],
    limit: 2,
    quotas: { mustMax: 2, niceMin: 2, unknownMax: 1 },
  });

  // Current quota policy reserves nice first when budget is tight.
  assert.deepEqual(selectedIds(result), ['n1', 'n2']);
  assert.equal(result.selectedByTier.must ?? 0, 0);
  assert.equal(result.selectedByTier.nice, 2);
});

test('tier_first_v1 keeps early-exit semantics when limit is already filled', async () => {
  const calls = [];

  const result = await runTierFirstV1({
    query: 'q',
    scope: 'global',
    limit: 2,
    searchLimit: 10,
    plans: [
      { tier: 'must', labels: ['must_remember'], missReason: 'must_missing' },
      { tier: 'nice', labels: ['nice_to_have'], missReason: 'nice_missing' },
    ],
    search: async ({ labels }) => {
      const tier = labels[0] === 'must_remember' ? 'must' : 'nice';
      calls.push(tier);

      if (tier === 'must') {
        return {
          ftsResults: [],
          vecResults: [hit('m1', 0.9), hit('m2', 0.89), hit('m3', 0.88)],
        };
      }

      throw new Error('nice tier should not be queried after budget cap');
    },
    fuseRecall: ({ vector }) => ({ order: vector }),
  });

  assert.deepEqual(calls, ['must']);
  assert.deepEqual(result.selected.map((item) => item.row.id), ['m1', 'm2']);
  assert.equal(result.rejected.includes('budget_cap'), true);
  assert.equal(result.tierCounts.length, 1);
});
