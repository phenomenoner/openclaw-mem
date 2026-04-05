import { selectTierQuotaV1 } from './tierSelection.js';

function uniqueReasons(values) {
  const seen = new Set();
  const out = [];
  for (const value of values ?? []) {
    if (!value) continue;
    if (seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
}

function compareHits(a, b) {
  if (b.score !== a.score) return b.score - a.score;
  const idDiff = String(a.row?.id ?? '').localeCompare(String(b.row?.id ?? ''));
  if (idDiff !== 0) return idDiff;
  return 0;
}

export function policyTierLabel(mode) {
  if (!mode?.enabled) return 'ignore';
  if (mode.usedIgnore) return 'must+nice+unknown+ignore';
  if (mode.usedUnknown) return 'must+nice+unknown';
  return 'must+nice';
}

/**
 * Importance policy loop v0.
 *
 * Contract:
 * - default policy is fail-open: start with must+nice, then widen to unknown, then ignore.
 * - when policy is disabled/empty, run unfiltered recall ("ignore") so callers still get results.
 *
 * Input callback `search` should already handle fail-open lexical-only behavior when embeddings are missing.
 */
export async function runScopedImportancePolicyLoopV0(input) {
  const query = String(input.query ?? '').trim();
  const limit = Math.max(1, Number(input.limit ?? 1));
  const searchLimit = Math.max(limit, Number(input.searchLimit ?? limit));
  const scopePlan = Array.isArray(input.scopePlan) ? input.scopePlan : [];
  const fuseRecall = input.fuseRecall;
  const search = input.search;
  const policyEnabled = Boolean(input.policyEnabled);
  const quotas = input.quotas ?? { mustMax: 2, niceMin: 2, unknownMax: 1 };

  if (typeof fuseRecall !== 'function') {
    throw new Error('missing fuseRecall');
  }
  if (typeof search !== 'function') {
    throw new Error('missing search');
  }

  const selected = [];
  const seen = new Set();
  const tierCounts = [];
  const ftsResults = [];
  const vecResults = [];
  const rejected = [];

  const consultedScopes = [];
  const usedScopes = [];
  let primaryCount = 0;

  const fallbackEligible = Boolean(input.fallback?.eligible);
  const fallbackSuppressedReason = input.fallback?.suppressedReason ?? null;

  let usedUnknown = false;
  let usedIgnore = false;

  const addSelectedHits = (hits, remaining) => {
    let added = 0;
    for (const hit of hits) {
      if (added >= remaining) break;
      const id = String(hit?.row?.id ?? '').trim();
      if (!id) continue;
      if (seen.has(id)) continue;
      seen.add(id);
      selected.push(hit);
      added += 1;
      if (selected.length >= limit) break;
    }
    return added;
  };

  const runUnfilteredTier = async (scope, prefix, remaining) => {
    const { ftsResults: tierFts, vecResults: tierVec } = await search({
      query,
      scope,
      labels: undefined,
      searchLimit,
    });

    ftsResults.push(...tierFts);
    vecResults.push(...tierVec);

    const fused = fuseRecall({ vector: tierVec, fts: tierFts, limit: searchLimit }).order;
    const added = addSelectedHits(fused, remaining);

    tierCounts.push({
      tier: `${prefix}ignore`,
      labels: [],
      candidates: fused.length,
      selected: added,
    });

    return added;
  };

  const runBaselineMustNice = async (scope, prefix, remaining) => {
    const planMust = { tier: 'must', labels: ['must_remember'], missReason: 'no_results_must' };
    const planNice = { tier: 'nice', labels: ['nice_to_have'], missReason: 'no_results_nice' };

    const mustResp = await search({ query, scope, labels: planMust.labels, searchLimit });
    const niceResp = await search({ query, scope, labels: planNice.labels, searchLimit });

    ftsResults.push(...(mustResp.ftsResults ?? []), ...(niceResp.ftsResults ?? []));
    vecResults.push(...(mustResp.vecResults ?? []), ...(niceResp.vecResults ?? []));

    const mustFused = fuseRecall({ vector: mustResp.vecResults ?? [], fts: mustResp.ftsResults ?? [], limit: searchLimit }).order;
    const niceFused = fuseRecall({ vector: niceResp.vecResults ?? [], fts: niceResp.ftsResults ?? [], limit: searchLimit }).order;

    if (mustFused.length === 0) rejected.push(planMust.missReason);
    if (niceFused.length === 0) rejected.push(planNice.missReason);

    const buckets = [
      { plan: planMust, fused: mustFused },
      { plan: planNice, fused: niceFused },
    ];

    const selection = selectTierQuotaV1({
      buckets,
      limit: remaining,
      quotas,
    });

    const added = addSelectedHits(selection.selected, remaining);

    tierCounts.push({
      tier: `${prefix}must`,
      labels: planMust.labels,
      candidates: mustFused.length,
      selected: selection.selectedByTier.must ?? 0,
    });

    tierCounts.push({
      tier: `${prefix}nice`,
      labels: planNice.labels,
      candidates: niceFused.length,
      selected: selection.selectedByTier.nice ?? 0,
    });

    if (added >= remaining) {
      rejected.push('budget_cap');
    }

    return added;
  };

  const runSingleTierFill = async ({ scope, prefix, remaining, tier, labels }) => {
    if (remaining <= 0) return 0;

    const { ftsResults: tierFts, vecResults: tierVec } = await search({ query, scope, labels, searchLimit });
    ftsResults.push(...tierFts);
    vecResults.push(...tierVec);

    const fused = fuseRecall({ vector: tierVec, fts: tierFts, limit: searchLimit }).order;
    const added = addSelectedHits(fused, remaining);

    tierCounts.push({
      tier: `${prefix}${tier}`,
      labels,
      candidates: fused.length,
      selected: added,
    });

    if (tier === 'unknown' && added > 0) usedUnknown = true;
    if (tier === 'ignore' && added > 0) usedIgnore = true;

    return added;
  };

  for (const plan of scopePlan) {
    if (selected.length >= limit) break;

    const scope = String(plan?.scope ?? '').trim();
    const origin = plan?.origin === 'fallback' ? 'fallback' : 'primary';
    if (!scope) continue;

    const beforeScopeCount = selected.length;

    const prefix = origin === 'fallback' ? `${scope}:` : '';

    if (origin === 'fallback') {
      consultedScopes.push(scope);
    }

    const remainingStart = Math.max(0, limit - selected.length);

    if (!policyEnabled) {
      const added = await runUnfilteredTier(scope, prefix, remainingStart);
      if (origin === 'primary') {
        primaryCount = selected.length;
      } else if (added > 0) {
        usedScopes.push(scope);
      }
      continue;
    }

    await runBaselineMustNice(scope, prefix, remainingStart);

    const remainingAfterBaseline = Math.max(0, limit - selected.length);
    if (remainingAfterBaseline > 0) {
      const addedUnknown = await runSingleTierFill({
        scope,
        prefix,
        remaining: remainingAfterBaseline,
        tier: 'unknown',
        labels: ['unknown'],
      });

      const remainingAfterUnknown = Math.max(0, limit - selected.length);
      if (remainingAfterUnknown > 0) {
        await runSingleTierFill({
          scope,
          prefix,
          remaining: remainingAfterUnknown,
          tier: 'ignore',
          labels: ['ignore'],
        });
      }

      if (addedUnknown > 0) {
        usedUnknown = true;
      }
    }

    const addedInScope = selected.length - beforeScopeCount;
    if (origin === 'primary') {
      primaryCount = selected.length;
    } else if (addedInScope > 0) {
      usedScopes.push(scope);
    }
  }

  const policyTier = policyTierLabel({ enabled: policyEnabled, usedUnknown, usedIgnore });

  return {
    selected,
    tierCounts,
    ftsResults,
    vecResults,
    fusedResults: selected,
    rejected: uniqueReasons(rejected),
    policyTier,
    fallback: {
      eligible: fallbackEligible,
      consulted: consultedScopes.length > 0,
      consultedScopes,
      usedScopes,
      contributed: Math.max(0, selected.length - primaryCount),
      suppressedReason: fallbackSuppressedReason,
    },
  };
}
